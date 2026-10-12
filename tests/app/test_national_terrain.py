"""Offline checks for bounded terrain calculations and source provenance."""

import io
import importlib
import json
import math
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from micometeo.habitat import terrain
from national_terrain import source


def _window(*, east: int = 1_000, north: int = 500) -> terrain.ProcessingWindow:
    return terrain.ProcessingWindow(
        west_e=4_300_000,
        south_n=2_300_000,
        east_e=4_300_000 + east,
        north_n=2_300_000 + north,
    )


def _plane(*, window: terrain.ProcessingWindow, rise_east: float, rise_north: float) -> np.ndarray:
    rows, columns = window.expanded_shape
    east = (
        window.expanded_west_e - 4_300_000
        + np.arange(columns, dtype="float32") * terrain.PROCESSING_PIXEL_M
    )
    north = (
        window.expanded_south_n - 2_300_000
        + np.arange(rows, dtype="float32") * terrain.PROCESSING_PIXEL_M
    )
    return 1_000 + east[None, :] * rise_east + north[:, None] * rise_north


def test_processing_window_keeps_elevation_in_metres_and_slope_direction() -> None:
    window = _window()
    values = _plane(window=window, rise_east=0.1, rise_north=-0.2)
    rows = terrain.summarise_processing_window(altitude=values, window=window)
    assert rows[0]["altitude_m"] == pytest.approx(976.2, abs=0.1)
    assert rows[0]["slope_deg"] == pytest.approx(12.6, abs=0.1)
    assert rows[0]["aspect_deg"] == pytest.approx(206.6, abs=0.2)


def test_processing_window_flat_ground_has_null_direction() -> None:
    window = _window()
    rows = terrain.summarise_processing_window(
        altitude=np.full(window.expanded_shape, 800.0, dtype="float32"), window=window
    )
    assert rows[0]["slope_deg"] == pytest.approx(0.0)
    assert rows[0]["aspect_deg"] is None


def test_reprojection_interpolates_source_plane_at_destination_pixel_centre() -> None:
    window = _window(east=500, north=500)
    source_transform = from_origin(
        window.expanded_west_e - 60,
        window.expanded_north_n + 60,
        30,
        30,
    )
    source_columns = 30
    source_rows = 30
    source_eastings = source_transform.c + (
        np.arange(source_columns, dtype="float64") + 0.5
    ) * 30
    source_northings = source_transform.f - (
        np.arange(source_rows, dtype="float64") + 0.5
    ) * 30
    source_values = (
        100.0
        + 0.01 * source_eastings[None, :]
        + 0.02 * source_northings[:, None]
    ).astype("float32")
    altitude = terrain.reproject_mosaic_to_window(
        mosaic=source_values,
        source_transform=source_transform,
        source_crs="EPSG:3035",
        source_nodata=None,
        window=window,
    )
    row = window.margin_pixels + 5
    column = window.margin_pixels + 7
    destination_easting = window.expanded_west_e + (column + 0.5) * 25
    destination_northing = window.expanded_north_n - (row + 0.5) * 25
    expected = 100.0 + 0.01 * destination_easting + 0.02 * destination_northing
    assert altitude[row, column] == pytest.approx(expected, abs=0.0001)


def test_processing_window_circular_direction_and_quality_thresholds() -> None:
    window = _window()
    values = _plane(window=window, rise_east=0.0, rise_north=0.02)
    rows = terrain.summarise_processing_window(altitude=values, window=window)
    assert rows[0]["aspect_deg"] is None
    assert rows[0]["aspect_deg_reliability"] == "low"
    assert terrain.coverage_reliability(valid_share=0.95) == "high"
    assert terrain.coverage_reliability(valid_share=0.5) == "low"
    assert terrain.coverage_reliability(valid_share=0.49) is None
    direction, resultant = terrain.circular_mean(degrees=np.array([359.0, 1.0]))
    assert min(direction, 360 - direction) == pytest.approx(0.0, abs=0.01)
    assert resultant == pytest.approx(math.cos(math.radians(1.0)))


def test_opposing_directions_keep_low_quality() -> None:
    window = _window(east=500, north=500)
    grid = terrain.SampleGrid(
        west_e=window.west_e,
        south_n=window.south_n,
        east_e=window.east_e,
        north_n=window.north_n,
    )
    altitude = np.full(grid.pixel_shape, 800.0, dtype="float32")
    slope = np.full(grid.pixel_shape, 10.0, dtype="float32")
    aspect = np.full(grid.pixel_shape, 90.0, dtype="float32")
    aspect[:, aspect.shape[1] // 2 :] = 270.0
    row = terrain.summarise_terrain_arrays(
        altitude=altitude,
        slope=slope,
        aspect=aspect,
        grid=grid,
        settings={"flat_slope_deg": 5.0, "min_resultant_length": 0.3},
    )[0]
    assert row["aspect_deg_reliability"] == "low"


def test_circular_direction_rounding_normalises_north_to_zero() -> None:
    window = _window(east=500, north=500)
    grid = terrain.SampleGrid(
        west_e=window.west_e,
        south_n=window.south_n,
        east_e=window.east_e,
        north_n=window.north_n,
    )
    row = terrain.summarise_terrain_arrays(
        altitude=np.full(grid.pixel_shape, 800.0, dtype="float32"),
        slope=np.full(grid.pixel_shape, 10.0, dtype="float32"),
        aspect=np.full(grid.pixel_shape, 359.99, dtype="float32"),
        grid=grid,
        settings={"flat_slope_deg": 5.0, "min_resultant_length": 0.3},
    )[0]
    assert row["aspect_deg"] == 0.0
    assert 0.0 <= row["aspect_deg"] < 360.0


def test_processing_margin_makes_adjacent_chunks_match_one_window() -> None:
    full = _window(east=1_000, north=500)
    all_rows = terrain.summarise_processing_window(
        altitude=_plane(window=full, rise_east=0.1, rise_north=0.05), window=full
    )
    left = _window(east=500, north=500)
    right = terrain.ProcessingWindow(
        west_e=4_300_500,
        south_n=2_300_000,
        east_e=4_301_000,
        north_n=2_300_500,
    )
    left_values = _plane(window=left, rise_east=0.1, rise_north=0.05)
    right_values = _plane(window=right, rise_east=0.1, rise_north=0.05)
    chunk_rows = terrain.summarise_processing_window(altitude=left_values, window=left)
    chunk_rows.extend(
        terrain.summarise_processing_window(altitude=right_values, window=right)
    )
    assert [row["altitude_m"] for row in chunk_rows] == pytest.approx(
        [row["altitude_m"] for row in all_rows]
    )
    assert [row["slope_deg"] for row in chunk_rows] == pytest.approx(
        [row["slope_deg"] for row in all_rows]
    )
    assert [row["aspect_deg"] for row in chunk_rows] == pytest.approx(
        [row["aspect_deg"] for row in all_rows]
    )


def _write_native_source_tiles(
    *,
    directory: Path,
    window: terrain.ProcessingWindow,
    source_nodata: float = terrain.NODATA,
    include_nodata_pixel: bool = False,
) -> list[Path]:
    bounds = terrain.source_bounds_for_window(window=window)
    west_arcseconds = math.floor(bounds[0] * 3600) - 2
    south_arcseconds = math.floor(bounds[1] * 3600) - 2
    east_arcseconds = math.ceil(bounds[2] * 3600) + 2
    north_arcseconds = math.ceil(bounds[3] * 3600) + 2
    width = east_arcseconds - west_arcseconds
    height = north_arcseconds - south_arcseconds
    split = width // 2
    x = west_arcseconds + np.arange(width, dtype="float32") + 0.5
    y = north_arcseconds - np.arange(height, dtype="float32") - 0.5
    values = (
        900.0
        + 0.7 * (x[None, :] - west_arcseconds)
        + 0.5 * (y[:, None] - south_arcseconds)
        + 150.0 * np.sin(x[None, :] / 40.0)
        + 100.0 * np.cos(y[:, None] / 45.0)
    ).astype("float32")
    if include_nodata_pixel:
        values[
            height // 2 - 10 : height // 2 + 10,
            width // 2 - 10 : width // 2 + 10,
        ] = source_nodata
    paths: list[Path] = []
    for name, start, stop in (("west", 0, split), ("east", split, width)):
        path = directory / f"{name}.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=height,
            width=stop - start,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(
                (west_arcseconds + start) / 3600,
                north_arcseconds / 3600,
                1 / 3600,
                1 / 3600,
            ),
            nodata=source_nodata,
        ) as target:
            target.write(values[:, start:stop], 1)
        paths.append(path)
    return paths


def test_native_mosaic_has_same_terrain_for_combined_and_adjacent_windows(
    tmp_path: Path,
) -> None:
    to_laea = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
    easting, northing = to_laea.transform(12.0, 42.0)
    west = math.floor(easting / 500) * 500
    south = math.floor(northing / 500) * 500
    combined_window = terrain.ProcessingWindow(
        west_e=west,
        south_n=south,
        east_e=west + 50_000,
        north_n=south + 25_000,
    )
    left_window = terrain.ProcessingWindow(
        west_e=west,
        south_n=south,
        east_e=west + 25_000,
        north_n=south + 25_000,
    )
    right_window = terrain.ProcessingWindow(
        west_e=west + 25_000,
        south_n=south,
        east_e=west + 50_000,
        north_n=south + 25_000,
    )
    paths = _write_native_source_tiles(directory=tmp_path, window=combined_window)

    def summarise(*, window: terrain.ProcessingWindow) -> list[dict[str, object]]:
        mosaic, transform, crs, nodata = terrain.mosaic_source_tiles(
            tile_paths=paths,
            bounds=terrain.source_bounds_for_window(window=window),
        )
        altitude = terrain.reproject_mosaic_to_window(
            mosaic=mosaic,
            source_transform=transform,
            source_crs=crs,
            source_nodata=nodata,
            window=window,
        )
        return terrain.summarise_processing_window(altitude=altitude, window=window)

    combined = summarise(window=combined_window)
    left = summarise(window=left_window)
    right = summarise(window=right_window)
    left_columns = terrain.SampleGrid(
        west_e=left_window.west_e,
        south_n=left_window.south_n,
        east_e=left_window.east_e,
        north_n=left_window.north_n,
    ).columns
    combined_rows = terrain.SampleGrid(
        west_e=combined_window.west_e,
        south_n=combined_window.south_n,
        east_e=combined_window.east_e,
        north_n=combined_window.north_n,
    ).rows
    adjacent: list[dict[str, object]] = []
    for row in range(combined_rows):
        adjacent.extend(left[row * left_columns : (row + 1) * left_columns])
        adjacent.extend(right[row * left_columns : (row + 1) * left_columns])
    assert len(combined) == len(adjacent) == 5_000
    for combined_row, adjacent_row in zip(combined, adjacent):
        for column in ("altitude_m", "slope_deg", "aspect_deg"):
            if combined_row[column] is None:
                assert adjacent_row[column] is None
            else:
                assert combined_row[column] == adjacent_row[column]
        for column in (
            "altitude_m_reliability",
            "altitude_m_valid_fraction",
            "slope_deg_reliability",
            "slope_deg_valid_fraction",
            "aspect_deg_reliability",
            "aspect_deg_valid_fraction",
            "source_gap",
            "altitude_m_source",
            "slope_deg_source",
            "aspect_deg_source",
        ):
            assert combined_row[column] == adjacent_row[column]


def test_nondefault_source_nodata_becomes_mosaic_nodata_and_stays_missing(
    tmp_path: Path,
) -> None:
    to_laea = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
    easting, northing = to_laea.transform(12.0, 42.0)
    window = terrain.ProcessingWindow(
        west_e=math.floor(easting / 500) * 500,
        south_n=math.floor(northing / 500) * 500,
        east_e=math.floor(easting / 500) * 500 + 50_000,
        north_n=math.floor(northing / 500) * 500 + 25_000,
    )
    paths = _write_native_source_tiles(
        directory=tmp_path,
        window=window,
        source_nodata=-9999.0,
        include_nodata_pixel=True,
    )
    mosaic, transform, crs, nodata = terrain.mosaic_source_tiles(
        tile_paths=paths,
        bounds=terrain.source_bounds_for_window(window=window),
    )
    assert nodata == terrain.NODATA
    assert np.count_nonzero(mosaic == terrain.NODATA) > 0
    altitude = terrain.reproject_mosaic_to_window(
        mosaic=mosaic,
        source_transform=transform,
        source_crs=crs,
        source_nodata=nodata,
        window=window,
    )
    rows = terrain.summarise_processing_window(altitude=altitude, window=window)
    assert any(row["source_gap"] for row in rows)
    assert all(row["altitude_m"] != 0.0 for row in rows if row["altitude_m"] is not None)


def test_missing_pixels_remain_null_and_report_fraction() -> None:
    window = _window()
    values = _plane(window=window, rise_east=0.1, rise_north=0.0)
    values[1:21, 1:21] = np.nan
    rows = terrain.summarise_processing_window(altitude=values, window=window)
    assert rows[0]["altitude_m"] is None
    assert rows[0]["slope_deg"] is None
    assert rows[0]["source_gap"] is True
    assert rows[0]["altitude_m_valid_fraction"] == pytest.approx(0.0)


def test_source_edge_nodata_is_a_gap_and_never_becomes_zero() -> None:
    window = _window(east=500, north=500)
    values = _plane(window=window, rise_east=0.1, rise_north=0.0)
    values[:, -2] = np.nan
    row = terrain.summarise_processing_window(altitude=values, window=window)[0]
    assert row["source_gap"] is True
    assert row["altitude_m"] != 0.0
    assert row["altitude_m_valid_fraction"] == pytest.approx(0.95)


class _Response:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self._body = io.BytesIO(body)
        self.headers = headers or {}

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        self._body.close()

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)


def _raster_bytes(
    *,
    path: Path,
    crs: str = "EPSG:4326",
    width: int = 3_600,
    height: int = 3_600,
    pixel_size: float = 1 / 3_600,
    transform: Any | None = None,
    nodata: float | None = None,
    area_or_point: str = "Point",
) -> bytes:
    values = np.ones((height, width), dtype="float32")
    if transform is None:
        transform = from_origin(
            10.0 - pixel_size / 2,
            46.0 + pixel_size / 2,
            pixel_size,
            pixel_size,
        )
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=nodata,
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as target:
        target.write(values, 1)
        target.update_tags(AREA_OR_POINT=area_or_point)
    data = path.read_bytes()
    path.unlink()
    return data


def _confirmed_missing_tile(*, tile_name: str, cache_dir: Path) -> source.CachedTile:
    return source.CachedTile(
        tile_name=tile_name,
        path=None,
        status="confirmed_missing",
        metadata={
            "tile_name": tile_name,
            "status": "confirmed_missing",
            "url": "https://example.invalid/tile.tif",
            "release": terrain.SOURCE_RELEASE,
            "crs": terrain.SOURCE_CRS,
            "native_pixel_m": terrain.SOURCE_NATIVE_PIXEL_M,
            "vertical_datum": terrain.SOURCE_VERTICAL_DATUM,
            "credit": terrain.LICENCE,
        },
        reused=True,
    )


def test_source_credit_contains_required_copernicus_liability_notice() -> None:
    required = (
        "The organisations in charge of the Copernicus programme by law or by delegation do not "
        "incur any liability for any use of the Copernicus WorldDEM-30"
    )
    assert required in terrain.LICENCE


def test_cache_reuses_checksum_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = _raster_bytes(path=tmp_path / "fixture.tif")
    calls = []

    def open_once(*args: object, **kwargs: object) -> _Response:
        calls.append(args)
        return _Response(body=body, headers={"Last-Modified": "2021"})

    monkeypatch.setattr(source.urllib.request, "urlopen", open_once)
    first = source.cache_tile(tile_name="N45_00_E010_00", cache_dir=tmp_path)
    monkeypatch.setattr(
        source.urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("cache hit made a network request"),
    )
    second = source.cache_tile(tile_name="N45_00_E010_00", cache_dir=tmp_path)
    assert first.reused is False
    assert second.reused is True
    assert len(calls) == 1
    assert second.metadata["release"] == terrain.SOURCE_RELEASE
    assert second.metadata["crs"] == "EPSG:4326"
    assert second.metadata["raster_width"] == 3_600
    assert second.metadata["raster_height"] == 3_600
    assert second.metadata["raster_dtype"] == "float32"
    assert second.metadata["raster_nodata"] is None
    assert second.metadata["area_or_point"] == "Point"
    assert second.metadata["vertical_datum"] == "EGM2008"
    assert second.metadata["sha256"] == source.sha256_path(path=second.path)


def test_cache_serializes_same_tile_first_fetches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _raster_bytes(path=tmp_path / "fixture.tif")
    calls = 0
    calls_lock = Lock()

    def open_once(*args: object, **kwargs: object) -> _Response:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.1)
        return _Response(body=body, headers={"Last-Modified": "2021"})

    monkeypatch.setattr(source.urllib.request, "urlopen", open_once)

    def fetch(_: int) -> source.CachedTile:
        return source.cache_tile(tile_name="N45_00_E010_00", cache_dir=tmp_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(fetch, range(2)))

    assert calls == 1
    assert sorted(result.reused for result in results) == [False, True]
    assert results[0].metadata == results[1].metadata
    assert results[0].path == results[1].path


@pytest.mark.parametrize(
    ("raster_kwargs", "error_fragment"),
    [
        ({"crs": "EPSG:3035"}, "EPSG:4326"),
        (
            {
                "transform": from_origin(
                    10.0 - (1 / 3_600) / 2 + 1 / 3_600,
                    46.0 + (1 / 3_600) / 2,
                    1 / 3_600,
                    1 / 3_600,
                )
            },
            "unexpected one-arcsecond transform",
        ),
        ({"width": 3_599}, "3600 by 3600"),
        ({"pixel_size": 1 / 1_800}, "unexpected one-arcsecond transform"),
    ],
)
def test_cache_rejects_raster_that_is_not_a_public_glo30_tile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raster_kwargs: dict[str, Any],
    error_fragment: str,
) -> None:
    body = _raster_bytes(path=tmp_path / "fixture.tif", **raster_kwargs)

    monkeypatch.setattr(
        source.urllib.request,
        "urlopen",
        lambda *args, **kwargs: _Response(body=body, headers={"Last-Modified": "2021"}),
    )
    with pytest.raises(source.TerrainSourceError, match=error_fragment):
        source.cache_tile(tile_name="N45_00_E010_00", cache_dir=tmp_path)
    metadata = json.loads(
        source.sidecar_path(cache_dir=tmp_path, tile_name="N45_00_E010_00").read_text()
    )
    assert metadata["status"] == "failed"
    assert error_fragment in metadata["error"]


def test_reused_legacy_sidecar_credit_is_overridden_for_build_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from national_terrain import services

    tile_name = "N45_00_E010_00"
    raster = source.raster_path(cache_dir=tmp_path, tile_name=tile_name)
    raster.write_bytes(_raster_bytes(path=tmp_path / "fixture.tif"))
    metadata = {
        "tile_name": tile_name,
        "status": "available",
        "url": "https://example.invalid/tile.tif",
        "release": terrain.SOURCE_RELEASE,
        "last_modified": "2021",
        "retrieved_at": "2021-01-01T00:00:00+00:00",
        "size_bytes": raster.stat().st_size,
        "sha256": source.sha256_path(path=raster),
        "crs": terrain.SOURCE_CRS,
        "native_pixel_m": terrain.SOURCE_NATIVE_PIXEL_M,
        "vertical_datum": terrain.SOURCE_VERTICAL_DATUM,
        "credit": "legacy source credit without the current notice",
    }
    source.sidecar_path(cache_dir=tmp_path, tile_name=tile_name).write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    monkeypatch.setattr(
        source.urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("legacy cache hit made a network request"),
    )

    cached = source.cache_tile(tile_name=tile_name, cache_dir=tmp_path)
    assert cached.reused is True
    assert cached.metadata["credit"] != terrain.LICENCE
    assert services._source_tile_defaults(item=cached)["credit"] == terrain.LICENCE


def test_cache_distinguishes_confirmed_missing_from_transient_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError("url", 404, "missing", {}, None)

    monkeypatch.setattr(source.urllib.request, "urlopen", missing)
    result = source.cache_tile(tile_name="N45_00_E011_00", cache_dir=tmp_path)
    assert result.status == "confirmed_missing"
    assert result.path is None
    assert json.loads((tmp_path / "N45_00_E011_00.json").read_text())["status"] == "confirmed_missing"

    def transient(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("timeout")

    monkeypatch.setattr(source.urllib.request, "urlopen", transient)
    with pytest.raises(source.TerrainSourceError):
        source.cache_tile(tile_name="N45_00_E012_00", cache_dir=tmp_path)
    failed_metadata = json.loads(
        (tmp_path / "N45_00_E012_00.json").read_text()
    )
    assert failed_metadata["status"] == "failed"
    assert failed_metadata["credit"] == terrain.LICENCE


def test_build_command_preserves_running_status_for_partial_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from django.core.management import call_command

    command_module = importlib.import_module(
        "national_terrain.management.commands.build_national_terrain"
    )

    class PartialResult:
        status = "running"

        def as_dict(self) -> dict[str, str]:
            return {"status": self.status}

    monkeypatch.setattr(
        command_module,
        "build_national_terrain",
        lambda **kwargs: PartialResult(),
    )
    output = io.StringIO()
    call_command(
        "build_national_terrain",
        grid_build_version="grid-v2",
        build_version="terrain-v2",
        cache_dir=tmp_path,
        max_chunks=1,
        stdout=output,
    )
    assert json.loads(output.getvalue())["status"] == "running"


def _completed_grid_build(*, version: str, chunk_count: int = 1):
    from django.contrib.gis.geos import MultiPolygon, Polygon

    from national_grid.models import GridBuild, GridBuildCell, GridCell, GridChunk, GridRegion

    build = GridBuild.objects.create(
        version=version,
        fingerprint="a" * 64,
        status=GridBuild.Status.COMPLETED,
        planned_chunk_count=chunk_count,
        completed_chunk_count=chunk_count,
        cell_count=chunk_count,
    )
    region = GridRegion.objects.create(
        build=build,
        istat_code="01",
        name="Synthetic region",
        geometry=MultiPolygon(
            [Polygon.from_bbox((4_300_000, 2_300_000, 4_300_000 + chunk_count * 500, 2_300_500))],
            srid=3035,
        ),
    )
    for index in range(chunk_count):
        west = 4_300_000 + index * 500
        chunk = GridChunk.objects.create(
            build=build,
            west_e=west,
            south_n=2_300_000,
            east_e=west + 500,
            north_n=2_300_500,
            status=GridChunk.Status.COMPLETED,
            cell_count=1,
        )

        cell = GridCell.objects.create(
            cell_id=f"500m_E{west}_N2300000",
            corner_e=west,
            corner_n=2_300_000,
            geometry=Polygon.from_bbox((west, 2_300_000, west + 500, 2_300_500)),
        )
        GridBuildCell.objects.create(
            build=build,
            cell=cell,
            chunk=chunk,
            owner_region=region,
            land_geometry=MultiPolygon(
                [Polygon.from_bbox((west, 2_300_000, west + 500, 2_300_500))], srid=3035
            ),
            land_share=1.0,
        )
    return build


def _sparse_completed_grid_build(*, version: str, member_count: int = 31):
    from django.contrib.gis.geos import MultiPolygon, Polygon

    from national_grid.models import GridBuild, GridBuildCell, GridCell, GridChunk, GridRegion

    west = 4_300_000
    south = 2_300_000
    chunk_size = 25_000
    build = GridBuild.objects.create(
        version=version,
        fingerprint="d" * 64,
        status=GridBuild.Status.COMPLETED,
        planned_chunk_count=1,
        completed_chunk_count=1,
        cell_count=member_count,
        chunk_size_m=chunk_size,
    )
    region = GridRegion.objects.create(
        build=build,
        istat_code="01",
        name="Sparse synthetic region",
        geometry=MultiPolygon(
            [Polygon.from_bbox((west, south, west + chunk_size, south + chunk_size))],
            srid=3035,
        ),
    )
    chunk = GridChunk.objects.create(
        build=build,
        west_e=west,
        south_n=south,
        east_e=west + chunk_size,
        north_n=south + chunk_size,
        status=GridChunk.Status.COMPLETED,
        cell_count=member_count,
    )
    for index in range(member_count):
        corner_e = west + index * 500
        cell = GridCell.objects.create(
            cell_id=f"500m_E{corner_e}_N{south}",
            corner_e=corner_e,
            corner_n=south,
            geometry=Polygon.from_bbox((corner_e, south, corner_e + 500, south + 500)),
        )
        GridBuildCell.objects.create(
            build=build,
            cell=cell,
            chunk=chunk,
            owner_region=region,
            land_geometry=MultiPolygon(
                [Polygon.from_bbox((corner_e, south, corner_e + 500, south + 500))],
                srid=3035,
            ),
            land_share=1.0,
        )
    return build


@pytest.mark.django_db(transaction=True)
def test_terrain_build_rejects_incomplete_grid(tmp_path: Path) -> None:
    from national_grid.models import GridBuild
    from national_terrain.services import IncompleteGridBuildError, build_national_terrain

    GridBuild.objects.create(version="unfinished-grid", fingerprint="b" * 64)
    with pytest.raises(IncompleteGridBuildError):
        build_national_terrain(
            grid_build_version="unfinished-grid",
            build_version="terrain-v1",
            cache_dir=tmp_path,
        )


@pytest.mark.django_db(transaction=True)
def test_terrain_build_stores_missing_cells_and_reuses_completed_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from national_terrain import services
    from national_terrain.models import TerrainCell, TerrainSourceTile

    grid_build = _completed_grid_build(version="grid-missing-v1")

    monkeypatch.setattr(services, "cache_tile", _confirmed_missing_tile)
    first = services.build_national_terrain(
        grid_build_version=grid_build.version,
        build_version="terrain-missing-v1",
        cache_dir=tmp_path,
    )
    assert first.status == "completed"
    assert TerrainCell.objects.filter(build=first.build, source_gap=True).count() == 1
    assert TerrainCell.objects.get(build=first.build).altitude_m is None
    assert TerrainSourceTile.objects.filter(build=first.build, status="confirmed_missing").exists()

    monkeypatch.setattr(services, "cache_tile", lambda **kwargs: pytest.fail("network used"))
    second = services.build_national_terrain(
        grid_build_version=grid_build.version,
        build_version="terrain-missing-v1",
        cache_dir=tmp_path,
    )
    assert second.status == "completed"
    assert second.processed_chunks == 0
    assert TerrainCell.objects.filter(build=second.build).count() == 1


@pytest.mark.django_db(transaction=True)
def test_failed_source_retry_as_confirmed_missing_completes_with_matching_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from national_terrain import services
    from national_terrain.models import TerrainCell, TerrainSourceTile

    grid_build = _completed_grid_build(version="grid-failed-missing-v1")

    def transient_failure(*, tile_name: str, cache_dir: Path) -> source.CachedTile:
        raise source.TerrainSourceError("temporary source failure")

    monkeypatch.setattr(services, "cache_tile", transient_failure)
    with pytest.raises(source.TerrainSourceError):
        services.build_national_terrain(
            grid_build_version=grid_build.version,
            build_version="terrain-failed-missing-v1",
            cache_dir=tmp_path,
        )
    failed = TerrainSourceTile.objects.get(build__version="terrain-failed-missing-v1")
    assert failed.status == TerrainSourceTile.Status.FAILED

    monkeypatch.setattr(services, "cache_tile", _confirmed_missing_tile)
    result = services.build_national_terrain(
        grid_build_version=grid_build.version,
        build_version="terrain-failed-missing-v1",
        cache_dir=tmp_path,
    )
    assert result.status == "completed"
    recorded = TerrainSourceTile.objects.get(build=result.build)
    assert recorded.status == TerrainSourceTile.Status.CONFIRMED_MISSING
    assert recorded.error_detail == ""
    cell = TerrainCell.objects.get(build=result.build)
    assert cell.source_gap is True
    assert cell.altitude_m is None


@pytest.mark.django_db(transaction=True)
def test_reused_source_metadata_uses_current_credit_on_build_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from national_terrain import services
    from national_terrain.models import TerrainSourceTile

    grid_build = _completed_grid_build(version="grid-credit-v2")
    old_credit = "legacy source credit without the current notice"
    summary = {
        "altitude_m": 800.0,
        "slope_deg": 10.0,
        "aspect_deg": 180.0,
        "altitude_m_valid_fraction": 1.0,
        "slope_deg_valid_fraction": 1.0,
        "aspect_deg_valid_fraction": 1.0,
        "altitude_m_reliability": "high",
        "slope_deg_reliability": "high",
        "aspect_deg_reliability": "high",
        "source_gap": False,
    }

    def reused_tile(*, tile_name: str, cache_dir: Path) -> source.CachedTile:
        return source.CachedTile(
            tile_name=tile_name,
            path=cache_dir / "reused.tif",
            status="available",
            metadata={
                "tile_name": tile_name,
                "status": "available",
                "url": "https://example.invalid/tile.tif",
                "release": terrain.SOURCE_RELEASE,
                "last_modified": "2021",
                "retrieved_at": "2026-01-01T00:00:00+00:00",
                "size_bytes": 1,
                "sha256": "a" * 64,
                "crs": terrain.SOURCE_CRS,
                "native_pixel_m": terrain.SOURCE_NATIVE_PIXEL_M,
                "vertical_datum": terrain.SOURCE_VERTICAL_DATUM,
                "credit": old_credit,
            },
            reused=True,
        )

    monkeypatch.setattr(services, "cache_tile", reused_tile)
    monkeypatch.setattr(services, "_summaries", lambda **kwargs: [summary])
    result = services.build_national_terrain(
        grid_build_version=grid_build.version,
        build_version="terrain-credit-v2",
        cache_dir=tmp_path,
    )

    assert result.status == "completed"
    assert result.build.source_metadata["credit"] == terrain.LICENCE
    records = TerrainSourceTile.objects.filter(build=result.build)
    assert records.exists()
    assert all(record.credit == terrain.LICENCE for record in records)
    assert all(record.credit != old_credit for record in records)


@pytest.mark.django_db(transaction=True)
def test_normalised_north_aspect_satisfies_postgres_constraint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from national_terrain import services
    from national_terrain.models import TerrainCell

    grid_build = _completed_grid_build(version="grid-aspect-v1")
    window = _window(east=500, north=500)
    grid = terrain.SampleGrid(
        west_e=window.west_e,
        south_n=window.south_n,
        east_e=window.east_e,
        north_n=window.north_n,
    )
    summary = terrain.summarise_terrain_arrays(
        altitude=np.full(grid.pixel_shape, 800.0, dtype="float32"),
        slope=np.full(grid.pixel_shape, 10.0, dtype="float32"),
        aspect=np.full(grid.pixel_shape, 359.99, dtype="float32"),
        grid=grid,
        settings={"flat_slope_deg": 5.0, "min_resultant_length": 0.3},
    )
    monkeypatch.setattr(services, "cache_tile", _confirmed_missing_tile)
    monkeypatch.setattr(services, "_summaries", lambda **kwargs: summary)
    result = services.build_national_terrain(
        grid_build_version=grid_build.version,
        build_version="terrain-aspect-v1",
        cache_dir=tmp_path,
    )
    assert result.status == "completed"
    stored = TerrainCell.objects.get(build=result.build)
    assert stored.aspect_deg == 0.0
    assert stored.aspect_deg < 360.0


@pytest.mark.django_db(transaction=True)
def test_terrain_build_stores_only_sparse_grid_memberships_in_large_chunk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from national_terrain import services
    from national_terrain.models import TerrainCell

    grid_build = _sparse_completed_grid_build(version="grid-sparse-v1", member_count=31)

    monkeypatch.setattr(services, "cache_tile", _confirmed_missing_tile)
    result = services.build_national_terrain(
        grid_build_version=grid_build.version,
        build_version="terrain-sparse-v1",
        cache_dir=tmp_path,
    )
    assert result.status == "completed"
    assert result.build.result_count == 31
    assert TerrainCell.objects.filter(build=result.build).count() == 31
    assert TerrainCell.objects.filter(build=result.build, source_gap=True).count() == 31


@pytest.mark.django_db(transaction=True)
def test_terrain_build_resumes_without_duplicate_cells_or_version_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from national_terrain import services
    from national_terrain.models import TerrainCell

    grid_build = _completed_grid_build(version="grid-resume-v1", chunk_count=2)

    monkeypatch.setattr(services, "cache_tile", _confirmed_missing_tile)
    events: list[dict[str, object]] = []
    first = services.build_national_terrain(
        grid_build_version=grid_build.version,
        build_version="terrain-resume-v1",
        cache_dir=tmp_path,
        max_chunks=1,
        progress_callback=events.append,
    )
    assert first.status == "running"
    assert events[0]["completed_chunk_count"] == 1
    assert events[0]["result_count"] == 1
    second = services.build_national_terrain(
        grid_build_version=grid_build.version,
        build_version="terrain-resume-v1",
        cache_dir=tmp_path,
    )
    assert second.status == "completed"
    assert TerrainCell.objects.filter(build=second.build).count() == 2
    assert TerrainCell.objects.filter(build=second.build).values("grid_build_cell").distinct().count() == 2

    with pytest.raises(services.TerrainBuildInputMismatchError):
        services.build_national_terrain(
            grid_build_version=grid_build.version,
            build_version="terrain-resume-v1",
            cache_dir=tmp_path,
            quality_settings={"flat_slope_deg": 4.0, "min_resultant_length": 0.3},
        )


@pytest.mark.django_db(transaction=True)
def test_resumed_build_rejects_changed_source_metadata_and_preserves_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from national_terrain import services
    from national_terrain.models import TerrainChunk, TerrainSourceTile

    grid_build = _completed_grid_build(version="grid-source-identity-v1", chunk_count=2)
    summary = {
        "altitude_m": 800.0,
        "slope_deg": 10.0,
        "aspect_deg": 180.0,
        "altitude_m_valid_fraction": 1.0,
        "slope_deg_valid_fraction": 1.0,
        "aspect_deg_valid_fraction": 1.0,
        "altitude_m_reliability": "high",
        "slope_deg_reliability": "high",
        "aspect_deg_reliability": "high",
        "source_gap": False,
    }
    state = {"sha256": "a" * 64, "fail": False}

    def cached_tile(*, tile_name: str, cache_dir: Path) -> source.CachedTile:
        if state["fail"]:
            raise source.TerrainSourceError("temporary source failure")
        return source.CachedTile(
            tile_name=tile_name,
            path=cache_dir / f"{tile_name}.tif",
            status="available",
            metadata={
                "tile_name": tile_name,
                "status": "available",
                "url": f"https://example.invalid/{tile_name}.tif",
                "release": terrain.SOURCE_RELEASE,
                "last_modified": "2021",
                "retrieved_at": "2026-01-01T00:00:00+00:00",
                "size_bytes": 1,
                "sha256": state["sha256"],
                "crs": terrain.SOURCE_CRS,
                "native_pixel_m": terrain.SOURCE_NATIVE_PIXEL_M,
                "vertical_datum": terrain.SOURCE_VERTICAL_DATUM,
                "credit": terrain.LICENCE,
            },
            reused=True,
        )

    monkeypatch.setattr(services, "cache_tile", cached_tile)
    monkeypatch.setattr(services, "_summaries", lambda **kwargs: [summary])
    first = services.build_national_terrain(
        grid_build_version=grid_build.version,
        build_version="terrain-source-identity-v1",
        cache_dir=tmp_path,
        max_chunks=1,
    )
    assert first.status == "running"
    previous = list(
        TerrainSourceTile.objects.filter(build=first.build).values(
            "tile_name", "status", "sha256", "retrieved_at", "url"
        )
    )
    assert previous

    state["sha256"] = "b" * 64
    with pytest.raises(services.TerrainBuildInputMismatchError):
        services.build_national_terrain(
            grid_build_version=grid_build.version,
            build_version="terrain-source-identity-v1",
            cache_dir=tmp_path,
        )
    assert list(
        TerrainSourceTile.objects.filter(build=first.build).values(
            "tile_name", "status", "sha256", "retrieved_at", "url"
        )
    ) == previous
    assert TerrainChunk.objects.filter(
        build=first.build, status=TerrainChunk.Status.PLANNED
    ).count() == 1

    state["fail"] = True
    with pytest.raises(source.TerrainSourceError):
        services.build_national_terrain(
            grid_build_version=grid_build.version,
            build_version="terrain-source-identity-v1",
            cache_dir=tmp_path,
        )
    assert all(
        tile.status == TerrainSourceTile.Status.AVAILABLE
        for tile in TerrainSourceTile.objects.filter(build=first.build)
    )


@pytest.mark.django_db(transaction=True)
def test_resumed_build_freezes_confirmed_missing_source_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from national_terrain import services
    from national_terrain.models import TerrainChunk, TerrainSourceTile

    grid_build = _completed_grid_build(version="grid-missing-identity-v1", chunk_count=2)
    monkeypatch.setattr(services, "cache_tile", _confirmed_missing_tile)
    first = services.build_national_terrain(
        grid_build_version=grid_build.version,
        build_version="terrain-missing-identity-v1",
        cache_dir=tmp_path,
        max_chunks=1,
    )
    assert first.status == "running"
    previous = list(
        TerrainSourceTile.objects.filter(build=first.build).values(
            "tile_name", "status", "url", "release", "retrieved_at", "sha256"
        )
    )
    assert previous
    assert all(row["status"] == TerrainSourceTile.Status.CONFIRMED_MISSING for row in previous)

    def available_tile(*, tile_name: str, cache_dir: Path) -> source.CachedTile:
        return source.CachedTile(
            tile_name=tile_name,
            path=cache_dir / f"{tile_name}.tif",
            status="available",
            metadata={
                "tile_name": tile_name,
                "status": "available",
                "url": "https://example.invalid/tile.tif",
                "release": terrain.SOURCE_RELEASE,
                "last_modified": "2021",
                "retrieved_at": "2026-01-01T00:00:00+00:00",
                "size_bytes": 1,
                "sha256": "a" * 64,
                "crs": terrain.SOURCE_CRS,
                "native_pixel_m": terrain.SOURCE_NATIVE_PIXEL_M,
                "vertical_datum": terrain.SOURCE_VERTICAL_DATUM,
                "credit": terrain.LICENCE,
            },
            reused=True,
        )

    monkeypatch.setattr(services, "cache_tile", available_tile)
    with pytest.raises(services.TerrainBuildInputMismatchError):
        services.build_national_terrain(
            grid_build_version=grid_build.version,
            build_version="terrain-missing-identity-v1",
            cache_dir=tmp_path,
        )
    assert list(
        TerrainSourceTile.objects.filter(build=first.build).values(
            "tile_name", "status", "url", "release", "retrieved_at", "sha256"
        )
    ) == previous
    assert TerrainChunk.objects.filter(
        build=first.build, status=TerrainChunk.Status.PLANNED
    ).count() == 1

    def transient_failure(*, tile_name: str, cache_dir: Path) -> source.CachedTile:
        raise source.TerrainSourceError("temporary source failure")

    monkeypatch.setattr(services, "cache_tile", transient_failure)
    with pytest.raises(source.TerrainSourceError):
        services.build_national_terrain(
            grid_build_version=grid_build.version,
            build_version="terrain-missing-identity-v1",
            cache_dir=tmp_path,
        )
    assert list(
        TerrainSourceTile.objects.filter(build=first.build).values(
            "tile_name", "status", "url", "release", "retrieved_at", "sha256"
        )
    ) == previous
    assert TerrainChunk.objects.filter(
        build=first.build, status=TerrainChunk.Status.FAILED
    ).count() == 1


@pytest.mark.django_db(transaction=True)
def test_build_race_recovery_rejects_winner_for_another_grid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from django.db import IntegrityError

    from national_terrain import services
    from national_grid.models import GridBuild

    requested_grid = _completed_grid_build(version="grid-race-requested-v1")
    winner_grid = GridBuild.objects.create(
        version="grid-race-winner-v1",
        fingerprint="a" * 64,
        status=GridBuild.Status.COMPLETED,
    )

    class FakeQuerySet:
        def filter(self, **kwargs: object) -> "FakeQuerySet":
            return self

        def first(self) -> None:
            return None

        def get(self, **kwargs: object) -> object:
            return type("Winner", (), {"grid_build_id": winner_grid.id})()

    class FakeManager:
        def select_for_update(self) -> FakeQuerySet:
            return FakeQuerySet()

        def create(self, **kwargs: object) -> object:
            raise IntegrityError("simulated concurrent insert")

    monkeypatch.setattr(services.TerrainBuild, "objects", FakeManager())
    with pytest.raises(services.TerrainBuildInputMismatchError):
        services._get_or_create_build(
            grid_build=requested_grid,
            build_version="terrain-race-v1",
            fingerprint="a" * 64,
            source_metadata={},
        )
