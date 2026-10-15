"""Build and resume bounded terrain chunks for a completed national grid."""

from __future__ import annotations

import hashlib
import json
import resource
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from sporameteo.finds.grid import CELL_SIZE_M
from sporameteo.habitat import terrain

from national_grid.models import GridBuild, GridBuildCell

from .models import TerrainBuild, TerrainCell, TerrainChunk, TerrainChunkSource, TerrainSourceTile
from .source import CachedTile, TerrainSourceError, cache_tile, manifest_fingerprint


QUALITY_SETTINGS = {"flat_slope_deg": 5.0, "min_resultant_length": 0.3}
ALGORITHM_VERSION = terrain.ALGORITHM_VERSION
SOURCE_IDENTITY_FIELDS = (
    "url",
    "release",
    "last_modified",
    "retrieved_at",
    "size_bytes",
    "sha256",
    "crs",
    "native_pixel_m",
    "vertical_datum",
)


class IncompleteGridBuildError(ValueError):
    """Report an attempt to process a grid that is not complete."""


class TerrainBuildInputMismatchError(ValueError):
    """Report an attempt to reuse a version with different inputs."""


@dataclass(frozen=True)
class TerrainBuildResult:
    """Expose terrain build state, counts and cache use."""

    build: TerrainBuild
    processed_chunks: int
    reused_chunks: int
    downloaded_tiles: int
    reused_tiles: int
    elapsed_seconds: float
    peak_rss_mb: float
    regional_counts: list[dict[str, Any]]
    cache_bytes: int

    @property
    def status(self) -> str:
        return self.build.status

    def as_dict(self) -> dict[str, Any]:
        chunks = list(self.build.chunks.all())
        return {
            "build_id": str(self.build.id),
            "build_version": self.build.version,
            "status": self.build.status,
            "result_count": self.build.result_count,
            "source_gap_count": self.build.source_gap_count,
            "planned_chunk_count": self.build.planned_chunk_count,
            "completed_chunk_count": self.build.completed_chunk_count,
            "processed_chunks": self.processed_chunks,
            "reused_chunks": self.reused_chunks,
            "downloaded_tiles": self.downloaded_tiles,
            "reused_tiles": self.reused_tiles,
            "downloaded_bytes": sum(chunk.downloaded_bytes for chunk in chunks),
            "reused_bytes": sum(chunk.reused_bytes for chunk in chunks),
            "cache_bytes": self.cache_bytes,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "peak_rss_mb": round(self.peak_rss_mb, 1),
            "regional_counts": self.regional_counts,
        }


def terrain_fingerprint(
    *,
    grid_fingerprint: str,
    algorithm_version: str = ALGORITHM_VERSION,
    source_release: str = terrain.SOURCE_RELEASE,
    source_url: str = terrain.SOURCE_URL,
    processing_pixel_m: int = terrain.PROCESSING_PIXEL_M,
    margin_pixels: int = terrain.MARGIN_PIXELS,
    quality_settings: dict[str, float] = QUALITY_SETTINGS,
) -> str:
    """Hash every input that can change stored terrain values."""
    inputs = {
        "grid_fingerprint": grid_fingerprint,
        "algorithm_version": algorithm_version,
        "source_release": source_release,
        "source_url": source_url,
        "processing_pixel_m": processing_pixel_m,
        "resampling": "bilinear",
        "reprojection_method": terrain.REPROJECT_METHOD,
        "margin_pixels": margin_pixels,
        "quality_settings": quality_settings,
    }
    return hashlib.sha256(
        json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_national_terrain(
    *,
    grid_build_version: str,
    build_version: str,
    cache_dir: Path,
    max_chunks: int | None = None,
    quality_settings: dict[str, float] = QUALITY_SETTINGS,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> TerrainBuildResult:
    """Create or resume a terrain build, committing each chunk atomically."""
    started = time.monotonic()
    grid_build = _completed_grid_build(version=grid_build_version)
    fingerprint = terrain_fingerprint(
        grid_fingerprint=grid_build.fingerprint,
        quality_settings=quality_settings,
    )
    source_metadata = {
        "dataset": terrain.LAYER_ID,
        "release": terrain.SOURCE_RELEASE,
        "source_url": terrain.SOURCE_URL,
        "source_readme": terrain.SOURCE_README_URL,
        "source_dataset": terrain.SOURCE_DATASET_URL,
        "crs": terrain.SOURCE_CRS,
        "vertical_datum": terrain.SOURCE_VERTICAL_DATUM,
        "native_pixel_m": terrain.SOURCE_NATIVE_PIXEL_M,
        "processing_pixel_m": terrain.PROCESSING_PIXEL_M,
        "resampling": "bilinear",
        "reprojection_method": terrain.REPROJECT_METHOD,
        "margin_pixels": terrain.MARGIN_PIXELS,
        "quality_settings": quality_settings,
        "credit": terrain.LICENCE,
    }
    build, created = _get_or_create_build(
        grid_build=grid_build,
        build_version=build_version,
        fingerprint=fingerprint,
        source_metadata=source_metadata,
    )
    if not created and build.fingerprint != fingerprint:
        raise TerrainBuildInputMismatchError(
            f"Terrain build version {build_version!r} already exists with different inputs."
        )
    if build.status == TerrainBuild.Status.COMPLETED:
        return _result(
            build=build,
            cache_dir=cache_dir,
            processed_chunks=0,
            reused_chunks=build.completed_chunk_count,
            downloaded_tiles=0,
            reused_tiles=0,
            started=started,
        )

    _prepare_build(build=build, grid_build=grid_build)
    completed_before = TerrainChunk.objects.filter(
        build=build, status=TerrainChunk.Status.COMPLETED
    ).count()
    processed = 0
    downloaded_tiles = 0
    reused_tiles = 0
    for chunk in (
        TerrainChunk.objects.filter(build=build)
        .select_related("grid_chunk")
        .order_by("grid_chunk__south_n", "grid_chunk__west_e")
    ):
        if chunk.status == TerrainChunk.Status.COMPLETED:
            continue
        if max_chunks is not None and processed >= max_chunks:
            break
        downloaded, reused = _process_chunk(
            build=build,
            chunk=chunk,
            cache_dir=cache_dir,
            quality_settings=quality_settings,
        )
        downloaded_tiles += downloaded
        reused_tiles += reused
        processed += 1
        build.refresh_from_db()
        chunk.refresh_from_db(
            fields=["downloaded_bytes", "reused_bytes", "result_count", "source_gap_count"]
        )
        if progress_callback is not None:
            progress_callback(
                {
                    "build_version": build.version,
                    "status": "chunk_completed",
                    "terrain_chunk_id": str(chunk.id),
                    "completed_chunk_count": build.completed_chunk_count,
                    "planned_chunk_count": build.planned_chunk_count,
                    "result_count": build.result_count,
                    "source_gap_count": build.source_gap_count,
                    "downloaded_tiles": downloaded,
                    "reused_tiles": reused,
                    "downloaded_bytes": chunk.downloaded_bytes,
                    "reused_bytes": chunk.reused_bytes,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "peak_rss_mb": round(_peak_rss_mb(), 1),
                }
            )
    _finalise_build(build=build)
    build.refresh_from_db()
    return _result(
        build=build,
        cache_dir=cache_dir,
        processed_chunks=processed,
        reused_chunks=completed_before,
        downloaded_tiles=downloaded_tiles,
        reused_tiles=reused_tiles,
        started=started,
    )


def _completed_grid_build(*, version: str) -> GridBuild:
    try:
        build = GridBuild.objects.get(version=version)
    except GridBuild.DoesNotExist as exc:
        raise IncompleteGridBuildError(f"Grid build {version!r} does not exist.") from exc
    if build.status != GridBuild.Status.COMPLETED:
        raise IncompleteGridBuildError(f"Grid build {version!r} is not completed.")
    if build.cell_count != GridBuildCell.objects.filter(build=build).count():
        raise IncompleteGridBuildError(f"Grid build {version!r} has an inconsistent cell count.")
    if build.completed_chunk_count != build.planned_chunk_count:
        raise IncompleteGridBuildError(f"Grid build {version!r} has unfinished chunks.")
    return build


def _get_or_create_build(
    *,
    grid_build: GridBuild,
    build_version: str,
    fingerprint: str,
    source_metadata: dict[str, Any],
) -> tuple[TerrainBuild, bool]:
    with transaction.atomic():
        existing = TerrainBuild.objects.select_for_update().filter(version=build_version).first()
        if existing is not None:
            if existing.grid_build_id != grid_build.id:
                raise TerrainBuildInputMismatchError(
                    f"Terrain build version {build_version!r} belongs to another grid build."
                )
            return existing, False
        try:
            with transaction.atomic():
                build = TerrainBuild.objects.create(
                    version=build_version,
                    grid_build=grid_build,
                    algorithm_version=ALGORITHM_VERSION,
                    fingerprint=fingerprint,
                    grid_fingerprint=grid_build.fingerprint,
                    source_metadata=source_metadata,
                    started_at=timezone.now(),
                )
        except IntegrityError:
            winner = TerrainBuild.objects.select_for_update().get(version=build_version)
            if winner.grid_build_id != grid_build.id:
                raise TerrainBuildInputMismatchError(
                    f"Terrain build version {build_version!r} belongs to another grid build."
                )
            return winner, False
        return build, True


def _prepare_build(*, build: TerrainBuild, grid_build: GridBuild) -> None:
    grid_chunks = list(grid_build.chunks.order_by("south_n", "west_e"))
    if any(chunk.status != chunk.Status.COMPLETED for chunk in grid_chunks):
        raise IncompleteGridBuildError("Every grid chunk must be completed before terrain processing.")
    with transaction.atomic():
        locked_build = TerrainBuild.objects.select_for_update().get(id=build.id)
        locked_build.planned_chunk_count = len(grid_chunks)
        locked_build.status = TerrainBuild.Status.RUNNING
        locked_build.started_at = locked_build.started_at or timezone.now()
        locked_build.save(
            update_fields=["planned_chunk_count", "status", "started_at", "updated_at"]
        )
        TerrainChunk.objects.bulk_create(
            [TerrainChunk(build=locked_build, grid_chunk=grid_chunk) for grid_chunk in grid_chunks],
            ignore_conflicts=True,
        )
        _update_build_progress(build=locked_build)


def _process_chunk(
    *,
    build: TerrainBuild,
    chunk: TerrainChunk,
    cache_dir: Path,
    quality_settings: dict[str, float],
) -> tuple[int, int]:
    grid_chunk = chunk.grid_chunk
    window = terrain.ProcessingWindow(
        west_e=grid_chunk.west_e,
        south_n=grid_chunk.south_n,
        east_e=grid_chunk.east_e,
        north_n=grid_chunk.north_n,
    )
    bounds = terrain.source_bounds_for_window(window=window)
    names = terrain.tile_names(west=bounds[0], south=bounds[1], east=bounds[2], north=bounds[3])
    cached: list[CachedTile] = []
    failed_name = ""
    try:
        for name in names:
            failed_name = name
            cached.append(cache_tile(tile_name=name, cache_dir=cache_dir))
    except TerrainSourceError as exc:
        with transaction.atomic():
            _record_source_failure(
                build=build,
                tile_name=failed_name,
                error=str(exc),
            )
            locked = TerrainChunk.objects.select_for_update().get(id=chunk.id)
            locked.status = TerrainChunk.Status.FAILED
            locked.last_error = str(exc)
            locked.save(update_fields=["status", "last_error", "updated_at"])
        raise
    paths = [item.path for item in cached if item.path is not None]
    missing = [item.tile_name for item in cached if item.status == "confirmed_missing"]
    _validate_source_tiles(build=build, cached=cached)
    summaries = _summaries(
        paths=paths,
        window=window,
        quality_settings=quality_settings,
    )
    memberships = list(
        GridBuildCell.objects.filter(build=build.grid_build, chunk=grid_chunk)
        .select_related("cell")
        .order_by("cell__corner_n", "cell__corner_e")
    )
    memberships.sort(key=lambda item: (-item.cell.corner_n, item.cell.corner_e))
    summaries = _summaries_for_memberships(
        summaries=summaries,
        memberships=memberships,
        chunk=grid_chunk,
    )
    gap_detail = (
        ", ".join(missing)
        if missing
        else "No valid elevation pixels in the source window."
    )
    for row in summaries:
        if row["source_gap"]:
            row["source_gap_detail"] = gap_detail
    with transaction.atomic():
        locked_chunk = TerrainChunk.objects.select_for_update().get(id=chunk.id)
        if locked_chunk.status == TerrainChunk.Status.COMPLETED:
            return 0, len(cached)
        locked_chunk.status = TerrainChunk.Status.RUNNING
        locked_chunk.started_at = locked_chunk.started_at or timezone.now()
        locked_chunk.save(update_fields=["status", "started_at", "updated_at"])
        source_tiles = []
        for item in cached:
            tile = _get_or_create_source_tile(
                build=build,
                tile_name=item.tile_name,
                item=item,
            )
            source_tiles.append(tile)
        TerrainChunkSource.objects.bulk_create(
            [TerrainChunkSource(chunk=locked_chunk, tile=tile) for tile in source_tiles],
            ignore_conflicts=True,
        )
        TerrainCell.objects.bulk_create(
            [
                TerrainCell(
                    build=build,
                    grid_build_cell_id=membership.id,
                    chunk=locked_chunk,
                    altitude_m=summary["altitude_m"],
                    slope_deg=summary["slope_deg"],
                    aspect_deg=summary["aspect_deg"],
                    altitude_valid_fraction=summary["altitude_m_valid_fraction"],
                    slope_valid_fraction=summary["slope_deg_valid_fraction"],
                    aspect_valid_fraction=summary["aspect_deg_valid_fraction"],
                    altitude_quality=summary["altitude_m_reliability"] or "",
                    slope_quality=summary["slope_deg_reliability"] or "",
                    aspect_quality=summary["aspect_deg_reliability"] or "",
                    source_gap=summary["source_gap"],
                    source_gap_detail=summary.get("source_gap_detail", ""),
                )
                for membership, summary in zip(memberships, summaries, strict=True)
            ],
            ignore_conflicts=True,
        )
        result_count = TerrainCell.objects.filter(chunk=locked_chunk).count()
        gap_count = TerrainCell.objects.filter(chunk=locked_chunk, source_gap=True).count()
        downloaded_tile_count = sum(not item.reused for item in cached)
        reused_tile_count = sum(item.reused for item in cached)
        downloaded_bytes = sum(
            int(item.metadata.get("size_bytes") or 0) for item in cached if not item.reused
        )
        reused_bytes = sum(
            int(item.metadata.get("size_bytes") or 0) for item in cached if item.reused
        )
        locked_chunk.result_count = result_count
        locked_chunk.source_gap_count = gap_count
        locked_chunk.downloaded_tile_count = downloaded_tile_count
        locked_chunk.reused_tile_count = reused_tile_count
        locked_chunk.downloaded_bytes = downloaded_bytes
        locked_chunk.reused_bytes = reused_bytes
        locked_chunk.source_bytes = downloaded_bytes + reused_bytes
        locked_chunk.status = TerrainChunk.Status.COMPLETED
        locked_chunk.completed_at = timezone.now()
        locked_chunk.last_error = ""
        locked_chunk.save(
            update_fields=[
                "result_count",
                "source_gap_count",
                "downloaded_tile_count",
                "reused_tile_count",
                "downloaded_bytes",
                "reused_bytes",
                "source_bytes",
                "status",
                "completed_at",
                "last_error",
                "updated_at",
            ]
        )
        locked_build = TerrainBuild.objects.select_for_update().get(id=build.id)
        _update_build_progress(build=locked_build)
    return downloaded_tile_count, reused_tile_count


def _summaries(
    *, paths: list[Path], window: terrain.ProcessingWindow, quality_settings: dict[str, float]
) -> list[dict[str, Any]]:
    if not paths:
        rows = []
        grid = terrain.SampleGrid(
            west_e=window.west_e,
            south_n=window.south_n,
            east_e=window.east_e,
            north_n=window.north_n,
        )
        for _ in grid.corners():
            rows.append(
                {
                    "altitude_m": None,
                    "slope_deg": None,
                    "aspect_deg": None,
                    "altitude_m_valid_fraction": 0.0,
                    "slope_deg_valid_fraction": 0.0,
                    "aspect_deg_valid_fraction": 0.0,
                    "altitude_m_reliability": None,
                    "slope_deg_reliability": None,
                    "aspect_deg_reliability": None,
                    "source_gap": True,
                }
            )
        return rows
    bounds = terrain.source_bounds_for_window(window=window)
    mosaic, source_transform, source_crs, source_nodata = terrain.mosaic_source_tiles(
        tile_paths=paths,
        bounds=bounds,
    )
    altitude = terrain.reproject_mosaic_to_window(
        mosaic=mosaic,
        source_transform=source_transform,
        source_crs=source_crs,
        source_nodata=source_nodata,
        window=window,
    )
    return terrain.summarise_processing_window(
        altitude=altitude,
        window=window,
        settings=quality_settings,
    )


def _summaries_for_memberships(
    *, summaries: list[dict[str, Any]], memberships: list[GridBuildCell], chunk: Any
) -> list[dict[str, Any]]:
    """Select only rectangular summaries whose cell IDs are in the grid build."""
    columns = (chunk.east_e - chunk.west_e) // CELL_SIZE_M
    rows = (chunk.north_n - chunk.south_n) // CELL_SIZE_M
    if columns <= 0 or rows <= 0 or len(summaries) != columns * rows:
        raise ValueError(
            f"Terrain summary shape does not match chunk {chunk.id}: "
            f"{len(summaries)} rows for {rows} by {columns} cells."
        )
    selected: list[dict[str, Any]] = []
    for membership in memberships:
        corner_e = membership.cell.corner_e
        corner_n = membership.cell.corner_n
        if (
            (corner_e - chunk.west_e) % CELL_SIZE_M
            or (corner_n - chunk.south_n) % CELL_SIZE_M
        ):
            raise ValueError(f"Grid membership {membership.id} is not aligned to its chunk.")
        column = (corner_e - chunk.west_e) // CELL_SIZE_M
        row = (chunk.north_n - corner_n - CELL_SIZE_M) // CELL_SIZE_M
        if not (0 <= row < rows and 0 <= column < columns):
            raise ValueError(f"Grid membership {membership.id} lies outside its chunk.")
        selected.append(summaries[row * columns + column])
    return selected


def _source_tile_defaults(*, item: CachedTile) -> dict[str, Any]:
    metadata = item.metadata
    return {
        "tile_name": item.tile_name,
        "status": item.status,
        "url": metadata.get("url", ""),
        "release": metadata.get("release", terrain.SOURCE_RELEASE),
        "last_modified": metadata.get("last_modified", ""),
        "retrieved_at": _parse_time(value=metadata.get("retrieved_at")),
        "size_bytes": metadata.get("size_bytes"),
        "sha256": metadata.get("sha256", ""),
        "crs": metadata.get("crs", terrain.SOURCE_CRS),
        "native_pixel_m": metadata.get("native_pixel_m", terrain.SOURCE_NATIVE_PIXEL_M),
        "vertical_datum": metadata.get("vertical_datum", terrain.SOURCE_VERTICAL_DATUM),
        # Cached sidecars may predate the current license terms.
        "credit": terrain.LICENCE,
        "error_detail": metadata.get("error", ""),
    }


def _validate_source_tiles(*, build: TerrainBuild, cached: list[CachedTile]) -> None:
    """Reject source changes after a tile fact was recorded for this build."""
    names = [item.tile_name for item in cached]
    existing = {
        tile.tile_name: tile
        for tile in TerrainSourceTile.objects.filter(build=build, tile_name__in=names)
    }
    for item in cached:
        previous = existing.get(item.tile_name)
        if previous is None or previous.status not in (
            TerrainSourceTile.Status.AVAILABLE,
            TerrainSourceTile.Status.CONFIRMED_MISSING,
        ):
            continue
        if item.status != previous.status:
            raise TerrainBuildInputMismatchError(
                f"Source tile {item.tile_name!r} changed from {previous.status} for "
                f"build {build.version!r}."
            )
        _assert_source_identity(previous=previous, item=item)


def _assert_source_identity(*, previous: TerrainSourceTile, item: CachedTile) -> None:
    current = _source_tile_defaults(item=item)
    changed = [
        field
        for field in SOURCE_IDENTITY_FIELDS
        if getattr(previous, field) != current[field]
    ]
    if changed:
        changed_fields = ", ".join(changed)
        raise TerrainBuildInputMismatchError(
            f"Source tile {item.tile_name!r} metadata changed after it was used: "
            f"{changed_fields}."
        )


def _get_or_create_source_tile(
    *, build: TerrainBuild, tile_name: str, item: CachedTile
) -> TerrainSourceTile:
    previous = (
        TerrainSourceTile.objects.select_for_update()
        .filter(build=build, tile_name=tile_name)
        .first()
    )
    if previous is None:
        return TerrainSourceTile.objects.create(
            build=build,
            **_source_tile_defaults(item=item),
        )
    if previous.status in (
        TerrainSourceTile.Status.AVAILABLE,
        TerrainSourceTile.Status.CONFIRMED_MISSING,
    ):
        if item.status != previous.status:
            raise TerrainBuildInputMismatchError(
                f"Source tile {item.tile_name!r} changed from {previous.status} for "
                f"build {build.version!r}."
            )
        _assert_source_identity(previous=previous, item=item)
        return previous
    if item.status not in (
        TerrainSourceTile.Status.AVAILABLE,
        TerrainSourceTile.Status.CONFIRMED_MISSING,
    ):
        return previous
    for field, value in _source_tile_defaults(item=item).items():
        setattr(previous, field, value)
    previous.save(update_fields=[*_source_tile_defaults(item=item)])
    return previous


def _record_source_failure(*, build: TerrainBuild, tile_name: str, error: str) -> None:
    previous = (
        TerrainSourceTile.objects.select_for_update()
        .filter(build=build, tile_name=tile_name)
        .first()
    )
    if previous is not None and previous.status in (
        TerrainSourceTile.Status.AVAILABLE,
        TerrainSourceTile.Status.CONFIRMED_MISSING,
    ):
        return
    defaults = {
        "status": TerrainSourceTile.Status.FAILED,
        "url": terrain.TILE_URL.format(name=tile_name),
        "release": terrain.SOURCE_RELEASE,
        "crs": terrain.SOURCE_CRS,
        "native_pixel_m": terrain.SOURCE_NATIVE_PIXEL_M,
        "vertical_datum": terrain.SOURCE_VERTICAL_DATUM,
        "credit": terrain.LICENCE,
        "error_detail": error,
    }
    if previous is None:
        TerrainSourceTile.objects.create(
            build=build,
            tile_name=tile_name,
            **defaults,
        )
        return
    for field, value in defaults.items():
        setattr(previous, field, value)
    previous.save(update_fields=[*defaults])


def _parse_time(*, value: object) -> Any:
    if not value:
        return None
    return timezone.datetime.fromisoformat(str(value))


def _update_build_progress(*, build: TerrainBuild) -> None:
    """Persist counts for chunks and cells committed before the next progress event."""
    build.completed_chunk_count = TerrainChunk.objects.filter(
        build=build, status=TerrainChunk.Status.COMPLETED
    ).count()
    build.result_count = TerrainCell.objects.filter(build=build).count()
    build.source_gap_count = TerrainCell.objects.filter(build=build, source_gap=True).count()
    build.save(
        update_fields=[
            "completed_chunk_count",
            "result_count",
            "source_gap_count",
            "updated_at",
        ]
    )


def _finalise_build(*, build: TerrainBuild) -> None:
    with transaction.atomic():
        locked = TerrainBuild.objects.select_for_update().get(id=build.id)
        chunks = list(TerrainChunk.objects.filter(build=locked))
        completed_count = sum(chunk.status == TerrainChunk.Status.COMPLETED for chunk in chunks)
        result_count = sum(chunk.result_count for chunk in chunks)
        gap_count = sum(chunk.source_gap_count for chunk in chunks)
        cell_count = TerrainCell.objects.filter(build=locked).count()
        expected_memberships = set(
            GridBuildCell.objects.filter(build=locked.grid_build).values_list("id", flat=True)
        )
        actual_memberships = set(
            TerrainCell.objects.filter(build=locked).values_list("grid_build_cell_id", flat=True)
        )
        locked.completed_chunk_count = completed_count
        locked.result_count = result_count
        locked.source_gap_count = gap_count
        if (
            completed_count == locked.planned_chunk_count
            and result_count == locked.grid_build.cell_count
            and cell_count == locked.grid_build.cell_count
            and actual_memberships == expected_memberships
            and sum(chunk.result_count for chunk in chunks) == cell_count
        ):
            records = list(
                TerrainSourceTile.objects.filter(build=locked)
                .order_by("tile_name")
                .values(
                    "tile_name",
                    "status",
                    "url",
                    "release",
                    "last_modified",
                    "size_bytes",
                    "sha256",
                    "crs",
                    "native_pixel_m",
                    "vertical_datum",
                    "credit",
                )
            )
            locked.source_manifest_fingerprint = manifest_fingerprint(records=records)
            locked.status = TerrainBuild.Status.COMPLETED
            locked.completed_at = locked.completed_at or timezone.now()
        else:
            locked.status = TerrainBuild.Status.RUNNING
        locked.save(
            update_fields=[
                "completed_chunk_count",
                "result_count",
                "source_gap_count",
                "source_manifest_fingerprint",
                "status",
                "completed_at",
                "updated_at",
            ]
        )


def _result(
    *,
    build: TerrainBuild,
    cache_dir: Path,
    processed_chunks: int,
    reused_chunks: int,
    downloaded_tiles: int,
    reused_tiles: int,
    started: float,
) -> TerrainBuildResult:
    counts = [
        {
            "istat_code": region.istat_code,
            "name": region.name,
            "cell_count": region.owned_cells.filter(build=build.grid_build).count(),
            "terrain_count": TerrainCell.objects.filter(
                build=build, grid_build_cell__owner_region=region
            ).count(),
        }
        for region in build.grid_build.regions.order_by("istat_code")
    ]
    cache_bytes = sum(
        path.stat().st_size
        for path in cache_dir.glob("*.tif")
        if path.is_file()
    )
    return TerrainBuildResult(
        build=build,
        processed_chunks=processed_chunks,
        reused_chunks=reused_chunks,
        downloaded_tiles=downloaded_tiles,
        reused_tiles=reused_tiles,
        elapsed_seconds=time.monotonic() - started,
        peak_rss_mb=_peak_rss_mb(),
        regional_counts=counts,
        cache_bytes=cache_bytes,
    )


def _peak_rss_mb() -> float:
    """Return process peak resident memory in megabytes."""
    raw_value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return raw_value / divisor
