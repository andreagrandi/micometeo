"""Offline checks for the national forest source and pure calculations."""

import gzip
import io
import itertools
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import numpy as np
import pytest
import rasterio
from django.contrib.gis.geos import GEOSGeometry
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.db.models import ProtectedError
from django.test.utils import CaptureQueriesContext
from rasterio.transform import from_origin

from micometeo.habitat.forest import summarise_national_block
from national_forest import layer, source
from national_forest.models import ForestBuild, ForestCell, ForestChunk
from national_forest.services import (
    ForestBuildIncompleteError,
    ForestBuildInputMismatchError,
    _get_or_create_build,
    build_national_forest,
    forest_build_fingerprint,
    regional_counts,
    _update_build_progress,
    weather_cell,
)
from national_grid.models import GridBuild, GridBuildCell, GridCell, GridChunk, GridRegion
from micometeo.finds.grid import format_cell_id


_VERSION_COUNTER = itertools.count()


def test_national_block_keeps_unrounded_fractions_and_source_counts() -> None:
    pixels = np.array([1, 1, 1, 0, 0, 0], dtype="uint8")
    result = summarise_national_block(pixels=pixels)
    assert result["forest_pixel_count"] == 3
    assert result["valid_pixel_count"] == 6
    assert result["forest_share"] == pytest.approx(0.5)
    assert result["broadleaf_share"] == 1.0
    assert result["leaf_type"] == "broadleaf"
    assert result["coverage_quality"] == "high"


@pytest.mark.parametrize(
    ("broadleaf", "conifer", "expected"),
    [(75, 25, "broadleaf"), (74, 26, "mixed"), (25, 75, "conifer")],
)
def test_national_leaf_type_boundaries(
    broadleaf: int, conifer: int, expected: str
) -> None:
    pixels = np.array([1] * broadleaf + [2] * conifer, dtype="uint8")
    assert summarise_national_block(pixels=pixels)["leaf_type"] == expected


@pytest.mark.parametrize(
    ("valid", "expected"), [(95, "high"), (94, "low"), (50, "low"), (49, "unavailable")]
)
def test_national_coverage_boundaries(valid: int, expected: str) -> None:
    pixels = np.array([0] * valid + [254] * (100 - valid), dtype="uint8")
    assert summarise_national_block(pixels=pixels)["coverage_quality"] == expected


def test_national_forest_flag_uses_counts_without_rounding() -> None:
    below = np.array([1] * 999 + [0] * 9_001, dtype="uint8")
    at = np.array([1] * 1_000 + [0] * 9_000, dtype="uint8")
    assert summarise_national_block(pixels=below)["is_forest"] is False
    assert summarise_national_block(pixels=at)["is_forest"] is True


def test_missing_codes_remain_separate_and_no_forest_has_null_broadleaf() -> None:
    result = summarise_national_block(pixels=np.array([0, 0, 254, 255], dtype="uint8"))
    assert result["forest_share"] == 0.0
    assert result["broadleaf_share"] is None
    assert result["unclassifiable_pixel_count"] == 1
    assert result["outside_pixel_count"] == 1
    assert result["leaf_type"] == "no forest"


def test_unsupported_tree_code_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        summarise_national_block(pixels=np.array([3], dtype="uint8"))


def _geo_tiff_bytes(*, bounds: tuple[int, int, int, int], values: np.ndarray, crs: str = "EPSG:3035") -> bytes:
    west, south, east, north = bounds
    handle = io.BytesIO()
    with rasterio.MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            height=values.shape[0],
            width=values.shape[1],
            count=1,
            dtype="uint8",
            crs=crs,
            transform=from_origin(west, north, 10, 10),
        ) as dataset:
            dataset.write(values, 1)
        handle.write(memory.read())
    return handle.getvalue()


class _Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        value = self.content
        self.content = b""
        return value


def test_source_query_and_cache_key_include_exact_request_values(tmp_path: Path) -> None:
    bounds = (4_000_000, 2_000_000, 4_000_100, 2_000_100)
    query = source.build_request(bounds=bounds)
    assert query["bbox"] == "4000000,2000000,4000100,2000100"
    assert query["bboxSR"] == 3035
    assert query["imageSR"] == 3035
    assert query["size"] == "10,10"
    assert query["interpolation"] == "RSP_NearestNeighbor"
    assert source.cache_key(bounds=bounds) != source.cache_key(
        bounds=(4_000_000, 2_000_000, 4_000_200, 2_000_100)
    )


def test_source_cache_validates_and_reuses_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bounds = (4_000_000, 2_000_000, 4_000_100, 2_000_100)
    content = _geo_tiff_bytes(bounds=bounds, values=np.zeros((10, 10), dtype="uint8"))
    calls: list[str] = []

    def fake_urlopen(request: object, timeout: int) -> _Response:
        calls.append(str(request))
        return _Response(content=content)

    monkeypatch.setattr(source.urllib.request, "urlopen", fake_urlopen)
    first = source.cache_source_chunk(bounds=bounds, cache_dir=tmp_path)
    second = source.cache_source_chunk(bounds=bounds, cache_dir=tmp_path)
    assert first.reused is False
    assert second.reused is True
    assert len(calls) == 1
    assert second.metadata["request_options"] == first.metadata["request_options"]
    assert first.metadata["source_path"] == str(first.path)
    assert first.metadata["source_crs_wkt"]


def test_source_cache_serializes_same_key_fetches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bounds = (4_000_000, 2_000_000, 4_000_100, 2_000_100)
    content = _geo_tiff_bytes(bounds=bounds, values=np.zeros((10, 10), dtype="uint8"))
    calls: list[str] = []

    def fake_urlopen(request: object, timeout: int) -> _Response:
        calls.append(str(request))
        time.sleep(0.1)
        return _Response(content=content)

    monkeypatch.setattr(source.urllib.request, "urlopen", fake_urlopen)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(source.cache_source_chunk, bounds=bounds, cache_dir=tmp_path)
            for _ in range(2)
        ]
        results = [future.result() for future in futures]

    assert len(calls) == 1
    assert sorted(result.reused for result in results) == [False, True]
    assert results[0].path == results[1].path


def test_source_cache_recovers_orphaned_raster_before_downloading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bounds = (4_000_000, 2_000_000, 4_000_100, 2_000_100)
    content = _geo_tiff_bytes(bounds=bounds, values=np.zeros((10, 10), dtype="uint8"))
    key = source.cache_key(bounds=bounds)
    source.raster_path(cache_dir=tmp_path, key=key).write_bytes(content)
    calls: list[str] = []

    def fake_urlopen(request: object, timeout: int) -> _Response:
        calls.append(str(request))
        return _Response(content=content)

    monkeypatch.setattr(source.urllib.request, "urlopen", fake_urlopen)
    cached = source.cache_source_chunk(bounds=bounds, cache_dir=tmp_path)

    assert cached.reused is False
    assert len(calls) == 1
    assert source.sidecar_path(cache_dir=tmp_path, key=key).is_file()


def test_source_cache_rejects_bad_shape_and_code(tmp_path: Path) -> None:
    bounds = (4_000_000, 2_000_000, 4_000_100, 2_000_100)
    path = tmp_path / "bad.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=9,
        width=10,
        count=1,
        dtype="uint8",
        crs="EPSG:3035",
        transform=from_origin(bounds[0], bounds[3], 10, 10),
    ) as dataset:
        dataset.write(np.full((9, 10), 3, dtype="uint8"), 1)
    with pytest.raises(source.ForestSourceError):
        source.validate_raster(path=path, bounds=bounds)


def test_source_accepts_exact_legacy_epsg3035_wkt_and_rejects_wrong_crs(tmp_path: Path) -> None:
    bounds = (4_000_000, 2_000_000, 4_000_100, 2_000_100)
    legacy_path = tmp_path / "legacy.tif"
    legacy_path.write_bytes(
        _geo_tiff_bytes(
            bounds=bounds,
            values=np.zeros((10, 10), dtype="uint8"),
            crs=source.LEGACY_EPSG3035_WKT,
        )
    )
    metadata = source.validate_raster(path=legacy_path, bounds=bounds)
    assert metadata["crs"] == "EPSG:3035"
    assert metadata["crs_wkt"] == source.LEGACY_EPSG3035_RASTERIO_WKT
    wrong_path = tmp_path / "wrong-crs.tif"
    wrong_path.write_bytes(
        _geo_tiff_bytes(
            bounds=bounds,
            values=np.zeros((10, 10), dtype="uint8"),
            crs="EPSG:4326",
        )
    )
    with pytest.raises(source.ForestSourceError, match="EPSG:3035"):
        source.validate_raster(path=wrong_path, bounds=bounds)


def test_layer_weighting_is_deterministic_and_has_one_public_property(tmp_path: Path) -> None:
    rows = [
        {
            "corner_e": 4_000_000 + column * 500,
            "corner_n": 2_000_000 + row * 500,
            "forest_pixel_count": 1 if column == 0 else 0,
            "valid_pixel_count": 10,
        }
        for row in range(4)
        for column in range(4)
    ]
    first = layer.write_forest_layer(rows=rows, output_path=tmp_path / "one.gz")
    second = layer.write_forest_layer(rows=list(reversed(rows)), output_path=tmp_path / "two.gz")
    assert first.sha256 == second.sha256
    with gzip.open(first.path, "rt", encoding="utf-8") as handle:
        document = json.load(handle)
    assert len(document["features"]) == 1
    assert set(document["features"][0]["properties"]) == {"forest_share"}
    assert document["features"][0]["properties"]["forest_share"] == pytest.approx(0.025)


def test_layer_groups_coarse_cells_before_streaming_and_skips_unavailable_rows(
    tmp_path: Path,
) -> None:
    rows = [
        {
            "corner_e": 4_000_000,
            "corner_n": 2_000_000,
            "forest_pixel_count": 10,
            "valid_pixel_count": 10,
            "is_forest": True,
        },
        {
            "corner_e": 4_002_000,
            "corner_n": 2_000_000,
            "forest_pixel_count": 10,
            "valid_pixel_count": 10,
            "is_forest": True,
        },
        {
            "corner_e": 4_000_000,
            "corner_n": 2_002_000,
            "forest_pixel_count": 10,
            "valid_pixel_count": 10,
            "is_forest": True,
        },
        {
            "corner_e": 4_000_500,
            "corner_n": 2_000_000,
            "forest_pixel_count": 1_000,
            "valid_pixel_count": 1_000,
            "is_forest": None,
        },
    ]
    artifact = layer.write_forest_layer(rows=rows, output_path=tmp_path / "grouped.gz")

    assert artifact.feature_count == 3
    with gzip.open(artifact.path, "rt", encoding="utf-8") as handle:
        document = json.load(handle)
    assert len(document["features"]) == 3
    assert [feature["properties"]["forest_share"] for feature in document["features"]] == [
        1.0,
        1.0,
        1.0,
    ]


def test_layer_publication_keeps_previous_artifact_when_stream_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "stable.gz"
    rows = [{"corner_e": 4_000_000, "corner_n": 2_000_000, "forest_pixel_count": 1, "valid_pixel_count": 1}]
    layer.write_forest_layer(rows=rows, output_path=output_path)
    original = output_path.read_bytes()

    def fail_stream(*args: object, **kwargs: object) -> tuple[int, int]:
        raise ValueError("stream failed")

    monkeypatch.setattr(layer, "_stream_json", fail_stream)
    with pytest.raises(ValueError, match="stream failed"):
        layer.write_forest_layer(rows=rows, output_path=output_path)

    assert output_path.read_bytes() == original
    assert list(tmp_path.glob(".stable.gz.*.tmp")) == []


def _polygon(*, west: int, south: int, east: int, north: int) -> GEOSGeometry:
    return GEOSGeometry(
        f"POLYGON (({west} {south}, {east} {south}, {east} {north}, "
        f"{west} {north}, {west} {south}))",
        srid=3035,
    )


def _multi_polygon(*, west: int, south: int, east: int, north: int) -> GEOSGeometry:
    polygon = _polygon(west=west, south=south, east=east, north=north)
    return GEOSGeometry(f"MULTIPOLYGON ({polygon.wkt[8:]})", srid=3035)


def _version(*, name: str) -> str:
    return f"test-forest-{name}-{next(_VERSION_COUNTER)}"


def _make_grid(
    *,
    chunks: list[tuple[int, int, int, int, list[tuple[int, int]]]],
    region_count: int = 1,
    status: str = GridBuild.Status.COMPLETED,
) -> GridBuild:
    """Create a small completed grid with exact memberships for service tests."""
    grid_build = GridBuild.objects.create(
        version=_version(name="grid"),
        fingerprint="a" * 64,
        status=status,
        planned_chunk_count=len(chunks),
        completed_chunk_count=len(chunks) if status == GridBuild.Status.COMPLETED else 0,
    )
    west = min(chunk[0] for chunk in chunks)
    south = min(chunk[1] for chunk in chunks)
    east = max(chunk[2] for chunk in chunks)
    north = max(chunk[3] for chunk in chunks)
    regions = [
        GridRegion.objects.create(
            build=grid_build,
            istat_code=f"{index:02d}",
            name=f"Region {index:02d}",
            geometry=_multi_polygon(west=west, south=south, east=east, north=north),
        )
        for index in range(1, region_count + 1)
    ]
    for chunk_index, (chunk_west, chunk_south, chunk_east, chunk_north, memberships) in enumerate(chunks):
        grid_chunk = GridChunk.objects.create(
            build=grid_build,
            west_e=chunk_west,
            south_n=chunk_south,
            east_e=chunk_east,
            north_n=chunk_north,
            status=GridChunk.Status.COMPLETED,
        )
        for membership_index, (corner_e, corner_n) in enumerate(memberships):
            cell = GridCell.objects.create(
                cell_id=format_cell_id(corner_e=corner_e, corner_n=corner_n),
                corner_e=corner_e,
                corner_n=corner_n,
                geometry=_polygon(
                    west=corner_e,
                    south=corner_n,
                    east=corner_e + 500,
                    north=corner_n + 500,
                ),
            )
            GridBuildCell.objects.create(
                build=grid_build,
                cell=cell,
                chunk=grid_chunk,
                owner_region=regions[(chunk_index + membership_index) % region_count],
                land_geometry=_multi_polygon(
                    west=corner_e,
                    south=corner_n,
                    east=corner_e + 500,
                    north=corner_n + 500,
                ),
                land_share=1.0,
            )
    return grid_build


def _fake_source_loader(*, calls: list[tuple[int, int, int, int]], values_by_bounds: dict[tuple[int, int, int, int], int]):
    def load(*, bounds: tuple[int, int, int, int], cache_dir: Path) -> Path:
        calls.append(bounds)
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / ("source_" + "_".join(str(value) for value in bounds) + ".tif")
        if path.exists():
            return path
        west, south, east, north = bounds
        values = np.full(
            ((north - south) // 10, (east - west) // 10),
            values_by_bounds.get(bounds, 0),
            dtype="uint8",
        )
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=values.shape[0],
            width=values.shape[1],
            count=1,
            dtype="uint8",
            crs="EPSG:3035",
            transform=from_origin(west, north, 10, 10),
        ) as dataset:
            dataset.write(values, 1)
        return path

    return load


@pytest.mark.django_db(transaction=True)
def test_build_stops_resumes_filters_sparse_memberships_and_repeats_without_writes(tmp_path: Path) -> None:
    first_bounds = (4_000_000, 2_000_000, 4_001_000, 2_001_000)
    sparse_bounds = (4_001_000, 2_000_000, 4_002_000, 2_001_000)
    grid_build = _make_grid(
        chunks=[
            (*first_bounds, [(4_000_000, 2_000_000), (4_000_500, 2_000_000), (4_000_000, 2_000_500), (4_000_500, 2_000_500)]),
            (*sparse_bounds, [(4_001_000, 2_000_000)]),
        ]
    )
    calls: list[tuple[int, int, int, int]] = []
    loader = _fake_source_loader(
        calls=calls,
        values_by_bounds={first_bounds: 1, sparse_bounds: 2},
    )
    first = build_national_forest(
        grid_build_version=grid_build.version,
        build_version=_version(name="resume"),
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        max_source_chunk_m=1_000,
        max_chunks=1,
        source_loader=loader,
    )
    assert first.status == ForestBuild.Status.RUNNING
    assert first.build.completed_chunk_count == 1
    assert first.build.cell_count == 4
    assert first.build.forest_cell_count == 4
    assert ForestCell.objects.filter(build=first.build).count() == 4
    first_ids = set(ForestCell.objects.filter(build=first.build).values_list("id", flat=True))
    second = build_national_forest(
        grid_build_version=grid_build.version,
        build_version=first.build.version,
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        max_source_chunk_m=1_000,
        source_loader=loader,
    )
    assert second.status == ForestBuild.Status.COMPLETED
    assert ForestCell.objects.filter(build=second.build).count() == 5
    assert ForestChunk.objects.filter(build=second.build, status=ForestChunk.Status.COMPLETED).count() == 2
    completed_chunk = ForestChunk.objects.filter(build=second.build).order_by("south_n", "west_e").first()
    assert completed_chunk is not None
    assert completed_chunk.source_sha256
    assert completed_chunk.source_path
    assert completed_chunk.source_metadata["raw_bytes"] == completed_chunk.source_bytes
    assert len(calls) == 2
    artifact_sha = second.build.layer_sha256
    values = list(ForestCell.objects.filter(build=second.build).order_by("id").values_list("forest_share", "leaf_type"))
    ids_before_repeat = set(ForestCell.objects.filter(build=second.build).values_list("id", flat=True))
    repeated = build_national_forest(
        grid_build_version=grid_build.version,
        build_version=second.build.version,
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        source_loader=loader,
    )
    assert repeated.status == ForestBuild.Status.COMPLETED
    assert repeated.processed_chunks == 0
    assert len(calls) == 2
    assert repeated.build.layer_sha256 == artifact_sha
    assert values == list(ForestCell.objects.filter(build=second.build).order_by("id").values_list("forest_share", "leaf_type"))
    assert ids_before_repeat == set(ForestCell.objects.filter(build=second.build).values_list("id", flat=True))
    assert first_ids.issubset(ids_before_repeat)


@pytest.mark.django_db(transaction=True)
def test_weather_counts_use_distinct_centres_per_region(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_bounds = (4_000_000, 2_000_000, 4_000_500, 2_000_500)
    second_bounds = (4_000_500, 2_000_000, 4_001_000, 2_000_500)
    grid_build = _make_grid(
        chunks=[
            (*first_bounds, [(first_bounds[0], first_bounds[1])]),
            (*second_bounds, [(second_bounds[0], second_bounds[1])]),
        ],
        region_count=2,
    )
    monkeypatch.setattr(
        "national_forest.services.weather_cell_for_corner",
        lambda **kwargs: (44.05, 10.05),
    )
    values = {first_bounds: 1, second_bounds: 1}
    result = build_national_forest(
        grid_build_version=grid_build.version,
        build_version=_version(name="weather-distinct"),
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        max_source_chunk_m=500,
        source_loader=_fake_source_loader(calls=[], values_by_bounds=values),
    )

    assert result.build.weather_cell_count == 1
    assert [row["weather_cell_count"] for row in result.regional_counts] == [1, 1]
    assert sum(row["weather_cell_count"] for row in result.regional_counts) == 2


@pytest.mark.django_db(transaction=True)
def test_build_artifacts_use_versioned_paths_without_overwriting_previous_build(
    tmp_path: Path,
) -> None:
    bounds = (4_000_000, 2_000_000, 4_000_500, 2_000_500)
    grid_build = _make_grid(chunks=[(*bounds, [(bounds[0], bounds[1])])])
    loader = _fake_source_loader(calls=[], values_by_bounds={bounds: 1})
    first = build_national_forest(
        grid_build_version=grid_build.version,
        build_version=_version(name="artifact-one"),
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        source_loader=loader,
    )
    first_path = Path(first.build.layer_path)
    first_bytes = first_path.read_bytes()
    second = build_national_forest(
        grid_build_version=grid_build.version,
        build_version=_version(name="artifact-two"),
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        source_loader=loader,
    )
    second_path = Path(second.build.layer_path)

    assert first_path != second_path
    assert first_path.parent.name == first.build.version
    assert second_path.parent.name == second.build.version
    assert first_path.is_file()
    assert second_path.is_file()
    assert first_path.read_bytes() == first_bytes


@pytest.mark.django_db
def test_build_rejects_incomplete_grid_and_changed_fingerprint(tmp_path: Path) -> None:
    bounds = (4_000_000, 2_000_000, 4_000_500, 2_000_500)
    pending = _make_grid(chunks=[(*bounds, [(bounds[0], bounds[1])])], status=GridBuild.Status.RUNNING)
    with pytest.raises(ForestBuildIncompleteError, match="completed"):
        build_national_forest(
            grid_build_version=pending.version,
            build_version=_version(name="pending"),
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            source_loader=lambda **kwargs: None,
        )
    complete_bounds = (4_001_000, 2_000_000, 4_001_500, 2_000_500)
    complete = _make_grid(chunks=[(*complete_bounds, [(complete_bounds[0], complete_bounds[1])])])
    build_version = _version(name="fingerprint")
    ForestBuild.objects.create(
        version=build_version,
        grid_build=complete,
        fingerprint="b" * 64,
    )
    with pytest.raises(ForestBuildInputMismatchError, match="different inputs"):
        build_national_forest(
            grid_build_version=complete.version,
            build_version=build_version,
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            source_loader=lambda **kwargs: None,
        )


@pytest.mark.django_db(transaction=True)
def test_concurrent_first_build_creation_returns_one_winner() -> None:
    bounds = (4_000_000, 2_000_000, 4_000_500, 2_000_500)
    grid_build = _make_grid(chunks=[(*bounds, [(bounds[0], bounds[1])])])
    build_version = _version(name="concurrent")
    source_options = {
        "bboxSR": 3035,
        "imageSR": 3035,
        "pixelType": "U8",
        "interpolation": "RSP_NearestNeighbor",
        "format": "tiff",
    }
    fingerprint = forest_build_fingerprint(
        grid_build_id=str(grid_build.id),
        grid_fingerprint=grid_build.fingerprint,
        request_options=source_options,
    )
    barrier = Barrier(2)

    def create() -> tuple[ForestBuild, bool]:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            local_grid = GridBuild.objects.get(pk=grid_build.pk)
            return _get_or_create_build(
                grid_build=local_grid,
                build_version=build_version,
                fingerprint=fingerprint,
                source_options=source_options,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(create) for _ in range(2)]
        results = [future.result() for future in futures]

    assert sorted(created for _, created in results) == [False, True]
    assert ForestBuild.objects.filter(version=build_version).count() == 1
    assert all(build.fingerprint == fingerprint for build, _ in results)


@pytest.mark.django_db(transaction=True)
def test_resume_rejects_a_different_source_chunk_layout_before_mutation(tmp_path: Path) -> None:
    bounds = (4_000_000, 2_000_000, 4_001_000, 2_001_000)
    grid_build = _make_grid(chunks=[(*bounds, [(bounds[0], bounds[1])])])
    build_version = _version(name="layout")
    build_national_forest(
        grid_build_version=grid_build.version,
        build_version=build_version,
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        max_source_chunk_m=1_000,
        max_chunks=0,
        source_loader=lambda **kwargs: None,
    )
    build = ForestBuild.objects.get(version=build_version)
    before = list(ForestChunk.objects.filter(build=build).values_list("id", "status", "west_e", "east_e"))

    with pytest.raises(ForestBuildInputMismatchError, match="source chunks"):
        build_national_forest(
            grid_build_version=grid_build.version,
            build_version=build_version,
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            max_source_chunk_m=500,
            max_chunks=0,
            source_loader=lambda **kwargs: None,
        )

    build.refresh_from_db()
    after = list(ForestChunk.objects.filter(build=build).values_list("id", "status", "west_e", "east_e"))
    assert build.source_chunk_size_m == 1_000
    assert after == before


@pytest.mark.django_db(transaction=True)
def test_completed_chunk_persists_cached_source_provenance(tmp_path: Path) -> None:
    bounds = (4_000_000, 2_000_000, 4_000_500, 2_000_500)
    grid_build = _make_grid(chunks=[(*bounds, [(bounds[0], bounds[1])])])
    base_loader = _fake_source_loader(calls=[], values_by_bounds={bounds: 1})

    def loader(*, bounds: tuple[int, int, int, int], cache_dir: Path) -> source.CachedForestChunk:
        path = base_loader(bounds=bounds, cache_dir=cache_dir)
        metadata = {
            "sha256": source.sha256_path(path=path),
            "raw_bytes": path.stat().st_size,
            "retrieved_at": "2026-10-12T10:11:12+00:00",
            "source_crs_wkt": source.LEGACY_EPSG3035_WKT,
            "source_path": str(path),
        }
        return source.CachedForestChunk(
            cache_key="a" * 64,
            path=path,
            metadata=metadata,
            reused=False,
        )

    result = build_national_forest(
        grid_build_version=grid_build.version,
        build_version=_version(name="provenance"),
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        source_loader=loader,
    )
    chunk = ForestChunk.objects.get(build=result.build)

    assert chunk.source_sha256 == chunk.source_metadata["sha256"]
    assert chunk.source_retrieved_at == "2026-10-12T10:11:12+00:00"
    assert chunk.source_crs_wkt == source.LEGACY_EPSG3035_WKT
    assert chunk.source_path == chunk.source_metadata["source_path"]


@pytest.mark.django_db(transaction=True)
def test_completed_repeat_hydrates_provenance_from_sidecar_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bounds = (4_000_000, 2_000_000, 4_000_500, 2_000_500)
    grid_build = _make_grid(chunks=[(*bounds, [(bounds[0], bounds[1])])])
    content = _geo_tiff_bytes(bounds=bounds, values=np.ones((50, 50), dtype="uint8"))
    calls: list[str] = []

    def fake_urlopen(request: object, timeout: int) -> _Response:
        calls.append(str(request))
        return _Response(content=content)

    monkeypatch.setattr(source.urllib.request, "urlopen", fake_urlopen)
    build_version = _version(name="sidecar-reconcile")
    result = build_national_forest(
        grid_build_version=grid_build.version,
        build_version=build_version,
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        source_loader=source.cache_source_chunk,
    )
    chunk = ForestChunk.objects.get(build=result.build)
    ForestChunk.objects.filter(id=chunk.id).update(
        source_sha256="",
        source_retrieved_at="",
        source_crs_wkt="",
        source_path="",
        source_metadata={},
    )
    calls_before_repeat = len(calls)

    def fail_urlopen(request: object, timeout: int) -> _Response:
        raise AssertionError("completed reconciliation must use the local sidecar")

    monkeypatch.setattr(source.urllib.request, "urlopen", fail_urlopen)
    repeated = build_national_forest(
        grid_build_version=grid_build.version,
        build_version=build_version,
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        source_loader=source.cache_source_chunk,
    )
    chunk.refresh_from_db()

    assert repeated.status == ForestBuild.Status.COMPLETED
    assert len(calls) == calls_before_repeat
    assert chunk.source_sha256
    assert chunk.source_retrieved_at
    assert chunk.source_crs_wkt
    assert chunk.source_path


def test_weather_cells_use_decimal_floor_and_cell_centres() -> None:
    assert weather_cell(latitude=44.0999, longitude=10.0999) == (44.05, 10.05)
    assert weather_cell(latitude=44.1, longitude=10.1) == (44.15, 10.15)
    assert weather_cell(latitude=44.0, longitude=10.0) == (44.05, 10.05)


@pytest.mark.django_db(transaction=True)
def test_regional_counts_include_all_twenty_regions(tmp_path: Path) -> None:
    chunks = []
    values: dict[tuple[int, int, int, int], int] = {}
    for index in range(20):
        bounds = (4_000_000 + index * 500, 2_000_000, 4_000_500 + index * 500, 2_000_500)
        chunks.append((*bounds, [(bounds[0], bounds[1])]))
        values[bounds] = 1 if index % 2 == 0 else 0
    grid_build = _make_grid(chunks=chunks, region_count=20)
    calls: list[tuple[int, int, int, int]] = []
    result = build_national_forest(
        grid_build_version=grid_build.version,
        build_version=_version(name="regions"),
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        max_source_chunk_m=500,
        source_loader=_fake_source_loader(calls=calls, values_by_bounds=values),
    )
    assert len(result.regional_counts) == 20
    assert [row["istat_code"] for row in result.regional_counts] == [f"{index:02d}" for index in range(1, 21)]
    assert sum(row["forest_cell_count"] for row in result.regional_counts) == 10
    assert sum(row["nonforest_cell_count"] for row in result.regional_counts) == 10
    assert sum(row["unavailable_cell_count"] for row in result.regional_counts) == 0
    with CaptureQueriesContext(connection) as captured:
        regional_counts(build=result.build)
    assert len(captured.captured_queries) <= 25
    assert all("land_geometry" not in query["sql"] for query in captured.captured_queries)


@pytest.mark.django_db(transaction=True)
def test_source_failure_creates_no_nonforest_rows(tmp_path: Path) -> None:
    bounds = (4_000_000, 2_000_000, 4_000_500, 2_000_500)
    grid_build = _make_grid(chunks=[(*bounds, [(bounds[0], bounds[1])])])

    def fail_loader(**kwargs: object) -> None:
        raise source.ForestSourceError("transport failed")

    with pytest.raises(source.ForestSourceError, match="transport failed"):
        build_national_forest(
            grid_build_version=grid_build.version,
            build_version=_version(name="failure"),
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            source_loader=fail_loader,
        )
    build = ForestBuild.objects.get(grid_build=grid_build)
    assert build.status == ForestBuild.Status.FAILED
    assert ForestCell.objects.filter(build=build).count() == 0
    assert not ForestCell.objects.filter(build=build, is_forest=False).exists()


@pytest.mark.django_db(transaction=True)
def test_failed_chunk_retry_counts_once_and_clears_build_failure(tmp_path: Path) -> None:
    bounds = (4_000_000, 2_000_000, 4_000_500, 2_000_500)
    grid_build = _make_grid(chunks=[(*bounds, [(bounds[0], bounds[1])])])
    calls: list[tuple[int, int, int, int]] = []
    successful_loader = _fake_source_loader(calls=calls, values_by_bounds={bounds: 1})
    attempts = 0

    def fail_once_loader(*, bounds: tuple[int, int, int, int], cache_dir: Path) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise source.ForestSourceError("temporary transport failure")
        return successful_loader(bounds=bounds, cache_dir=cache_dir)

    build_version = _version(name="retry-count")
    with pytest.raises(source.ForestSourceError, match="temporary transport failure"):
        build_national_forest(
            grid_build_version=grid_build.version,
            build_version=build_version,
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            source_loader=fail_once_loader,
        )

    failed = ForestBuild.objects.get(version=build_version)
    failed_chunk = ForestChunk.objects.get(build=failed)
    assert failed.failed_chunk_count == 1
    assert failed_chunk.attempt_count == 1

    completed = build_national_forest(
        grid_build_version=grid_build.version,
        build_version=build_version,
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "output",
        source_loader=fail_once_loader,
    )
    failed_chunk.refresh_from_db()

    assert completed.status == ForestBuild.Status.COMPLETED
    assert completed.build.failed_chunk_count == 0
    assert failed_chunk.attempt_count == 2


@pytest.mark.django_db(transaction=True)
def test_layer_failure_does_not_mark_build_completed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bounds = (4_000_000, 2_000_000, 4_000_500, 2_000_500)
    grid_build = _make_grid(chunks=[(*bounds, [(bounds[0], bounds[1])])])
    calls: list[tuple[int, int, int, int]] = []
    loader = _fake_source_loader(calls=calls, values_by_bounds={bounds: 1})

    def fail_layer(**kwargs: object) -> None:
        raise ValueError("invalid final artifact")

    monkeypatch.setattr(layer, "write_forest_layer", fail_layer)
    with pytest.raises(ValueError, match="invalid final artifact"):
        build_national_forest(
            grid_build_version=grid_build.version,
            build_version=_version(name="artifact"),
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "output",
            source_loader=loader,
        )
    build = ForestBuild.objects.get(grid_build=grid_build)
    assert build.status != ForestBuild.Status.COMPLETED
    assert build.layer_sha256 == ""


@pytest.mark.django_db(transaction=True)
def test_build_progress_counts_partial_and_unavailable_source_cells() -> None:
    bounds = (4_000_000, 2_000_000, 4_001_500, 2_000_500)
    memberships = [
        (4_000_000, 2_000_000),
        (4_000_500, 2_000_000),
        (4_001_000, 2_000_000),
    ]
    grid_build = _make_grid(chunks=[(*bounds, memberships)])
    build = ForestBuild.objects.create(
        version=_version(name="source-gaps"),
        grid_build=grid_build,
        fingerprint="d" * 64,
        planned_chunk_count=1,
        completed_chunk_count=1,
    )
    grid_chunk = GridChunk.objects.get(build=grid_build)
    forest_chunk = ForestChunk.objects.create(
        build=build,
        grid_chunk=grid_chunk,
        west_e=bounds[0],
        south_n=bounds[1],
        east_e=bounds[2],
        north_n=bounds[3],
        status=ForestChunk.Status.COMPLETED,
        cell_count=3,
    )
    grid_cells = list(GridBuildCell.objects.filter(build=grid_build).order_by("cell__corner_e"))
    ForestCell.objects.bulk_create(
        [
            ForestCell(
                build=build,
                grid_build_cell=grid_cells[0],
                chunk=forest_chunk,
                total_pixel_count=100,
                valid_pixel_count=96,
                forest_pixel_count=96,
                broadleaf_pixel_count=96,
                unclassifiable_pixel_count=4,
                valid_coverage=0.96,
                coverage_quality="high",
                forest_share=1.0,
                broadleaf_share=1.0,
                leaf_type="broadleaf",
                is_forest=True,
                weather_latitude=44.05,
                weather_longitude=10.05,
            ),
            ForestCell(
                build=build,
                grid_build_cell=grid_cells[1],
                chunk=forest_chunk,
                total_pixel_count=100,
                valid_pixel_count=50,
                forest_pixel_count=50,
                broadleaf_pixel_count=50,
                unclassifiable_pixel_count=50,
                valid_coverage=0.5,
                coverage_quality="low",
                forest_share=1.0,
                broadleaf_share=1.0,
                leaf_type="broadleaf",
                is_forest=True,
                weather_latitude=44.05,
                weather_longitude=10.05,
            ),
            ForestCell(
                build=build,
                grid_build_cell=grid_cells[2],
                chunk=forest_chunk,
                total_pixel_count=100,
                valid_pixel_count=0,
                forest_pixel_count=0,
                unclassifiable_pixel_count=100,
                valid_coverage=0.0,
                coverage_quality="unavailable",
            ),
        ]
    )

    _update_build_progress(build_id=build.id)
    build.refresh_from_db()

    assert build.source_gap_count == 3
    assert build.cell_count == 3
    assert build.forest_cell_count == 2


@pytest.mark.django_db
def test_models_retain_source_metadata_and_reject_unsupported_values() -> None:
    bounds = (4_000_000, 2_000_000, 4_000_500, 2_000_500)
    grid_build = _make_grid(chunks=[(*bounds, [(bounds[0], bounds[1])])])
    build = ForestBuild.objects.create(version=_version(name="metadata"), grid_build=grid_build, fingerprint="c" * 64)
    assert build.source_release == "HRL Forest Type 2018"
    assert build.catalogue_url == source.CATALOGUE_URL
    assert "2018" in build.credit
    assert build.grid_build_id == grid_build.id
    membership = GridBuildCell.objects.get(build=grid_build)
    chunk = GridChunk.objects.get(build=grid_build)
    forest_chunk = ForestChunk.objects.create(
        build=build,
        grid_chunk=chunk,
        west_e=bounds[0],
        south_n=bounds[1],
        east_e=bounds[2],
        north_n=bounds[3],
    )
    valid_no_forest = ForestCell(
        build=build,
        grid_build_cell=membership,
        chunk=forest_chunk,
        total_pixel_count=100,
        valid_pixel_count=100,
        forest_pixel_count=9,
        broadleaf_pixel_count=9,
        coverage_quality="high",
        valid_coverage=1.0,
        forest_share=0.09,
        leaf_type="no forest",
        is_forest=False,
    )
    valid_no_forest.full_clean()
    invalid_leaf = ForestCell(
        build=build,
        grid_build_cell=membership,
        chunk=forest_chunk,
        total_pixel_count=4,
        valid_pixel_count=4,
        forest_pixel_count=4,
        broadleaf_pixel_count=4,
        coverage_quality="high",
        valid_coverage=1.0,
        forest_share=1.0,
        leaf_type="beech",
        is_forest=True,
        weather_latitude=44.05,
        weather_longitude=10.05,
    )
    with pytest.raises(ValidationError):
        invalid_leaf.full_clean()
    invalid_weather = ForestCell(
        build=build,
        grid_build_cell=membership,
        chunk=forest_chunk,
        total_pixel_count=4,
        valid_pixel_count=4,
        forest_pixel_count=0,
        coverage_quality="high",
        valid_coverage=1.0,
        forest_share=0.0,
        leaf_type="no forest",
        is_forest=False,
        weather_latitude=44.05,
    )
    with pytest.raises(ValidationError):
        invalid_weather.full_clean()
    with pytest.raises(ProtectedError):
        grid_build.delete()


def test_stored_layer_path_is_relative_inside_the_repository_and_absolute_outside(tmp_path: Path) -> None:
    inside = layer.REPOSITORY_ROOT / "data/processed/mvp_forest/v1/forest_layer_2000m.geojson.gz"
    assert layer.stored_layer_path(path=inside) == "data/processed/mvp_forest/v1/forest_layer_2000m.geojson.gz"
    assert layer.resolve_layer_path(value="data/processed/x.gz") == layer.REPOSITORY_ROOT / "data/processed/x.gz"
    outside = tmp_path / "forest_layer_2000m.geojson.gz"
    assert layer.stored_layer_path(path=outside) == str(outside.resolve())
    assert layer.resolve_layer_path(value=str(outside)) == outside
