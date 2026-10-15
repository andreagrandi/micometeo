"""Check and prepare the stored geographic inputs for Tuscany estimates.

Grid, forest and terrain are only checked. Host-tree values are sampled once per source version.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction

from sporameteo.host_trees import checksum, prepare_sources, read_manifest, sample_squares
from national_forest import layer
from national_forest.models import ForestBuild, ForestCell, ForestChunk
from national_grid.models import GridBuild, GridBuildCell, GridRegion
from national_grid.subset import TUSCANY_ISTAT_CODE
from national_terrain.models import TerrainBuild, TerrainCell, TerrainSourceTile
from national_terrain.source import raster_path, sha256_path

from .models import HostTreeCache, TuscanyInputSet


REPOSITORY_ROOT = Path(settings.BASE_DIR).parent.parent
SKIPPED_SOURCE_FILES = "Source files were not checked."
BATCH_SIZE = 5_000
SAMPLE_LIMIT = 5
READY = "ready"
MISSING = "missing"
INCOMPLETE = "incomplete"
CORRUPT = "corrupt"
REJECTED = "rejected"
FALLBACK = "fallback"
BLOCKED = "blocked"
PREPARE_DATABASE = (
    "Run prepare_tuscany_map_database to build the Tuscany subset database. "
    "This command does not rebuild it."
)


@dataclass
class SourceStatus:
    """Describe one source: its state, version, required action and affected area."""

    source: str
    state: str
    version: str
    action: str
    detail: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.state not in {READY, FALLBACK}


@dataclass
class TuscanyReport:
    """Hold the inventory of all four sources and the preparation counts."""

    region_code: str
    dry_run: bool
    sources: list[SourceStatus]
    counts: dict[str, int] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    @property
    def failures(self) -> list[SourceStatus]:
        return [item for item in self.sources if item.failed]

    @property
    def ready(self) -> bool:
        return not self.failures

    def as_dict(self) -> dict[str, Any]:
        return {
            "region_code": self.region_code,
            "dry_run": self.dry_run,
            "ready": self.ready,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "counts": self.counts,
            "sources": [asdict(item) for item in self.sources],
        }


def _sample(values: list[str]) -> list[str]:
    shown = ", ".join(values[:SAMPLE_LIMIT])
    return [f"{shown} and {len(values) - SAMPLE_LIMIT} more" if len(values) > SAMPLE_LIMIT else shown]


def _check_grid(*, forest: ForestBuild | None) -> SourceStatus:
    if forest is None:
        return SourceStatus(
            source="administrative_geometry", state=MISSING, version="",
            action="The configured forest build is missing, so the grid cannot be identified. " + PREPARE_DATABASE,
        )
    grid = forest.grid_build
    result = SourceStatus(source="administrative_geometry", state=READY, version=grid.version, action="None.")

    def fail(*, state: str, detail: str, action: str = PREPARE_DATABASE) -> SourceStatus:
        result.state, result.action = state, action
        result.detail.append(detail)
        return result

    if grid.status != GridBuild.Status.COMPLETED:
        return fail(state=INCOMPLETE, detail=f"Grid build {grid.version} is {grid.status}, not completed.")
    regions = list(GridRegion.objects.filter(build=grid).values_list("istat_code", flat=True))
    if regions != [TUSCANY_ISTAT_CODE]:
        return fail(
            state=REJECTED,
            detail=f"The grid has regions {sorted(regions)}. This command works only with region {TUSCANY_ISTAT_CODE}.",
        )
    memberships = GridBuildCell.objects.filter(build=grid)
    outside = memberships.exclude(owner_region__istat_code=TUSCANY_ISTAT_CODE).count()
    if outside:
        return fail(state=REJECTED, detail=f"{outside} grid squares belong to a region other than {TUSCANY_ISTAT_CODE}.")
    count = memberships.count()
    result.counts["squares"] = count
    if count != grid.cell_count:
        return fail(state=INCOMPLETE, detail=f"The grid has {count} squares but its build records {grid.cell_count}.")
    return result


def _missing_rows(*, grid: GridBuild, model: type, build: Any) -> list[str]:
    rows = model.objects.filter(build=build).values("grid_build_cell_id")
    return list(
        GridBuildCell.objects.filter(build=grid).exclude(id__in=rows)
        .order_by("cell_id").values_list("cell_id", flat=True)
    )


def _check_forest(*, forest: ForestBuild | None, version: str, grid: SourceStatus, check_source_files: bool = True) -> SourceStatus:
    action = "Run prepare_tuscany_map_database, or build_national_forest for the national build."
    if forest is None:
        return SourceStatus(
            source="forest", state=MISSING, version=version, action=action,
            detail=[f"No forest build named {version} exists."],
        )
    result = SourceStatus(source="forest", state=READY, version=forest.version, action="None.")

    def fail(*, state: str, detail: str) -> SourceStatus:
        result.state, result.action = state, action
        result.detail.append(detail)
        return result

    if forest.status != ForestBuild.Status.COMPLETED:
        return fail(state=INCOMPLETE, detail=f"Forest build {forest.version} is {forest.status}, not completed.")
    if grid.state != READY:
        return fail(state=BLOCKED, detail="The grid used by this forest build is not ready.")
    missing = _missing_rows(grid=forest.grid_build, model=ForestCell, build=forest)
    result.counts["missing_squares"] = len(missing)
    if missing:
        return fail(state=INCOMPLETE, detail=f"{len(missing)} squares have no forest row: " + _sample(missing)[0])
    if not forest.layer_path:
        return fail(state=MISSING, detail="The forest build has no layer file.")
    layer_path = layer.resolve_layer_path(value=forest.layer_path)
    if not layer_path.is_file():
        return fail(state=MISSING, detail=f"Layer file {layer_path} is missing.")
    try:
        found = layer.validate_layer(path=layer_path)["sha256"]
    except ValueError as exc:
        return fail(state=CORRUPT, detail=f"Layer file {layer_path} is damaged: {exc}")
    if found != forest.layer_sha256:
        return fail(state=CORRUPT, detail=f"Layer file {layer_path} changed since the build.")
    if not check_source_files:
        result.detail.append(SKIPPED_SOURCE_FILES)
        return result
    for chunk in ForestChunk.objects.filter(build=forest).exclude(source_path="").order_by("west_e", "south_n"):
        area = f"chunk at E{chunk.west_e} N{chunk.south_n}"
        # Forest builds store cache paths relative to the repository root.
        path = REPOSITORY_ROOT / chunk.source_path
        if not path.is_file():
            return fail(state=MISSING, detail=f"Source file {path} for {area} is missing.")
        if chunk.source_sha256 and sha256_path(path=path) != chunk.source_sha256:
            return fail(state=CORRUPT, detail=f"Source file {path} for {area} changed since the build.")
    return result


def _check_terrain(*, terrain: TerrainBuild | None, version: str, grid: SourceStatus, forest: ForestBuild | None, cache_dir: Path, check_source_files: bool = True) -> SourceStatus:
    action = "Run prepare_tuscany_map_database, or build_national_terrain for the national build."
    if terrain is None:
        return SourceStatus(
            source="terrain", state=MISSING, version=version, action=action,
            detail=[f"No terrain build named {version} exists."],
        )
    result = SourceStatus(source="terrain", state=READY, version=terrain.version, action="None.")

    def fail(*, state: str, detail: str) -> SourceStatus:
        result.state, result.action = state, action
        result.detail.append(detail)
        return result

    if terrain.status != TerrainBuild.Status.COMPLETED:
        return fail(state=INCOMPLETE, detail=f"Terrain build {terrain.version} is {terrain.status}, not completed.")
    if grid.state != READY or forest is None or terrain.grid_build_id != forest.grid_build_id:
        return fail(state=BLOCKED, detail="The terrain build does not use the same ready grid as the forest build.")
    missing = _missing_rows(grid=terrain.grid_build, model=TerrainCell, build=terrain)
    result.counts["missing_squares"] = len(missing)
    if missing:
        return fail(state=INCOMPLETE, detail=f"{len(missing)} squares have no terrain row: " + _sample(missing)[0])
    if not check_source_files:
        result.detail.append(SKIPPED_SOURCE_FILES)
        return result
    tiles = TerrainSourceTile.objects.filter(
        build=terrain, status=TerrainSourceTile.Status.AVAILABLE,
    ).order_by("tile_name")
    for tile in tiles:
        path = raster_path(cache_dir=cache_dir, tile_name=tile.tile_name)
        if not path.is_file():
            return fail(state=MISSING, detail=f"Terrain tile {tile.tile_name} is missing at {path}.")
        if tile.sha256 and sha256_path(path=path) != tile.sha256:
            return fail(state=CORRUPT, detail=f"Terrain tile {tile.tile_name} at {path} changed since the build.")
    return result


def eligible_squares(*, forest: ForestBuild) -> dict[str, tuple[float, float]]:
    """Return the centre of every forest square in the build, keyed by grid cell id.
    These are the squares that estimates can ask host-tree values for."""
    rows = ForestCell.objects.filter(build=forest, is_forest=True).values_list(
        "grid_build_cell__cell__cell_id", "grid_build_cell__cell__corner_e", "grid_build_cell__cell__corner_n",
    )
    return {cell_id: (east + 250.0, north + 250.0) for cell_id, east, north in rows.iterator(chunk_size=BATCH_SIZE)}


def _check_host_trees(*, forest: ForestBuild | None, ready: bool, directory: Path, allow_forest_only: bool) -> tuple[SourceStatus, dict | None, dict[str, tuple[float, float]]]:
    """Return the host-tree status, the manifest if readable and the squares needing values."""
    result = SourceStatus(source="host_trees", state=READY, version="", action="None.")
    if forest is None or not ready:
        result.state = BLOCKED
        result.action = "Fix the sources above first."
        return result, None, {}
    squares = eligible_squares(forest=forest)
    result.counts["eligible_squares"] = len(squares)
    problem = ""
    state = MISSING
    manifest = None
    try:
        selected = read_manifest(directory=directory)
        if selected is None:
            problem = f"No JRC manifest in {directory}."
        else:
            manifest, version = selected
            result.version = version
            for record in manifest["files"]:
                path = directory / record["filename"]
                if not path.is_file():
                    problem = f"JRC file {path} is missing."
                    break
                if checksum(path=path) != record["sha256"]:
                    state, problem = CORRUPT, f"JRC file {path} changed since it was downloaded."
                    break
    except (OSError, ValueError, KeyError) as exc:
        state, problem = CORRUPT, f"The JRC manifest in {directory} is not usable: {exc}"
    if problem:
        if allow_forest_only:
            result.state = FALLBACK
            result.action = "Estimates use forest only, without host-tree evidence. Prepare JRC files later to add it."
        else:
            result.state = state
            result.action = (
                "Run prepare_tuscany_inputs to download the JRC files." if manifest is None and state == MISSING
                else "Restore the JRC files or prepare a new JRC directory, then run prepare_tuscany_inputs."
            )
        result.detail.append(problem)
        return result, None, {}
    stored = set(
        HostTreeCache.objects.filter(source_version=result.version).values_list("cell_id", flat=True).iterator(chunk_size=BATCH_SIZE)
    )
    needed = {key: value for key, value in squares.items() if key not in stored}
    result.counts["missing_squares"] = len(needed)
    if needed:
        result.state = INCOMPLETE
        result.action = "Run prepare_tuscany_inputs to sample the missing squares from the local JRC files."
        result.detail.append(f"{len(needed)} squares have no host-tree values: " + _sample(sorted(needed))[0])
    return result, manifest, needed


def build_inventory(*, terrain_cache_dir: Path, allow_forest_only: bool = False, check_source_files: bool = True) -> tuple[TuscanyReport, dict | None, dict[str, tuple[float, float]]]:
    """Check each source without writing or contacting a provider.
    Also return the manifest and the squares that still need host-tree values."""
    forest = ForestBuild.objects.filter(version=settings.SPORAMETEO_FOREST_BUILD_VERSION).select_related("grid_build").first()
    terrain = TerrainBuild.objects.filter(version=settings.SPORAMETEO_TERRAIN_BUILD_VERSION).first()
    grid = _check_grid(forest=forest)
    forest_status = _check_forest(forest=forest, version=settings.SPORAMETEO_FOREST_BUILD_VERSION, grid=grid, check_source_files=check_source_files)
    terrain_status = _check_terrain(
        terrain=terrain, version=settings.SPORAMETEO_TERRAIN_BUILD_VERSION, grid=grid,
        forest=forest, cache_dir=terrain_cache_dir, check_source_files=check_source_files,
    )
    trees, manifest, needed = _check_host_trees(
        forest=forest, ready=grid.state == READY and forest_status.state == READY,
        directory=Path(settings.SPORAMETEO_JRC_DIRECTORY), allow_forest_only=allow_forest_only,
    )
    report = TuscanyReport(
        region_code=TUSCANY_ISTAT_CODE, dry_run=True, sources=[grid, forest_status, terrain_status, trees],
    )
    return report, manifest, needed


def _store_host_trees(*, manifest: dict, version: str, needed: dict[str, tuple[float, float]]) -> None:
    directory = Path(settings.SPORAMETEO_JRC_DIRECTORY)
    keys = sorted(needed)
    for start in range(0, len(keys), BATCH_SIZE):
        centres = {key: needed[key] for key in keys[start:start + BATCH_SIZE]}
        sampled = sample_squares(directory=directory, manifest=manifest, version=version, centres=centres)
        HostTreeCache.objects.bulk_create(
            [HostTreeCache(source_version=version, cell_id=key, values=list(value.values)) for key, value in sampled.items()],
            ignore_conflicts=True,
        )


def prepare_tuscany_inputs(*, terrain_cache_dir: Path, dry_run: bool = False, allow_forest_only: bool = False, check_source_files: bool = True) -> TuscanyReport:
    """Report readiness and, unless dry, store host-tree values for every eligible square.
    Only a missing JRC manifest triggers a download. Older source versions stay untouched."""
    started = time.monotonic()
    report, manifest, needed = build_inventory(terrain_cache_dir=terrain_cache_dir, allow_forest_only=allow_forest_only, check_source_files=check_source_files)
    report.dry_run = dry_run
    trees = report.sources[3]
    if not dry_run and all(item.state == READY for item in report.sources[:3]):
        directory = Path(settings.SPORAMETEO_JRC_DIRECTORY)
        if trees.state == MISSING and manifest is None and not trees.version:
            prepare_sources(directory=directory)
            report, manifest, needed = build_inventory(terrain_cache_dir=terrain_cache_dir, allow_forest_only=allow_forest_only, check_source_files=check_source_files)
            report.dry_run = False
            trees = report.sources[3]
        if trees.state in {INCOMPLETE, READY} and manifest is not None:
            _store_host_trees(manifest=manifest, version=trees.version, needed=needed)
            report, _, _ = build_inventory(terrain_cache_dir=terrain_cache_dir, allow_forest_only=allow_forest_only, check_source_files=check_source_files)
            report.dry_run = False
            trees = report.sources[3]
            if report.ready:
                _record_provenance(report=report, manifest=manifest)
    report.counts = {
        "eligible_squares": trees.counts.get("eligible_squares", 0),
        "missing_host_tree_squares": trees.counts.get("missing_squares", 0),
        "tuscany_squares": report.sources[0].counts.get("squares", 0),
        "input_sets": TuscanyInputSet.objects.count(),
        "host_tree_rows": HostTreeCache.objects.filter(source_version=trees.version).count() if trees.version else 0,
    }
    report.elapsed_seconds = time.monotonic() - started
    return report


def _record_provenance(*, report: TuscanyReport, manifest: dict) -> None:
    grid, forest, terrain, trees = report.sources
    with transaction.atomic():
        TuscanyInputSet.objects.get_or_create(
            region_code=TUSCANY_ISTAT_CODE, grid_build_version=grid.version,
            forest_build_version=forest.version, terrain_build_version=terrain.version,
            host_tree_source_version=trees.version,
            defaults={
                "jrc_manifest": manifest,
                "eligible_square_count": trees.counts["eligible_squares"],
                "host_tree_row_count": HostTreeCache.objects.filter(source_version=trees.version).count(),
            },
        )
