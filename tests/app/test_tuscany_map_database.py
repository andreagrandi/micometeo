"""Checks for the isolated Tuscany static database preparation helpers."""

from __future__ import annotations

import copy
import uuid
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.gis.geos import MultiPolygon, Polygon

from background_jobs.models import BackgroundJob
from estimate_updates.models import EstimateUpdate
from national_forest.models import ForestBuild, ForestCell, ForestChunk
from national_grid.models import GridBuild, GridBuildCell, GridCell, GridChunk, GridRegion
from national_grid.subset import prepare_tuscany_subset
from national_terrain.models import (
    TerrainBuild,
    TerrainCell,
    TerrainChunk,
    TerrainChunkSource,
    TerrainSourceTile,
)
from weather_requests.models import WeatherRequest
from national_grid.subset import (
    DestinationNotEmptyError,
    SourceBuildError,
    TuscanySubsetError,
    _ensure_distinct_databases,
    _ensure_empty_target,
    _source_membership_keys,
    _subset_fingerprint,
)


SOURCE_ALIAS = "tuscany_subset_source"
if SOURCE_ALIAS not in settings.DATABASES:
    source_database = copy.deepcopy(settings.DATABASES["default"])
    source_database["NAME"] = f"{source_database['NAME']}_source"
    settings.DATABASES[SOURCE_ALIAS] = source_database


def _square(*, west: int, south: int, size: int = 500) -> Polygon:
    return Polygon(
        [
            (west, south),
            (west + size, south),
            (west + size, south + size),
            (west, south + size),
            (west, south),
        ],
        srid=3035,
    )


@pytest.mark.django_db
def test_tuscany_membership_selection_keeps_only_the_selected_region() -> None:
    build = GridBuild.objects.create(
        version=f"test-grid-{uuid.uuid4()}",
        fingerprint="a" * 64,
        status=GridBuild.Status.COMPLETED,
    )
    tuscany = GridRegion.objects.create(
        build=build,
        istat_code="09",
        name="Toscana",
        geometry=MultiPolygon([_square(west=1_000, south=2_000)]),
    )
    other = GridRegion.objects.create(
        build=build,
        istat_code="10",
        name="Umbria",
        geometry=MultiPolygon([_square(west=2_000, south=2_000)]),
    )
    chunk = GridChunk.objects.create(
        build=build,
        west_e=1_000,
        south_n=2_000,
        east_e=2_500,
        north_n=2_500,
        status=GridChunk.Status.COMPLETED,
    )
    first_cell = GridCell.objects.create(
        cell_id="500m_E1000_N2000",
        corner_e=1_000,
        corner_n=2_000,
        geometry=_square(west=1_000, south=2_000),
    )
    second_cell = GridCell.objects.create(
        cell_id="500m_E1500_N2000",
        corner_e=1_500,
        corner_n=2_000,
        geometry=_square(west=1_500, south=2_000),
    )
    GridBuildCell.objects.create(
        build=build,
        cell=first_cell,
        chunk=chunk,
        owner_region=tuscany,
        land_geometry=MultiPolygon([_square(west=1_000, south=2_000)]),
        land_share=1.0,
    )
    GridBuildCell.objects.create(
        build=build,
        cell=second_cell,
        chunk=chunk,
        owner_region=other,
        land_geometry=MultiPolygon([_square(west=1_500, south=2_000)]),
        land_share=1.0,
    )

    selected = _source_membership_keys(
        alias="default",
        build_id=build.id,
        region_id=tuscany.id,
    )

    assert [row["cell_id"] for row in selected] == [first_cell.cell_id]
    assert selected[0]["owner_region_id"] == tuscany.id


@pytest.mark.django_db
def test_empty_target_rejects_existing_static_or_dynamic_rows() -> None:
    _ensure_empty_target(alias="default")
    GridBuild.objects.create(
        version=f"test-grid-{uuid.uuid4()}",
        fingerprint="b" * 64,
    )

    with pytest.raises(DestinationNotEmptyError, match="national_grid.GridBuild"):
        _ensure_empty_target(alias="default")


def test_source_and_target_aliases_must_not_match() -> None:
    with pytest.raises(TuscanySubsetError, match="aliases must be different"):
        _ensure_distinct_databases(source_alias="default", target_alias="default")


def test_subset_fingerprint_changes_when_version_or_region_changes() -> None:
    first = _subset_fingerprint("c" * 64, "tuscany-grid-a", "09")

    assert first != _subset_fingerprint("c" * 64, "tuscany-grid-b", "09")
    assert first != _subset_fingerprint("c" * 64, "tuscany-grid-a", "10")


@pytest.mark.django_db(transaction=True, databases={"default", SOURCE_ALIAS})
def test_prepare_tuscany_subset_copies_static_rows_and_keeps_source_unchanged(
    tmp_path: Path,
) -> None:
    source = _create_source_fixture(alias=SOURCE_ALIAS)
    source_counts = {
        "grid_builds": GridBuild.objects.using(SOURCE_ALIAS).count(),
        "grid_memberships": GridBuildCell.objects.using(SOURCE_ALIAS).count(),
        "forest_cells": ForestCell.objects.using(SOURCE_ALIAS).count(),
        "terrain_cells": TerrainCell.objects.using(SOURCE_ALIAS).count(),
    }

    result = prepare_tuscany_subset(
        source_alias=SOURCE_ALIAS,
        target_alias="default",
        source_grid_version=source["grid"].version,
        source_forest_version=source["forest"].version,
        source_terrain_version=source["terrain"].version,
        grid_version="tuscany-grid-test",
        forest_version="tuscany-forest-test",
        terrain_version="tuscany-terrain-test",
        output_dir=tmp_path,
    )

    target_grid = GridBuild.objects.get(version="tuscany-grid-test")
    target_forest = ForestBuild.objects.get(version="tuscany-forest-test")
    target_terrain = TerrainBuild.objects.get(version="tuscany-terrain-test")
    target_memberships = GridBuildCell.objects.filter(build=target_grid)
    target_forest_cells = ForestCell.objects.filter(build=target_forest)
    target_terrain_cells = TerrainCell.objects.filter(build=target_terrain)

    assert result.counts["grid_cells"] == 2
    assert target_grid.cell_count == 2
    assert target_memberships.count() == 2
    assert target_memberships.exclude(owner_region__istat_code="09").count() == 0
    assert target_forest.cell_count == 2
    assert target_forest.forest_cell_count == 2
    assert target_forest.weather_cell_count == 1
    assert target_forest.source_gap_count == 1
    assert target_forest.chunks.get().cell_count == 2
    assert target_terrain.result_count == 2
    assert target_terrain.source_gap_count == 1
    assert target_terrain.chunks.get().result_count == 2
    assert target_forest_cells.count() == 2
    assert target_terrain_cells.count() == 2
    assert list(
        target_forest_cells.values_list("forest_share", flat=True).order_by("id")
    ) == [0.8, 0.8]
    assert target_terrain_cells.values_list("altitude_m", flat=True).order_by("id").first() == 123.5
    assert target_forest.layer_path == str(result.layer_path)
    assert Path(result.layer_path).is_file()
    assert TerrainSourceTile.objects.filter(build=target_terrain).count() == 1
    assert BackgroundJob.objects.count() == 0
    assert EstimateUpdate.objects.count() == 0
    assert WeatherRequest.objects.count() == 0
    assert source_counts == {
        "grid_builds": GridBuild.objects.using(SOURCE_ALIAS).count(),
        "grid_memberships": GridBuildCell.objects.using(SOURCE_ALIAS).count(),
        "forest_cells": ForestCell.objects.using(SOURCE_ALIAS).count(),
        "terrain_cells": TerrainCell.objects.using(SOURCE_ALIAS).count(),
    }
    assert not ForestBuild.objects.filter(version=source["forest"].version).exists()
    assert not TerrainBuild.objects.filter(version=source["terrain"].version).exists()


@pytest.mark.parametrize("missing_kind", ["forest", "terrain"])
@pytest.mark.django_db(transaction=True, databases={"default", SOURCE_ALIAS})
def test_prepare_tuscany_subset_rejects_missing_habitat_rows_without_partial_target(
    missing_kind: str,
    tmp_path: Path,
) -> None:
    source = _create_source_fixture(alias=SOURCE_ALIAS)
    if missing_kind == "forest":
        ForestCell.objects.using(SOURCE_ALIAS).filter(build=source["forest"]).first().delete()
    else:
        TerrainCell.objects.using(SOURCE_ALIAS).filter(build=source["terrain"]).first().delete()

    with pytest.raises(SourceBuildError, match="exactly cover"):
        prepare_tuscany_subset(
            source_alias=SOURCE_ALIAS,
            target_alias="default",
            source_grid_version=source["grid"].version,
            source_forest_version=source["forest"].version,
            source_terrain_version=source["terrain"].version,
            grid_version=f"tuscany-grid-missing-{missing_kind}",
            forest_version=f"tuscany-forest-missing-{missing_kind}",
            terrain_version=f"tuscany-terrain-missing-{missing_kind}",
            output_dir=tmp_path,
        )

    assert GridBuild.objects.count() == 0
    assert ForestBuild.objects.count() == 0
    assert TerrainBuild.objects.count() == 0
    assert GridBuildCell.objects.count() == 0


def _create_source_fixture(*, alias: str) -> dict[str, object]:
    manager = lambda model: model.objects.using(alias)
    grid = manager(GridBuild).create(
        version=f"source-grid-{uuid.uuid4()}",
        fingerprint="d" * 64,
        status=GridBuild.Status.COMPLETED,
        planned_chunk_count=1,
        completed_chunk_count=1,
        cell_count=3,
    )
    tuscany = manager(GridRegion).create(
        build=grid,
        istat_code="09",
        name="Toscana",
        geometry=MultiPolygon([_square(west=1_000, south=2_000)]),
    )
    other = manager(GridRegion).create(
        build=grid,
        istat_code="10",
        name="Umbria",
        geometry=MultiPolygon([_square(west=3_000, south=2_000)]),
    )
    grid_chunk = manager(GridChunk).create(
        build=grid,
        west_e=1_000,
        south_n=2_000,
        east_e=3_500,
        north_n=2_500,
        status=GridChunk.Status.COMPLETED,
        cell_count=3,
    )
    cells = [
        manager(GridCell).create(
            cell_id=f"500m_E{west}_N2000",
            corner_e=west,
            corner_n=2_000,
            geometry=_square(west=west, south=2_000),
        )
        for west in (1_000, 1_500, 3_000)
    ]
    memberships = [
        manager(GridBuildCell).create(
            build=grid,
            cell=cell,
            chunk=grid_chunk,
            owner_region=tuscany if index < 2 else other,
            land_geometry=MultiPolygon([_square(west=cell.corner_e, south=2_000)]),
            land_share=1.0,
        )
        for index, cell in enumerate(cells)
    ]
    forest = manager(ForestBuild).create(
        version=f"source-forest-{uuid.uuid4()}",
        grid_build=grid,
        fingerprint="e" * 64,
        status=ForestBuild.Status.COMPLETED,
        planned_chunk_count=1,
        completed_chunk_count=1,
        cell_count=3,
        forest_cell_count=3,
        weather_cell_count=1,
    )
    forest_chunk = manager(ForestChunk).create(
        build=forest,
        grid_chunk=grid_chunk,
        west_e=1_000,
        south_n=2_000,
        east_e=3_500,
        north_n=2_500,
        status=ForestChunk.Status.COMPLETED,
        cell_count=3,
        source_sha256="f" * 64,
        source_path="/tmp/source.tif",
        source_metadata={"source": "fixture"},
    )
    for index, membership in enumerate(memberships):
        manager(ForestCell).create(
            build=forest,
            grid_build_cell=membership,
            chunk=forest_chunk,
            total_pixel_count=100,
            valid_pixel_count=100,
            forest_pixel_count=80 if index < 2 else 0,
            broadleaf_pixel_count=80 if index < 2 else 0,
            conifer_pixel_count=0,
            unclassifiable_pixel_count=0,
            outside_pixel_count=0,
            valid_coverage=0.8 if index == 1 else 1.0,
            coverage_quality="high",
            forest_share=0.8 if index < 2 else 0.0,
            broadleaf_share=1.0 if index < 2 else 0.0,
            leaf_type=ForestCell.LeafType.BROADLEAF if index < 2 else ForestCell.LeafType.NO_FOREST,
            is_forest=index < 2,
            weather_latitude=43.5 if index < 2 else None,
            weather_longitude=11.2 if index < 2 else None,
        )
    terrain = manager(TerrainBuild).create(
        version=f"source-terrain-{uuid.uuid4()}",
        grid_build=grid,
        fingerprint="1" * 64,
        grid_fingerprint=grid.fingerprint,
        status=TerrainBuild.Status.COMPLETED,
        planned_chunk_count=1,
        completed_chunk_count=1,
        result_count=3,
        source_gap_count=1,
    )
    terrain_chunk = manager(TerrainChunk).create(
        build=terrain,
        grid_chunk=grid_chunk,
        status=TerrainChunk.Status.COMPLETED,
        result_count=3,
        source_gap_count=1,
    )
    tile = manager(TerrainSourceTile).create(
        build=terrain,
        tile_name="fixture.tif",
        status=TerrainSourceTile.Status.AVAILABLE,
        url="https://example.invalid/fixture.tif",
        release="fixture",
        credit="fixture",
    )
    manager(TerrainChunkSource).create(chunk=terrain_chunk, tile=tile)
    for index, membership in enumerate(memberships):
        manager(TerrainCell).create(
            build=terrain,
            grid_build_cell=membership,
            chunk=terrain_chunk,
            altitude_m=123.5 if index == 0 else 200.0,
            slope_deg=5.0,
            aspect_deg=10.0,
            altitude_valid_fraction=1.0,
            slope_valid_fraction=1.0,
            aspect_valid_fraction=1.0,
            source_gap=index == 1,
            source_gap_detail="fixture gap" if index == 1 else "",
        )
    return {"grid": grid, "forest": forest, "terrain": terrain}
