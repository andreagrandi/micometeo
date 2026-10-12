"""Focused checks for map request validation and stored result states."""

import gzip
import json
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from math import isclose
from pathlib import Path
from time import monotonic, sleep
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.cache import cache
from django.test import Client
from django.test import override_settings
from shapely import transform as shapely_transform
from shapely.wkb import loads as load_wkb

from estimate_updates.models import EstimateResult, EstimateUpdate
from micometeo.finds.grid import format_cell_id
from map_api.api import (
    MAX_DAYS_AHEAD,
    MAX_VIEW_HEIGHT_M,
    MAX_VIEW_WIDTH_M,
    GRID_TO_WGS84,
    _coverage,
    _bbox_size_m,
    _cache_key,
    _parse_bbox,
    _parse_date,
    _result_properties,
)
from national_forest import layer
from national_forest.models import ForestBuild, ForestCell, ForestChunk
from national_grid.models import GridBuild, GridBuildCell, GridCell, GridChunk, GridRegion
from national_terrain.models import TerrainBuild
import weather_on_demand.services as weather_services
from weather_requests.models import WeatherRequest, WeatherRequestAttempt
from weather_summaries.models import WeatherDaily, WeatherSnapshot


MAP_DATE = date(2026, 10, 12)


class _MapFakeOpenMeteo:
    """Return a complete deterministic hourly response for #46."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    @property
    def call_count(self) -> int:
        """Return the number of provider requests made by the service."""
        return len(self.calls)

    def __call__(self, *, url: str, timeout: float) -> object:
        del timeout
        query = {
            key: values[0]
            for key, values in parse_qs(urlsplit(url).query).items()
        }
        self.calls.append(query)

        def query_time(*, date_name: str, hour_name: str) -> datetime:
            hour_value = query[hour_name]
            if "T" in hour_value:
                parsed = datetime.fromisoformat(hour_value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
            return datetime.fromisoformat(
                f"{query[date_name]}T{int(hour_value):02d}:00:00+00:00"
            )

        start = query_time(date_name="start_date", hour_name="start_hour")
        end = query_time(date_name="end_date", hour_name="end_hour")
        hours = int((end - start).total_seconds() // 3600) + 1
        variables = query["hourly"].split(",")
        units = {
            "precipitation": "mm",
            "temperature_2m": "°C",
            "soil_moisture_0_to_7cm": "m³/m³",
            "soil_temperature_0_to_7cm": "°C",
            "et0_fao_evapotranspiration": "mm",
        }
        times = [int((start + timedelta(hours=index)).timestamp()) for index in range(hours)]
        latitudes = query["latitude"].split(",")
        longitudes = query["longitude"].split(",")
        return [
            {
                "latitude": float(latitude),
                "longitude": float(longitude),
                "elevation": 200,
                "timezone": "GMT",
                "hourly_units": {variable: units[variable] for variable in variables},
                "hourly": {
                    "time": times,
                    **{
                        variable: [
                            1.0
                            if variable == "precipitation"
                            else 0.5
                            if variable == "soil_moisture_0_to_7cm"
                            else 10.0
                        ]
                        * hours
                        for variable in variables
                    },
                },
            }
            for latitude, longitude in zip(latitudes, longitudes, strict=True)
        ]


def _layer_metadata(*, path: Path, rows: list[dict[str, object]]) -> dict[str, object]:
    """Write one small deterministic forest artifact and return its metadata."""
    artifact = layer.write_forest_layer(rows=rows, output_path=path)
    return {
        "layer_path": str(artifact.path),
        "layer_sha256": artifact.sha256,
        "layer_gzip_bytes": artifact.gzip_bytes,
        "layer_raw_bytes": artifact.raw_bytes,
    }


@pytest.fixture
def map_fixture(tmp_path: Path) -> dict[str, object]:
    """Create a compact national-build fixture with stored map states."""
    suffix = uuid4().hex[:10]
    west, south = 4_300_000, 2_300_000
    polygon = Polygon.from_bbox((west, south, west + 2_000, south + 500))
    polygon.srid = 3035
    multipolygon = MultiPolygon(polygon)
    multipolygon.srid = 3035
    grid = GridBuild.objects.create(
        version=f"map-grid-{suffix}",
        fingerprint="a" * 64,
        status=GridBuild.Status.COMPLETED,
        planned_chunk_count=1,
        completed_chunk_count=1,
        cell_count=5,
    )
    region = GridRegion.objects.create(
        build=grid,
        istat_code=f"R{suffix}",
        name=f"Map region {suffix}",
        geometry=multipolygon,
    )
    grid_chunk = GridChunk.objects.create(
        build=grid,
        west_e=west,
        south_n=south,
        east_e=west + 2_500,
        north_n=south + 500,
        status=GridChunk.Status.COMPLETED,
        cell_count=4,
    )
    memberships: list[GridBuildCell] = []
    for index in range(5):
        corner_e = west + index * 500
        cell_polygon = Polygon.from_bbox((corner_e, south, corner_e + 500, south + 500))
        cell_polygon.srid = 3035
        grid_cell = GridCell.objects.create(
            cell_id=format_cell_id(corner_e=corner_e, corner_n=south),
            corner_e=corner_e,
            corner_n=south,
            geometry=cell_polygon,
        )
        memberships.append(
            GridBuildCell.objects.create(
                build=grid,
                cell=grid_cell,
                chunk=grid_chunk,
                owner_region=region,
                land_geometry=multipolygon,
                land_share=1.0,
            )
        )
    forest = ForestBuild.objects.create(
        version=f"map-forest-{suffix}",
        grid_build=grid,
        fingerprint="b" * 64,
        status=ForestBuild.Status.COMPLETED,
        planned_chunk_count=1,
        completed_chunk_count=1,
        cell_count=5,
        forest_cell_count=2,
        weather_cell_count=2,
    )
    forest_chunk = ForestChunk.objects.create(
        build=forest,
        grid_chunk=grid_chunk,
        west_e=west,
        south_n=south,
        east_e=west + 2_500,
        north_n=south + 500,
        status=ForestChunk.Status.COMPLETED,
        cell_count=5,
    )
    forest_cells = [
        ForestCell.objects.create(
            build=forest,
            grid_build_cell=memberships[0],
            chunk=forest_chunk,
            total_pixel_count=100,
            valid_pixel_count=100,
            forest_pixel_count=100,
            broadleaf_pixel_count=100,
            valid_coverage=1.0,
            coverage_quality="high",
            forest_share=1.0,
            broadleaf_share=1.0,
            leaf_type=ForestCell.LeafType.BROADLEAF,
            is_forest=True,
            weather_latitude=44.0,
            weather_longitude=11.0,
        ),
        ForestCell.objects.create(
            build=forest,
            grid_build_cell=memberships[1],
            chunk=forest_chunk,
            total_pixel_count=100,
            valid_pixel_count=100,
            forest_pixel_count=0,
            broadleaf_pixel_count=0,
            valid_coverage=1.0,
            coverage_quality="high",
            forest_share=0.0,
            leaf_type=ForestCell.LeafType.NO_FOREST,
            is_forest=False,
        ),
        ForestCell.objects.create(
            build=forest,
            grid_build_cell=memberships[2],
            chunk=forest_chunk,
            total_pixel_count=100,
            valid_pixel_count=0,
            forest_pixel_count=0,
            broadleaf_pixel_count=0,
            valid_coverage=0.0,
            coverage_quality="unavailable",
            forest_share=None,
            leaf_type=None,
            is_forest=None,
            missing_reason="source_gap",
        ),
        ForestCell.objects.create(
            build=forest,
            grid_build_cell=memberships[3],
            chunk=forest_chunk,
            total_pixel_count=100,
            valid_pixel_count=100,
            forest_pixel_count=100,
            broadleaf_pixel_count=100,
            valid_coverage=1.0,
            coverage_quality="high",
            forest_share=1.0,
            broadleaf_share=1.0,
            leaf_type=ForestCell.LeafType.BROADLEAF,
            is_forest=True,
            weather_latitude=44.1,
            weather_longitude=11.1,
        ),
        ForestCell.objects.create(
            build=forest,
            grid_build_cell=memberships[4],
            chunk=forest_chunk,
            total_pixel_count=100,
            valid_pixel_count=0,
            forest_pixel_count=0,
            broadleaf_pixel_count=0,
            valid_coverage=0.0,
            coverage_quality="unavailable",
            forest_share=None,
            leaf_type=None,
            is_forest=None,
            missing_reason="optional_missing",
        ),
    ]
    rows = [
        {
            "corner_e": west + index * 500,
            "corner_n": south,
            "forest_pixel_count": 100 if index in {0, 3} else 0,
            "valid_pixel_count": 100,
            "is_forest": index != 2,
        }
        for index in range(5)
    ]
    forest_data = _layer_metadata(path=tmp_path / "forest-layer.gz", rows=rows)
    for field, value in forest_data.items():
        setattr(forest, field, value)
    forest.save(update_fields=[*forest_data, "updated_at"])
    terrain = TerrainBuild.objects.create(
        version=f"map-terrain-{suffix}",
        grid_build=grid,
        fingerprint="c" * 64,
        grid_fingerprint=grid.fingerprint,
        status=TerrainBuild.Status.COMPLETED,
    )
    snapshot = WeatherSnapshot.objects.create(
        cell_key="44.00,11.00",
        assessment_date=MAP_DATE,
        latest_retrieval=datetime(2026, 10, 12, 10, tzinfo=UTC),
        source_ids=["map:test"],
        source_attempt_ids=["map:attempt"],
    )
    old_update = EstimateUpdate.objects.create(
        cell_key=snapshot.cell_key,
        assessment_date=MAP_DATE,
        calculated_at=datetime(2026, 10, 12, 8, tzinfo=UTC),
        snapshot=snapshot,
        forest_build=forest,
        terrain_build=terrain,
        method_version="map-test-old",
        row_count=1,
        input_fingerprint=sha256(f"old-{suffix}".encode()).hexdigest(),
    )
    new_update = EstimateUpdate.objects.create(
        cell_key=snapshot.cell_key,
        assessment_date=MAP_DATE,
        calculated_at=datetime(2026, 10, 12, 9, tzinfo=UTC),
        snapshot=snapshot,
        forest_build=forest,
        terrain_build=terrain,
        method_version="map-test-new",
        row_count=1,
        input_fingerprint=sha256(f"new-{suffix}".encode()).hexdigest(),
    )
    EstimateResult.objects.create(update=old_update, forest_cell=forest_cells[0], values=bytes([11] * 8))
    EstimateResult.objects.create(
        update=new_update,
        forest_cell=forest_cells[0],
        values=bytes([0, 42, 42, 42, 42, 42, 42, 42]),
    )
    return {
        "build": forest,
        "cells": forest_cells,
        "snapshot": snapshot,
        "old_update": old_update,
        "new_update": new_update,
        "bbox": "9.73,43.80,9.78,43.83",
    }


def test_bbox_parser_requires_four_finite_wgs84_values() -> None:
    parsed, error = _parse_bbox(value="10,44,10.1,44.1")

    assert error is None
    assert parsed == (10.0, 44.0, 10.1, 44.1)


@pytest.mark.parametrize(
    "value",
    [
        "10,44,10",
        "nan,44,10.1,44.1",
        "10,44,181,44.1",
        "10.1,44,10,44.1",
        "10,45,10.1,44",
    ],
)
def test_bbox_parser_rejects_malformed_nonfinite_out_of_range_and_reversed_values(
    value: str,
) -> None:
    parsed, error = _parse_bbox(value=value)

    assert parsed is None
    assert error is not None
    assert error.status_code == 400
    assert json.loads(error.content)["code"] == "invalid_bbox"


def test_date_parser_requires_exact_iso_date() -> None:
    parsed, error = _parse_date(value="2026-10-12")

    assert error is None
    assert parsed == date(2026, 10, 12)

    parsed, error = _parse_date(value="2026-1-2")
    assert parsed is None
    assert error is not None
    assert json.loads(error.content)["code"] == "invalid_date"


def test_bbox_size_uses_wgs84_geodesic_distance() -> None:
    width_m, height_m = _bbox_size_m(bbox=(10.0, 44.0, 10.5, 44.5))

    assert width_m > 0
    assert height_m > 0
    assert width_m < MAX_VIEW_WIDTH_M
    assert height_m < MAX_VIEW_HEIGHT_M


@pytest.mark.django_db(transaction=True)
def test_coverage_uses_the_transformed_extent_of_stored_cell_geometry() -> None:
    suffix = uuid4().hex[:10]
    west, south = 4_300_000, 2_300_000
    first_geometry = Polygon.from_bbox((west, south, west + 500, south + 500))
    second_geometry = Polygon.from_bbox((west + 20_000, south + 20_000, west + 20_500, south + 20_500))
    first_geometry.srid = 3035
    second_geometry.srid = 3035
    region_geometry = MultiPolygon(first_geometry, second_geometry, srid=3035)
    grid = GridBuild.objects.create(
        version=f"coverage-grid-{suffix}",
        fingerprint="a" * 64,
        status=GridBuild.Status.COMPLETED,
        planned_chunk_count=1,
        completed_chunk_count=1,
        cell_count=2,
    )
    region = GridRegion.objects.create(
        build=grid,
        istat_code=f"C{suffix}",
        name="Coverage test region",
        geometry=region_geometry,
    )
    chunk = GridChunk.objects.create(
        build=grid,
        west_e=west,
        south_n=south,
        east_e=west + 20_500,
        north_n=south + 20_500,
        status=GridChunk.Status.COMPLETED,
        cell_count=2,
    )
    for geometry in (first_geometry, second_geometry):
        cell = GridCell.objects.create(
            cell_id=format_cell_id(
                corner_e=int(geometry.extent[0]),
                corner_n=int(geometry.extent[1]),
            ),
            corner_e=int(geometry.extent[0]),
            corner_n=int(geometry.extent[1]),
            geometry=geometry,
        )
        GridBuildCell.objects.create(
            build=grid,
            cell=cell,
            chunk=chunk,
            owner_region=region,
            land_geometry=MultiPolygon(geometry, srid=3035),
            land_share=1.0,
        )
    forest = ForestBuild.objects.create(
        version=f"coverage-forest-{suffix}",
        grid_build=grid,
        fingerprint="b" * 64,
        status=ForestBuild.Status.COMPLETED,
        planned_chunk_count=1,
        completed_chunk_count=1,
        cell_count=2,
    )

    actual = _coverage(build=forest)
    expected = [float("inf"), float("inf"), float("-inf"), float("-inf")]
    for geometry in (first_geometry, second_geometry):
        transformed = shapely_transform(
            load_wkb(bytes(geometry.wkb)),
            GRID_TO_WGS84.transform,
            interleaved=False,
        )
        geometry_bounds = transformed.bounds
        expected[0] = min(expected[0], geometry_bounds[0])
        expected[1] = min(expected[1], geometry_bounds[1])
        expected[2] = max(expected[2], geometry_bounds[2])
        expected[3] = max(expected[3], geometry_bounds[3])

    assert actual is not None
    assert all(
        isclose(actual_value, expected_value, rel_tol=0.0, abs_tol=1e-7)
        for actual_value, expected_value in zip(
            (actual.west, actual.south, actual.east, actual.north),
            expected,
            strict=True,
        )
    )


def test_cache_key_changes_when_an_immutable_update_changes() -> None:
    first = _cache_key(
        build_version="forest-v1",
        bbox=(10.0, 44.0, 10.1, 44.1),
        target_date=date(2026, 10, 12),
        weather_items=(("44.00,10.00", "current", "snapshot-a", "update-a"),),
    )
    second = _cache_key(
        build_version="forest-v1",
        bbox=(10.0, 44.0, 10.1, 44.1),
        target_date=date(2026, 10, 12),
        weather_items=(("44.00,10.00", "current", "snapshot-a", "update-b"),),
    )

    assert first != second


def test_result_properties_keep_zero_distinct_from_no_forest() -> None:
    update_id = uuid4()
    update = SimpleNamespace(
        assessment_date=date(2026, 10, 12),
        public_id=update_id,
        calculated_at=datetime(2026, 10, 12, 8, 0),
    )
    estimate = SimpleNamespace(values=bytes([0] + [20] * (MAX_DAYS_AHEAD)))
    forest_cell = SimpleNamespace(
        is_forest=True,
        forest_share=1.0,
        missing_reason="",
        weather_latitude=44.0,
        weather_longitude=10.0,
        grid_build_cell=SimpleNamespace(cell=SimpleNamespace(cell_id="stable500m_E1_N2")),
    )
    properties = _result_properties(
        cell=forest_cell,
        target_date=date(2026, 10, 12),
        weather_result=SimpleNamespace(state="current", assessment_date=date(2026, 10, 12)),
        update=update,
        estimate_result=estimate,
    )

    assert properties["state"] == "available"
    assert properties["percentage"] == 0
    assert properties["unavailable_reason"] is None

    forest_cell.is_forest = False
    forest_cell.forest_share = 0.0
    no_forest = _result_properties(
        cell=forest_cell,
        target_date=date(2026, 10, 12),
        weather_result=None,
        update=None,
        estimate_result=None,
    )

    assert no_forest["state"] == "noforest"
    assert no_forest["percentage"] is None
    assert no_forest["unavailable_reason"] == "noforest"


def test_result_properties_mark_previous_update_outside_its_eight_day_range_expired() -> None:
    forest_cell = SimpleNamespace(
        is_forest=True,
        forest_share=1.0,
        missing_reason="",
        weather_latitude=44.0,
        weather_longitude=10.0,
        grid_build_cell=SimpleNamespace(cell=SimpleNamespace(cell_id="stable500m_E1_N2")),
    )
    update = SimpleNamespace(
        assessment_date=date(2026, 10, 1),
        public_id=uuid4(),
        calculated_at=None,
    )
    result = _result_properties(
        cell=forest_cell,
        target_date=date(2026, 10, 12),
        weather_result=SimpleNamespace(state="previous", assessment_date=date(2026, 10, 1)),
        update=update,
        estimate_result=SimpleNamespace(values=bytes([25] * 8)),
    )

    assert result["state"] == "expired"
    assert result["unavailable_reason"] == "target_outside_update_range"


@pytest.mark.django_db
def test_registered_squares_route_validates_before_database_reads() -> None:
    response = Client().get(
        "/api/v1/squares",
        headers={"Host": "127.0.0.1"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "missing_parameter"


def test_broad_view_returns_zoom_in_error_without_weather_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(**kwargs: object) -> None:
        raise AssertionError("broad views must not request weather")

    monkeypatch.setattr("map_api.api.weather_services.request_weather", fail_if_called)
    response = Client().get(
        "/api/v1/squares?bbox=10,44,11,44.5&target_date=2026-10-12",
        headers={"Host": "127.0.0.1"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "view_too_large"


@pytest.mark.django_db(transaction=True)
def test_info_and_forest_layer_routes_expose_contract_and_revalidate(
    map_fixture: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = map_fixture["build"]
    monkeypatch.setattr("map_api.api._today", lambda: MAP_DATE)
    cache.clear()

    with override_settings(MICOMETEO_FOREST_BUILD_VERSION=build.version):
        client = Client()
        info_response = client.get("/api/v1/info")
        assert info_response.status_code == 200
        info_body = info_response.json()
        assert info_body["today"] == MAP_DATE.isoformat()
        assert info_body["target_dates"] == [
            (MAP_DATE + timedelta(days=offset)).isoformat()
            for offset in range(MAX_DAYS_AHEAD + 1)
        ]
        assert "assessment_dates" not in info_body
        assert info_body["max_width_km"] == 60
        assert info_body["max_height_km"] == 60
        assert info_body["max_squares"] == 16_000
        assert info_body["forest_build_version"] == build.version

        plain_response = client.get("/api/v1/forest-layer")
        assert plain_response.status_code == 200
        assert plain_response["Cache-Control"] == "no-cache"
        assert plain_response["Vary"] == "Accept-Encoding"
        assert "Content-Encoding" not in plain_response
        plain_body = json.loads(plain_response.content)
        assert plain_body["type"] == "FeatureCollection"

        gzip_response = client.get(
            "/api/v1/forest-layer",
            HTTP_ACCEPT_ENCODING="gzip",
        )
        assert gzip_response.status_code == 200
        assert gzip_response["ETag"] == plain_response["ETag"]
        assert gzip_response["Content-Encoding"] == "gzip"
        assert gzip.decompress(gzip_response.content) == plain_response.content

        conditional_response = client.get(
            "/api/v1/forest-layer",
            HTTP_IF_NONE_MATCH=plain_response["ETag"],
        )
        assert conditional_response.status_code == 304
        assert conditional_response["ETag"] == plain_response["ETag"]
        assert conditional_response["Cache-Control"] == "no-cache"


@pytest.mark.django_db(transaction=True)
def test_info_target_dates_follow_an_explicit_clock_advance(
    map_fixture: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    build = map_fixture["build"]
    first_day = date(2026, 10, 12)
    next_day = first_day + timedelta(days=1)
    with override_settings(MICOMETEO_FOREST_BUILD_VERSION=build.version):
        monkeypatch.setattr("map_api.api._today", lambda: first_day)
        first_response = Client().get("/api/v1/info")
        monkeypatch.setattr("map_api.api._today", lambda: next_day)
        next_response = Client().get("/api/v1/info")

    assert first_response.status_code == 200
    assert next_response.status_code == 200
    assert first_response.json()["today"] == first_day.isoformat()
    assert next_response.json()["today"] == next_day.isoformat()
    assert first_response.json()["target_dates"][0] == first_day.isoformat()
    assert next_response.json()["target_dates"][0] == next_day.isoformat()


@pytest.mark.django_db(transaction=True)
def test_forest_layer_etag_changes_when_configured_completed_build_changes(
    map_fixture: dict[str, object],
    tmp_path: Path,
) -> None:
    build = map_fixture["build"]
    second_build = ForestBuild.objects.create(
        version=f"{build.version}-next",
        grid_build=build.grid_build,
        fingerprint="d" * 64,
        status=ForestBuild.Status.COMPLETED,
        planned_chunk_count=1,
        completed_chunk_count=1,
        cell_count=5,
        forest_cell_count=1,
        weather_cell_count=1,
    )
    second_data = _layer_metadata(
        path=tmp_path / "second-forest-layer.gz",
        rows=[
            {
                "corner_e": 4_300_000,
                "corner_n": 2_300_000,
                "forest_pixel_count": 75,
                "valid_pixel_count": 100,
                "is_forest": True,
            }
        ],
    )
    for field, value in second_data.items():
        setattr(second_build, field, value)
    second_build.save(update_fields=[*second_data, "updated_at"])

    with override_settings(MICOMETEO_FOREST_BUILD_VERSION=build.version):
        first_response = Client().get("/api/v1/forest-layer")
    with override_settings(MICOMETEO_FOREST_BUILD_VERSION=second_build.version):
        second_response = Client().get("/api/v1/forest-layer")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response["ETag"] != second_response["ETag"]
    assert first_response["Cache-Control"] == "no-cache"
    assert second_response["Cache-Control"] == "no-cache"
    assert first_response.content != second_response.content


@pytest.mark.django_db(transaction=True)
def test_squares_route_uses_newest_publication_and_preserves_all_square_states(
    map_fixture: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = map_fixture["build"]
    snapshot = map_fixture["snapshot"]
    new_update = map_fixture["new_update"]
    cells = map_fixture["cells"]
    requester_calls: list[dict[str, object]] = []

    def fake_request_weather(**kwargs: object) -> SimpleNamespace:
        requester_calls.append(kwargs)
        return SimpleNamespace(
            by_cell={
                "44.00,11.00": SimpleNamespace(
                    state="current",
                    assessment_date=MAP_DATE,
                    snapshot_id=str(snapshot.id),
                ),
                "44.10,11.10": SimpleNamespace(
                    state="not_available_yet",
                    assessment_date=None,
                    snapshot_id=None,
                ),
            }
        )

    monkeypatch.setattr("map_api.api._today", lambda: MAP_DATE)
    monkeypatch.setattr("map_api.api.weather_services.request_weather", fake_request_weather)
    cache.clear()

    with override_settings(MICOMETEO_FOREST_BUILD_VERSION=build.version):
        client = Client()
        url = f"/api/v1/squares?bbox={map_fixture['bbox']}&target_date={MAP_DATE.isoformat()}"
        response = client.get(url, REMOTE_ADDR="198.51.100.7")
        repeated_response = client.get(url, REMOTE_ADDR="198.51.100.7")

    assert response.status_code == 200
    assert repeated_response.status_code == 200
    assert response["Cache-Control"] == "no-cache"
    assert response["ETag"] == repeated_response["ETag"]
    assert len(requester_calls) == 2
    assert requester_calls[0]["visitor_id"] == "198.51.100.7"
    assert requester_calls[0]["assessment_date"] == MAP_DATE
    assert requester_calls[0]["wait_seconds"] == 3
    assert requester_calls[0]["forest_build_version"] == build.version

    features = response.json()["features"]
    assert response.json()["target_date"] == MAP_DATE.isoformat()
    assert response.json()["square_count"] == len(features)
    assert [feature["id"] for feature in features] == sorted(
        feature["id"] for feature in features
    )
    assert all(feature["geometry"]["type"] == "Polygon" for feature in features)
    by_cell_id = {feature["id"]: feature["properties"] for feature in features}
    assert by_cell_id[cells[0].grid_build_cell.cell.cell_id]["state"] == "available"
    assert by_cell_id[cells[0].grid_build_cell.cell.cell_id]["percentage"] == 0
    assert (
        by_cell_id[cells[0].grid_build_cell.cell.cell_id]["target_date"]
        == MAP_DATE.isoformat()
    )
    assert (
        by_cell_id[cells[0].grid_build_cell.cell.cell_id]["assessment_date"]
        == MAP_DATE.isoformat()
    )
    assert by_cell_id[cells[0].grid_build_cell.cell.cell_id]["update_id"] == str(
        new_update.public_id
    )
    assert by_cell_id[cells[0].grid_build_cell.cell.cell_id]["calculated_at"].startswith(
        "2026-10-12T09:00:00"
    )
    assert by_cell_id[cells[1].grid_build_cell.cell.cell_id]["state"] == "noforest"
    assert by_cell_id[cells[1].grid_build_cell.cell.cell_id]["percentage"] is None
    assert by_cell_id[cells[1].grid_build_cell.cell.cell_id]["update_id"] is None
    assert (
        by_cell_id[cells[2].grid_build_cell.cell.cell_id]["unavailable_reason"]
        == "missing_forest_data"
    )
    assert by_cell_id[cells[2].grid_build_cell.cell.cell_id]["update_id"] is None
    assert by_cell_id[cells[3].grid_build_cell.cell.cell_id]["state"] == "noresultyet"
    assert by_cell_id[cells[3].grid_build_cell.cell.cell_id]["unavailable_reason"] == "pending"
    assert by_cell_id[cells[3].grid_build_cell.cell.cell_id]["update_id"] is None
    assert (
        by_cell_id[cells[4].grid_build_cell.cell.cell_id]["unavailable_reason"]
        == "missing_forest_data"
    )
    assert by_cell_id[cells[4].grid_build_cell.cell.cell_id]["update_id"] is None


@pytest.mark.django_db(transaction=True)
def test_squares_route_uses_real_weather_service_and_reuses_provider_fetch(
    map_fixture: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = map_fixture["build"]
    snapshot = map_fixture["snapshot"]
    fake_transport = _MapFakeOpenMeteo()
    real_request_weather = weather_services.request_weather

    def request_weather_with_fake_transport(**kwargs: object) -> object:
        return real_request_weather(
            transport=fake_transport,
            clock=lambda: datetime(2026, 10, 12, 12, tzinfo=UTC),
            **kwargs,
        )

    monkeypatch.setattr("map_api.api._today", lambda: MAP_DATE)
    monkeypatch.setattr(
        "map_api.api.weather_services.request_weather",
        request_weather_with_fake_transport,
    )
    cache.clear()

    with override_settings(MICOMETEO_FOREST_BUILD_VERSION=build.version):
        client = Client()
        url = f"/api/v1/squares?bbox={map_fixture['bbox']}&target_date={MAP_DATE.isoformat()}"
        first_response = client.get(url, REMOTE_ADDR="198.51.100.8")
        deadline = monotonic() + 10
        while WeatherDaily.objects.count() < 29 and monotonic() < deadline:
            sleep(0.05)
        second_response = client.get(url, REMOTE_ADDR="198.51.100.8")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert fake_transport.call_count == 1
    assert WeatherRequest.objects.count() == 1
    assert WeatherRequestAttempt.objects.count() == 1
    assert WeatherDaily.objects.count() == 29
    assert WeatherSnapshot.objects.filter(
        cell_key="44.10,11.10",
        assessment_date=MAP_DATE,
    ).count() == 1
    assert first_response["ETag"] == second_response["ETag"]
    assert snapshot.cell_key == "44.00,11.00"



@pytest.mark.django_db(transaction=True)
def test_squares_cache_identity_changes_for_target_date_and_new_publication(
    map_fixture: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = map_fixture["build"]
    snapshot = map_fixture["snapshot"]
    cell = map_fixture["cells"][0]
    requester_calls: list[date] = []

    def fake_request_weather(**kwargs: object) -> SimpleNamespace:
        requester_calls.append(kwargs["assessment_date"])
        return SimpleNamespace(
            by_cell={
                "44.00,11.00": SimpleNamespace(
                    state="current",
                    assessment_date=MAP_DATE,
                    snapshot_id=str(snapshot.id),
                ),
                "44.10,11.10": SimpleNamespace(
                    state="not_available_yet",
                    assessment_date=None,
                    snapshot_id=None,
                ),
            }
        )

    monkeypatch.setattr("map_api.api._today", lambda: MAP_DATE)
    monkeypatch.setattr("map_api.api.weather_services.request_weather", fake_request_weather)
    cache.clear()

    with override_settings(MICOMETEO_FOREST_BUILD_VERSION=build.version):
        client = Client()
        current_url = f"/api/v1/squares?bbox={map_fixture['bbox']}&target_date={MAP_DATE.isoformat()}"
        next_url = (
            f"/api/v1/squares?bbox={map_fixture['bbox']}&target_date="
            f"{(MAP_DATE + timedelta(days=1)).isoformat()}"
        )
        current_response = client.get(current_url)
        next_response = client.get(next_url)
        EstimateResult.objects.create(
            update=EstimateUpdate.objects.create(
                cell_key=snapshot.cell_key,
                assessment_date=MAP_DATE,
                calculated_at=datetime(2026, 10, 12, 10, tzinfo=UTC),
                snapshot=snapshot,
                forest_build=build,
                terrain_build=map_fixture["new_update"].terrain_build,
                method_version="map-test-newer",
                row_count=1,
                input_fingerprint=sha256(b"newer-publication").hexdigest(),
            ),
            forest_cell=cell,
            values=bytes([77] * 8),
        )
        EstimateResult.objects.create(
            update=EstimateUpdate.objects.create(
                cell_key=snapshot.cell_key,
                assessment_date=MAP_DATE,
                calculated_at=datetime(2026, 10, 12, 10, tzinfo=UTC),
                snapshot=snapshot,
                forest_build=build,
                terrain_build=map_fixture["new_update"].terrain_build,
                method_version="map-test-newest-id",
                row_count=1,
                input_fingerprint=sha256(b"newest-id-publication").hexdigest(),
            ),
            forest_cell=cell,
            values=bytes([88] * 8),
        )
        published_response = client.get(current_url)

    assert current_response.status_code == 200
    assert next_response.status_code == 200
    assert published_response.status_code == 200
    assert current_response["ETag"] != next_response["ETag"]
    assert next_response.json()["features"][0]["properties"]["percentage"] == 42
    assert published_response["ETag"] != current_response["ETag"]
    assert published_response.json()["features"][0]["properties"]["percentage"] == 88
    assert requester_calls == [MAP_DATE, MAP_DATE, MAP_DATE]


@pytest.mark.django_db(transaction=True)
def test_squares_route_rejects_outside_coverage_before_weather_request(
    map_fixture: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = map_fixture["build"]
    weather_calls: list[object] = []

    def fail_if_called(**kwargs: object) -> None:
        weather_calls.append(kwargs)
        raise AssertionError("outside views must not request weather")

    monkeypatch.setattr("map_api.api._today", lambda: MAP_DATE)
    monkeypatch.setattr("map_api.api.weather_services.request_weather", fail_if_called)

    with override_settings(MICOMETEO_FOREST_BUILD_VERSION=build.version):
        response = Client().get(
            f"/api/v1/squares?bbox=0,0,0.01,0.01&target_date={MAP_DATE.isoformat()}"
        )

    assert response.status_code == 400
    assert response.json()["code"] == "outside_coverage"
    assert weather_calls == []


@pytest.mark.django_db(transaction=True)
def test_squares_route_rejects_target_date_after_the_eight_supported_dates(
    map_fixture: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = map_fixture["build"]
    weather_calls: list[object] = []

    def fail_if_called(**kwargs: object) -> None:
        weather_calls.append(kwargs)
        raise AssertionError("unsupported dates must not request weather")

    monkeypatch.setattr("map_api.api._today", lambda: MAP_DATE)
    monkeypatch.setattr("map_api.api.weather_services.request_weather", fail_if_called)

    with override_settings(MICOMETEO_FOREST_BUILD_VERSION=build.version):
        response = Client().get(
            f"/api/v1/squares?bbox={map_fixture['bbox']}&target_date="
            f"{(MAP_DATE + timedelta(days=8)).isoformat()}"
        )

    assert response.status_code == 400
    assert response.json()["code"] == "unsupported_date"
    assert weather_calls == []


@pytest.mark.django_db(transaction=True)
def test_forest_layer_returns_stable_error_for_a_hash_mismatch(
    map_fixture: dict[str, object],
) -> None:
    build = map_fixture["build"]
    build.layer_sha256 = "0" * 64
    build.save(update_fields=["layer_sha256", "updated_at"])

    with override_settings(MICOMETEO_FOREST_BUILD_VERSION=build.version):
        response = Client().get("/api/v1/forest-layer")

    assert response.status_code == 503
    assert response.json()["code"] == "forest_layer_unavailable"


@pytest.mark.django_db(transaction=True)
def test_squares_route_marks_previous_weather_outside_range_as_expired(
    map_fixture: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = map_fixture["build"]
    cell = map_fixture["cells"][0]
    terrain = map_fixture["new_update"].terrain_build
    previous_date = MAP_DATE - timedelta(days=11)
    previous_snapshot = WeatherSnapshot.objects.create(
        cell_key="44.00,11.00",
        assessment_date=previous_date,
        latest_retrieval=datetime(2026, 10, 1, 10, tzinfo=UTC),
        source_ids=["map:previous"],
        source_attempt_ids=["map:previous-attempt"],
    )
    previous_update = EstimateUpdate.objects.create(
        cell_key=previous_snapshot.cell_key,
        assessment_date=previous_date,
        calculated_at=datetime(2026, 10, 1, 11, tzinfo=UTC),
        snapshot=previous_snapshot,
        forest_build=build,
        terrain_build=terrain,
        method_version="map-test-previous",
        row_count=1,
        input_fingerprint=sha256(b"previous-publication").hexdigest(),
    )
    EstimateResult.objects.create(
        update=previous_update,
        forest_cell=cell,
        values=bytes([25] * 8),
    )

    def fake_request_weather(**kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            by_cell={
                "44.00,11.00": SimpleNamespace(
                    state="previous",
                    assessment_date=previous_date,
                    snapshot_id=str(previous_snapshot.id),
                ),
                "44.10,11.10": SimpleNamespace(
                    state="not_available_yet",
                    assessment_date=None,
                    snapshot_id=None,
                ),
            }
        )

    monkeypatch.setattr("map_api.api._today", lambda: MAP_DATE)
    monkeypatch.setattr("map_api.api.weather_services.request_weather", fake_request_weather)
    cache.clear()

    with override_settings(MICOMETEO_FOREST_BUILD_VERSION=build.version):
        response = Client().get(
            f"/api/v1/squares?bbox={map_fixture['bbox']}&target_date={MAP_DATE.isoformat()}"
        )

    assert response.status_code == 200
    properties = response.json()["features"][0]["properties"]
    assert properties["state"] == "expired"
    assert properties["unavailable_reason"] == "target_outside_update_range"
    assert properties["update_id"] == str(previous_update.public_id)
    assert properties["assessment_date"] == previous_date.isoformat()
