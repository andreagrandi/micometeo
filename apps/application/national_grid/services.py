"""Build and resume the national grid in small database transactions."""

from __future__ import annotations

import hashlib
import json
import resource
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from collections.abc import Callable
from typing import Any

from django.contrib.gis.geos import GEOSGeometry
from django.db import IntegrityError, transaction
from django.utils import timezone

from .geometry import GridChunkBounds, cells_for_chunk, iter_chunk_bounds
from .models import GridBuild, GridBuildCell, GridCell, GridChunk, GridRegion
from .source import BoundarySource, read_boundary_source

ALGORITHM_VERSION = "national-grid-v1"
INCLUSION_RULE = "positive area of the Italian regional union"


@dataclass(frozen=True)
class BuildResult:
    """Expose build state and counts for a command or caller."""

    build: GridBuild
    processed_chunks: int
    reused_chunks: int
    elapsed_seconds: float
    peak_rss_mb: float
    regional_counts: list[dict[str, Any]]

    @property
    def status(self) -> str:
        return self.build.status

    def as_dict(self) -> dict[str, Any]:
        return {
            "build_id": str(self.build.id),
            "build_version": self.build.version,
            "status": self.build.status,
            "cell_count": self.build.cell_count,
            "planned_chunk_count": self.build.planned_chunk_count,
            "completed_chunk_count": self.build.completed_chunk_count,
            "processed_chunks": self.processed_chunks,
            "reused_chunks": self.reused_chunks,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "peak_rss_mb": round(self.peak_rss_mb, 1),
            "regional_counts": self.regional_counts,
        }


class BuildInputMismatchError(ValueError):
    """Report an attempt to reuse a version with different build inputs."""


def build_fingerprint(
    *,
    archive_sha256: str,
    members: list[str],
    source_version: str,
    source_crs: str,
    grid_crs: str,
    cell_size_m: int,
    chunk_size_m: int,
    inclusion_rule: str = INCLUSION_RULE,
    algorithm_version: str = ALGORITHM_VERSION,
) -> str:
    """Hash every input that can change the national grid."""
    inputs = {
        "archive_sha256": archive_sha256,
        "members": sorted(members),
        "source_version": source_version,
        "source_crs": source_crs,
        "grid_crs": grid_crs,
        "cell_size_m": cell_size_m,
        "chunk_size_m": chunk_size_m,
        "inclusion_rule": inclusion_rule,
        "algorithm_version": algorithm_version,
    }
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_national_grid(
    *,
    archive_path: Path | None,
    build_version: str,
    expected_sha256: str,
    downloaded_on: date | str | None,
    chunk_size_m: int = 25_000,
    max_chunks: int | None = None,
    source: BoundarySource | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> BuildResult:
    """Create or resume one national build, committing each chunk separately."""
    started = time.monotonic()
    boundary_source = source or read_boundary_source(
        archive_path=archive_path if archive_path is not None else Path(),
        expected_sha256=expected_sha256,
        downloaded_on=downloaded_on,
    )
    metadata = dict(boundary_source.metadata)
    metadata.setdefault("archive_sha256", expected_sha256)
    metadata.setdefault("members", [])
    metadata.setdefault("version", "injected")
    metadata.setdefault("source_crs", "EPSG:32632")
    metadata.setdefault("grid_crs", "EPSG:3035")
    fingerprint = build_fingerprint(
        archive_sha256=str(metadata["archive_sha256"]),
        members=list(metadata["members"]),
        source_version=str(metadata["version"]),
        source_crs=str(metadata["source_crs"]),
        grid_crs=str(metadata["grid_crs"]),
        cell_size_m=500,
        chunk_size_m=chunk_size_m,
    )
    metadata["algorithm_version"] = ALGORITHM_VERSION
    metadata["cell_size_m"] = 500
    metadata["chunk_size_m"] = chunk_size_m
    metadata["inclusion_rule"] = INCLUSION_RULE
    metadata["fingerprint"] = fingerprint

    build, created = _get_or_create_build(
        build_version=build_version,
        fingerprint=fingerprint,
        metadata=metadata,
        chunk_size_m=chunk_size_m,
    )
    if not created and build.fingerprint != fingerprint:
        raise BuildInputMismatchError(
            f"Build version {build_version!r} already exists with different inputs."
        )
    if build.status == GridBuild.Status.COMPLETED:
        return _result(
            build=build,
            processed_chunks=0,
            reused_chunks=build.completed_chunk_count,
            elapsed_seconds=time.monotonic() - started,
            peak_rss_mb=_peak_rss_mb(),
        )

    chunks = iter_chunk_bounds(
        regions=boundary_source.regions,
        cell_size_m=build.cell_size_m,
        chunk_size_m=build.chunk_size_m,
    )
    _prepare_build(build=build, source=boundary_source, chunks=chunks)
    completed_before = GridChunk.objects.filter(
        build=build,
        status=GridChunk.Status.COMPLETED,
    ).count()
    processed = 0
    for chunk in GridChunk.objects.filter(build=build).order_by("south_n", "west_e"):
        if chunk.status == GridChunk.Status.COMPLETED:
            continue
        if max_chunks is not None and processed >= max_chunks:
            break
        _process_chunk(build=build, chunk=chunk, source=boundary_source)
        processed += 1
        if progress_callback is not None:
            build.refresh_from_db()
            progress_callback(
                {
                    "build_version": build.version,
                    "status": "chunk_completed",
                    "completed_chunk_count": build.chunks.filter(
                        status=GridChunk.Status.COMPLETED
                    ).count(),
                    "planned_chunk_count": build.planned_chunk_count,
                    "cell_count": GridBuildCell.objects.filter(build=build).count(),
                }
            )
    _finalise_build(build=build)
    build.refresh_from_db()
    return _result(
        build=build,
        processed_chunks=processed,
        reused_chunks=completed_before,
        elapsed_seconds=time.monotonic() - started,
        peak_rss_mb=_peak_rss_mb(),
    )


def _get_or_create_build(
    *,
    build_version: str,
    fingerprint: str,
    metadata: dict[str, Any],
    chunk_size_m: int,
) -> tuple[GridBuild, bool]:
    with transaction.atomic():
        build = GridBuild.objects.select_for_update().filter(version=build_version).first()
        if build is not None:
            return build, False
        try:
            with transaction.atomic():
                build = GridBuild.objects.create(
                    version=build_version,
                    fingerprint=fingerprint,
                    cell_size_m=500,
                    chunk_size_m=chunk_size_m,
                    grid_crs="EPSG:3035",
                    source_crs="EPSG:32632",
                    algorithm_version=ALGORITHM_VERSION,
                    source_metadata=metadata,
                    started_at=timezone.now(),
                )
        except IntegrityError:
            build = GridBuild.objects.select_for_update().get(version=build_version)
            return build, False
        return build, True


def _prepare_build(
    *,
    build: GridBuild,
    source: BoundarySource,
    chunks: list[GridChunkBounds],
) -> None:
    with transaction.atomic():
        locked_build = GridBuild.objects.select_for_update().get(id=build.id)
        locked_build.planned_chunk_count = len(chunks)
        locked_build.status = GridBuild.Status.RUNNING
        if locked_build.started_at is None:
            locked_build.started_at = timezone.now()
        locked_build.save(
            update_fields=[
                "planned_chunk_count",
                "status",
                "started_at",
                "updated_at",
            ]
        )
        GridRegion.objects.bulk_create(
            [
                GridRegion(
                    build=locked_build,
                    istat_code=region.istat_code,
                    name=region.name,
                    geometry=GEOSGeometry(memoryview(region.geometry.wkb), srid=3035),
                )
                for region in source.regions
            ],
            ignore_conflicts=True,
        )
        GridChunk.objects.bulk_create(
            [
                GridChunk(
                    build=locked_build,
                    west_e=chunk.west_e,
                    south_n=chunk.south_n,
                    east_e=chunk.east_e,
                    north_n=chunk.north_n,
                )
                for chunk in chunks
            ],
            ignore_conflicts=True,
        )


def _process_chunk(*, build: GridBuild, chunk: GridChunk, source: BoundarySource) -> None:
    definitions = cells_for_chunk(
        regions=source.regions,
        bounds=GridChunkBounds(
            west_e=chunk.west_e,
            south_n=chunk.south_n,
            east_e=chunk.east_e,
            north_n=chunk.north_n,
        ),
        cell_size_m=build.cell_size_m,
    )
    with transaction.atomic():
        locked_chunk = GridChunk.objects.select_for_update().get(id=chunk.id)
        if locked_chunk.status == GridChunk.Status.COMPLETED:
            return
        locked_chunk.status = GridChunk.Status.RUNNING
        locked_chunk.started_at = locked_chunk.started_at or timezone.now()
        locked_chunk.save(update_fields=["status", "started_at", "updated_at"])
        region_ids = {
            region.istat_code: region.id
            for region in GridRegion.objects.filter(build=build)
        }
        GridCell.objects.bulk_create(
            [
                GridCell(
                    cell_id=definition.cell_id,
                    corner_e=definition.corner_e,
                    corner_n=definition.corner_n,
                    geometry=GEOSGeometry(memoryview(definition.geometry.wkb), srid=3035),
                )
                for definition in definitions
            ],
            ignore_conflicts=True,
        )
        memberships = [
            GridBuildCell(
                build=build,
                cell_id=definition.cell_id,
                chunk=locked_chunk,
                owner_region_id=region_ids[definition.owner_code],
                land_geometry=GEOSGeometry(memoryview(definition.land_geometry.wkb), srid=3035),
                land_share=definition.land_share,
            )
            for definition in definitions
        ]
        GridBuildCell.objects.bulk_create(memberships, ignore_conflicts=True)
        count = GridBuildCell.objects.filter(chunk=locked_chunk).count()
        locked_chunk.cell_count = count
        locked_chunk.status = GridChunk.Status.COMPLETED
        locked_chunk.completed_at = timezone.now()
        locked_chunk.save(update_fields=["cell_count", "status", "completed_at", "updated_at"])


def _finalise_build(*, build: GridBuild) -> None:
    with transaction.atomic():
        locked_build = GridBuild.objects.select_for_update().get(id=build.id)
        completed_chunks = GridChunk.objects.filter(
            build=locked_build,
            status=GridChunk.Status.COMPLETED,
        )
        completed_count = completed_chunks.count()
        cell_count = GridBuildCell.objects.filter(build=locked_build).count()
        locked_build.completed_chunk_count = completed_count
        locked_build.cell_count = cell_count
        if completed_count == locked_build.planned_chunk_count and all(
            chunk.cell_count >= 0 for chunk in completed_chunks
        ) and sum(chunk.cell_count for chunk in completed_chunks) == cell_count:
            locked_build.status = GridBuild.Status.COMPLETED
            locked_build.completed_at = locked_build.completed_at or timezone.now()
        else:
            locked_build.status = GridBuild.Status.RUNNING
        locked_build.save(
            update_fields=[
                "completed_chunk_count",
                "cell_count",
                "status",
                "completed_at",
                "updated_at",
            ]
        )


def _result(
    *,
    build: GridBuild,
    processed_chunks: int,
    reused_chunks: int,
    elapsed_seconds: float,
    peak_rss_mb: float,
) -> BuildResult:
    counts = [
        {"istat_code": region.istat_code, "name": region.name, "cell_count": region.owned_cells.filter(build=build).count()}
        for region in build.regions.order_by("istat_code")
    ]
    return BuildResult(
        build=build,
        processed_chunks=processed_chunks,
        reused_chunks=reused_chunks,
        elapsed_seconds=elapsed_seconds,
        peak_rss_mb=peak_rss_mb,
        regional_counts=counts,
    )


def _peak_rss_mb() -> float:
    """Return process peak resident memory in megabytes."""
    raw_value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return raw_value / divisor
