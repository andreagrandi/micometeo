"""Build, resume and publish national forest values for the national grid."""

from __future__ import annotations

import hashlib
import json
import math
import resource
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from pyproj import Transformer
from rasterio.windows import Window

from background_jobs.services import logical_job_lock
from micometeo.habitat.forest import summarise_national_block
from national_grid.models import GridBuild, GridBuildCell, GridChunk

from . import layer, source
from .models import ForestBuild, ForestCell, ForestChunk

ALGORITHM_VERSION = "national-forest-v1"
LAYER_VERSION = "forest-layer-2000m-v1"
WEATHER_POLICY_VERSION = "centre-epsg3035-floor-tenths-v1"
GRID_CELL_SIZE_M = 500
SOURCE_PIXEL_SIZE_M = 10
SOURCE_CHUNK_LIMIT_M = 40_000
PIXELS_PER_CELL_SIDE = GRID_CELL_SIZE_M // SOURCE_PIXEL_SIZE_M
_TO_WGS84 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)


class ForestBuildInputMismatchError(ValueError):
    """Report an attempt to reuse a build version with different inputs."""


class ForestBuildIncompleteError(RuntimeError):
    """Report a national forest build that cannot be marked completed."""


@dataclass(frozen=True)
class BuildResult:
    """Expose forest build state and progress to a command or caller."""

    build: ForestBuild
    processed_chunks: int
    reused_chunks: int
    elapsed_seconds: float
    peak_rss_mb: float
    regional_counts: list[dict[str, Any]]

    @property
    def status(self) -> str:
        """Return the current build status."""
        return self.build.status

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-safe build details."""
        return {
            "build_id": str(self.build.id),
            "build_version": self.build.version,
            "status": self.build.status,
            "grid_build_version": self.build.grid_build.version,
            "fingerprint": self.build.fingerprint,
            "cell_count": self.build.cell_count,
            "forest_cell_count": self.build.forest_cell_count,
            "weather_cell_count": self.build.weather_cell_count,
            "planned_chunk_count": self.build.planned_chunk_count,
            "completed_chunk_count": self.build.completed_chunk_count,
            "processed_chunks": self.processed_chunks,
            "reused_chunks": self.reused_chunks,
            "layer_path": self.build.layer_path,
            "layer_sha256": self.build.layer_sha256,
            "layer_raw_bytes": self.build.layer_raw_bytes,
            "layer_gzip_bytes": self.build.layer_gzip_bytes,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "peak_rss_mb": round(self.peak_rss_mb, 1),
            "regional_counts": self.regional_counts,
        }


def forest_build_fingerprint(
    *,
    grid_build_id: str,
    grid_fingerprint: str,
    source_release: str = source.SOURCE_RELEASE,
    source_resolution_m: int = source.SOURCE_RESOLUTION_M,
    source_crs: str = source.SOURCE_CRS,
    resampling: str = source.RESAMPLING,
    request_options: dict[str, Any] | None = None,
    thresholds: dict[str, float] | None = None,
    weather_policy: str = WEATHER_POLICY_VERSION,
    layer_version: str = LAYER_VERSION,
    algorithm_version: str = ALGORITHM_VERSION,
) -> str:
    """Hash every input that can change national forest rows or its layer."""
    values = {
        "algorithm_version": algorithm_version,
        "grid_build_id": str(grid_build_id),
        "grid_fingerprint": grid_fingerprint,
        "source_release": source_release,
        "source_resolution_m": source_resolution_m,
        "source_crs": source_crs,
        "resampling": resampling,
        "request_options": request_options or {},
        "thresholds": thresholds
        or {
            "high_coverage": 0.95,
            "low_coverage": 0.5,
            "no_forest_below": 0.1,
            "broadleaf_from": 0.75,
        },
        "weather_policy": weather_policy,
        "layer_version": layer_version,
    }
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


build_fingerprint = forest_build_fingerprint


def weather_cell(*, latitude: float, longitude: float) -> tuple[float, float]:
    """Return the centre of the deterministic 0.1 degree weather cell."""
    latitude_decimal = Decimal(str(latitude))
    longitude_decimal = Decimal(str(longitude))
    tenth = Decimal("0.1")
    centre_offset = Decimal("0.05")
    latitude_floor = (latitude_decimal / tenth).to_integral_value(rounding=ROUND_FLOOR) * tenth
    longitude_floor = (longitude_decimal / tenth).to_integral_value(rounding=ROUND_FLOOR) * tenth
    return (
        float(latitude_floor + centre_offset),
        float(longitude_floor + centre_offset),
    )


def weather_cell_for_corner(*, corner_e: int, corner_n: int) -> tuple[float, float]:
    """Return weather cell centre for a 500 metre square centre."""
    longitude, latitude = _TO_WGS84.transform(
        corner_e + GRID_CELL_SIZE_M / 2,
        corner_n + GRID_CELL_SIZE_M / 2,
    )
    return weather_cell(latitude=latitude, longitude=longitude)


def split_source_bounds(
    *,
    bounds: tuple[int, int, int, int],
    max_source_chunk_m: int = SOURCE_CHUNK_LIMIT_M,
) -> Iterator[tuple[int, int, int, int]]:
    """Split one grid chunk into aligned requests within the source limits."""
    west, south, east, north = bounds
    if max_source_chunk_m <= 0 or max_source_chunk_m % SOURCE_PIXEL_SIZE_M:
        raise ValueError("The source chunk limit must be a positive ten metre multiple.")
    if east <= west or north <= south:
        raise ValueError("A source chunk must have positive dimensions.")
    for south_edge in range(south, north, max_source_chunk_m):
        for west_edge in range(west, east, max_source_chunk_m):
            yield (
                west_edge,
                south_edge,
                min(west_edge + max_source_chunk_m, east),
                min(south_edge + max_source_chunk_m, north),
            )


def _get_or_create_build(
    *,
    grid_build: GridBuild,
    build_version: str,
    fingerprint: str,
    source_options: dict[str, Any],
) -> tuple[ForestBuild, bool]:
    metadata = source.source_metadata()
    metadata.update({"request_options": source_options, "fingerprint": fingerprint})
    defaults = {
        "grid_build": grid_build,
        "fingerprint": fingerprint,
        "algorithm_version": ALGORITHM_VERSION,
        "source_release": source.SOURCE_RELEASE,
        "source_metadata": metadata,
        "service_url": source.SERVICE_URL,
        "catalogue_url": source.CATALOGUE_URL,
        "source_resolution_m": source.SOURCE_RESOLUTION_M,
        "source_crs": source.SOURCE_CRS,
        "resampling": source.RESAMPLING,
        "licence": source.LICENCE,
        "credit": source.CREDIT,
        "started_at": timezone.now(),
    }
    with transaction.atomic():
        build = ForestBuild.objects.select_for_update().filter(version=build_version).first()
        if build is not None:
            return build, False
        try:
            with transaction.atomic():
                return ForestBuild.objects.create(version=build_version, **defaults), True
        except IntegrityError:
            return ForestBuild.objects.select_for_update().get(version=build_version), False


def _validate_build_inputs(
    *,
    build: ForestBuild,
    grid_build: GridBuild,
    fingerprint: str,
) -> None:
    """Check the winner of a concurrent build creation race."""
    if grid_build.status != GridBuild.Status.COMPLETED:
        raise ForestBuildIncompleteError("The national grid build must be completed first.")
    if build.grid_build_id != grid_build.id or build.fingerprint != fingerprint:
        raise ForestBuildInputMismatchError(
            f"Forest build version {build.version!r} already exists with different inputs."
        )


def _planned_chunk_rows(
    *,
    build: ForestBuild,
    grid_build: GridBuild,
    max_source_chunk_m: int,
) -> list[ForestChunk]:
    """Create the immutable source chunk rows for one requested layout."""
    chunks: list[ForestChunk] = []
    for grid_chunk in GridChunk.objects.filter(build=grid_build).order_by("south_n", "west_e"):
        for bounds in split_source_bounds(
            bounds=(
                grid_chunk.west_e,
                grid_chunk.south_n,
                grid_chunk.east_e,
                grid_chunk.north_n,
            ),
            max_source_chunk_m=max_source_chunk_m,
        ):
            request_options = source.build_request(bounds=bounds)
            request_key = source.cache_key(bounds=bounds, request_options=request_options)
            chunks.append(
                ForestChunk(
                    build=build,
                    grid_chunk=grid_chunk,
                    west_e=bounds[0],
                    south_n=bounds[1],
                    east_e=bounds[2],
                    north_n=bounds[3],
                    request_key=request_key,
                    request_sha256=request_key,
                )
            )
    return chunks


def _validate_source_chunk_layout(
    *,
    build: ForestBuild,
    planned_chunks: list[ForestChunk],
    max_source_chunk_m: int,
) -> None:
    """Reject a changed chunk layout before changing a resumable build."""
    if build.source_chunk_size_m is not None and build.source_chunk_size_m != max_source_chunk_m:
        raise ForestBuildInputMismatchError(
            f"Forest build {build.version!r} already uses {build.source_chunk_size_m} metre source chunks."
        )
    actual_bounds = sorted(
        ForestChunk.objects.filter(build=build).values_list(
            "west_e", "south_n", "east_e", "north_n"
        )
    )
    planned_bounds = sorted(
        (chunk.west_e, chunk.south_n, chunk.east_e, chunk.north_n)
        for chunk in planned_chunks
    )
    if actual_bounds and actual_bounds != planned_bounds:
        raise ForestBuildInputMismatchError(
            f"Forest build {build.version!r} already has a different source chunk layout."
        )
    if build.source_chunk_size_m is None:
        ForestBuild.objects.filter(id=build.id).update(source_chunk_size_m=max_source_chunk_m)


def _prepare_build(
    *,
    build: ForestBuild,
    grid_build: GridBuild,
    max_source_chunk_m: int,
) -> None:
    chunks = _planned_chunk_rows(
        build=build,
        grid_build=grid_build,
        max_source_chunk_m=max_source_chunk_m,
    )
    _validate_source_chunk_layout(
        build=build,
        planned_chunks=chunks,
        max_source_chunk_m=max_source_chunk_m,
    )
    with transaction.atomic():
        locked = ForestBuild.objects.select_for_update().get(id=build.id)
        locked.status = ForestBuild.Status.RUNNING
        locked.planned_chunk_count = len(chunks)
        locked.started_at = locked.started_at or timezone.now()
        locked.source_chunk_size_m = max_source_chunk_m
        locked.save(update_fields=["status", "planned_chunk_count", "source_chunk_size_m", "started_at", "updated_at"])
        ForestChunk.objects.bulk_create(chunks, ignore_conflicts=True)


def _log_progress(*, path: Path | None, event: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()


def _source_path(value: Any) -> tuple[Path, bool, int]:
    if isinstance(value, Path):
        return value, False, value.stat().st_size
    if isinstance(value, str):
        path = Path(value)
        return path, False, path.stat().st_size
    path = Path(value.path)
    metadata = getattr(value, "metadata", {})
    source_bytes = metadata.get("raw_bytes")
    if source_bytes is None:
        source_bytes = path.stat().st_size
    return path, bool(getattr(value, "reused", False)), int(source_bytes)


def _source_provenance(*, value: Any, path: Path, source_bytes: int) -> dict[str, Any]:
    """Return cached source metadata without inventing retrieval facts."""
    metadata = dict(getattr(value, "metadata", {}) or {})
    metadata.setdefault("source_path", str(path))
    metadata.setdefault("sha256", source.sha256_path(path=path))
    metadata.setdefault("raw_bytes", source_bytes)
    return metadata


def _chunk_has_source_provenance(*, forest_chunk: ForestChunk) -> bool:
    """Return whether one completed chunk has persisted cache provenance."""
    return bool(
        forest_chunk.source_sha256
        and forest_chunk.source_path
        and forest_chunk.source_metadata
    )


def _hydrate_chunk_provenance(*, build: ForestBuild, cache_dir: Path) -> None:
    """Persist metadata from existing local sidecars without network access."""
    for forest_chunk in ForestChunk.objects.filter(
        build=build,
        status=ForestChunk.Status.COMPLETED,
    ).iterator(chunk_size=500):
        if _chunk_has_source_provenance(forest_chunk=forest_chunk):
            continue
        path = source.raster_path(cache_dir=cache_dir, key=forest_chunk.request_key)
        sidecar = source.sidecar_path(cache_dir=cache_dir, key=forest_chunk.request_key)
        if not path.is_file() or not sidecar.is_file():
            raise ForestBuildIncompleteError(
                f"Completed forest chunk {forest_chunk.id} has no local source sidecar."
            )
        cached = source.cache_source_chunk(bounds=forest_chunk.bounds, cache_dir=cache_dir)
        metadata = _source_provenance(
            value=cached,
            path=cached.path,
            source_bytes=int(cached.metadata.get("raw_bytes", cached.path.stat().st_size)),
        )
        ForestChunk.objects.filter(id=forest_chunk.id).update(
            source_bytes=int(metadata.get("raw_bytes", cached.path.stat().st_size)),
            source_sha256=str(metadata.get("sha256", "")),
            source_retrieved_at=str(metadata.get("retrieved_at", "")),
            source_crs_wkt=str(metadata.get("source_crs_wkt", "")),
            source_path=str(metadata.get("source_path", cached.path)),
            source_metadata=metadata,
            updated_at=timezone.now(),
        )


def _cell_rows(
    *,
    build: ForestBuild,
    forest_chunk: ForestChunk,
    raster_path: Path,
) -> list[ForestCell]:
    """Read one source chunk and summarise its grid memberships."""
    source.validate_raster(path=raster_path, bounds=forest_chunk.bounds)
    memberships = (
        GridBuildCell.objects.filter(build=build.grid_build, chunk=forest_chunk.grid_chunk)
        .select_related("cell")
        .order_by("cell__corner_n", "cell__corner_e")
    )
    rows: list[ForestCell] = []
    with rasterio.open(raster_path) as dataset:
        for membership in memberships.iterator(chunk_size=2_000):
            corner_e = membership.cell.corner_e
            corner_n = membership.cell.corner_n
            if not (
                forest_chunk.west_e <= corner_e
                and corner_e + GRID_CELL_SIZE_M <= forest_chunk.east_e
                and forest_chunk.south_n <= corner_n
                and corner_n + GRID_CELL_SIZE_M <= forest_chunk.north_n
            ):
                continue
            column = (corner_e - forest_chunk.west_e) // SOURCE_PIXEL_SIZE_M
            row = (forest_chunk.north_n - corner_n - GRID_CELL_SIZE_M) // SOURCE_PIXEL_SIZE_M
            pixels = dataset.read(
                1,
                window=Window(
                    column,
                    row,
                    PIXELS_PER_CELL_SIDE,
                    PIXELS_PER_CELL_SIDE,
                ),
            )
            values = summarise_national_block(pixels=pixels)
            kwargs: dict[str, Any] = {
                "build": build,
                "grid_build_cell": membership,
                "chunk": forest_chunk,
                **values,
                "missing_reason": values["missing_reason"] or "",
            }
            if values["is_forest"] is True:
                latitude, longitude = weather_cell_for_corner(
                    corner_e=corner_e,
                    corner_n=corner_n,
                )
                kwargs["weather_latitude"] = latitude
                kwargs["weather_longitude"] = longitude
            rows.append(ForestCell(**kwargs))
    return rows


def _fail_chunk(*, forest_chunk: ForestChunk, reason: str) -> None:
    with transaction.atomic():
        locked = ForestChunk.objects.select_for_update().get(id=forest_chunk.id)
        locked.status = ForestChunk.Status.FAILED
        locked.failure_reason = reason[:10_000]
        locked.last_attempt_at = timezone.now()
        locked.save(update_fields=["status", "failure_reason", "last_attempt_at", "updated_at"])
        ForestBuild.objects.filter(id=locked.build_id).update(
            status=ForestBuild.Status.FAILED,
            failed_chunk_count=ForestChunk.objects.filter(
                build_id=locked.build_id,
                status=ForestChunk.Status.FAILED,
            ).count(),
            updated_at=timezone.now(),
        )


def _distinct_weather_count(*, build_id: Any, region_id: Any | None = None) -> int:
    """Count unique weather centres for one build or one owner region."""
    cells = ForestCell.objects.filter(
        build_id=build_id,
        is_forest=True,
        weather_latitude__isnull=False,
        weather_longitude__isnull=False,
    )
    if region_id is not None:
        cells = cells.filter(grid_build_cell__owner_region_id=region_id)
    return cells.values("weather_latitude", "weather_longitude").distinct().count()


def _update_build_progress(*, build_id: Any) -> None:
    """Refresh committed row and chunk counters after one database commit."""
    completed_chunks = ForestChunk.objects.filter(
        build_id=build_id,
        status=ForestChunk.Status.COMPLETED,
    ).count()
    failed_chunks = ForestChunk.objects.filter(
        build_id=build_id,
        status=ForestChunk.Status.FAILED,
    ).count()
    cell_counts = ForestCell.objects.filter(build_id=build_id).aggregate(
        cell_count=Count("id"),
        forest_cell_count=Count("id", filter=Q(is_forest=True)),
        source_gap_count=Count("id", filter=Q(valid_coverage__lt=1.0)),
    )
    ForestBuild.objects.filter(id=build_id).update(
        completed_chunk_count=completed_chunks,
        failed_chunk_count=failed_chunks,
        cell_count=cell_counts["cell_count"] or 0,
        forest_cell_count=cell_counts["forest_cell_count"] or 0,
        source_gap_count=cell_counts["source_gap_count"] or 0,
        weather_cell_count=_distinct_weather_count(build_id=build_id),
        updated_at=timezone.now(),
    )


def _process_chunk(
    *,
    build: ForestBuild,
    forest_chunk: ForestChunk,
    cache_dir: Path,
    source_loader: Callable[..., Any],
    progress_path: Path | None,
) -> None:
    with transaction.atomic():
        locked = ForestChunk.objects.select_for_update().get(id=forest_chunk.id)
        if locked.status == ForestChunk.Status.COMPLETED:
            return
        locked.status = ForestChunk.Status.RUNNING
        locked.attempt_count += 1
        locked.started_at = locked.started_at or timezone.now()
        locked.last_attempt_at = timezone.now()
        locked.failure_reason = ""
        locked.save(update_fields=["status", "attempt_count", "started_at", "last_attempt_at", "failure_reason", "updated_at"])

    started = time.monotonic()
    try:
        fetched = source_loader(bounds=forest_chunk.bounds, cache_dir=cache_dir)
        raster_path, reused, source_bytes = _source_path(fetched)
        provenance = _source_provenance(
            value=fetched,
            path=raster_path,
            source_bytes=source_bytes,
        )
        rows = _cell_rows(build=build, forest_chunk=forest_chunk, raster_path=raster_path)
        with transaction.atomic():
            locked = ForestChunk.objects.select_for_update().get(id=forest_chunk.id)
            ForestCell.objects.bulk_create(rows, ignore_conflicts=True, batch_size=2_000)
            locked.cell_count = ForestCell.objects.filter(chunk=locked).count()
            locked.source_bytes = source_bytes
            locked.source_sha256 = str(provenance.get("sha256", ""))
            locked.source_retrieved_at = str(provenance.get("retrieved_at", ""))
            locked.source_crs_wkt = str(provenance.get("source_crs_wkt", ""))
            locked.source_path = str(provenance.get("source_path", raster_path))
            locked.source_metadata = provenance
            locked.status = ForestChunk.Status.COMPLETED
            locked.completed_at = timezone.now()
            locked.save(
                update_fields=[
                    "cell_count",
                    "source_bytes",
                    "source_sha256",
                    "source_retrieved_at",
                    "source_crs_wkt",
                    "source_path",
                    "source_metadata",
                    "status",
                    "completed_at",
                    "updated_at",
                ]
            )
            _update_build_progress(build_id=locked.build_id)
        _log_progress(
            path=progress_path,
            event={
                "status": "chunk_completed",
                "chunk_id": str(forest_chunk.id),
                "bounds": list(forest_chunk.bounds),
                "cell_count": len(rows),
                "cache_reused": reused,
                "source_bytes": source_bytes,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "peak_rss_mb": round(_peak_rss_mb(), 1),
                "source_gap": False,
            },
        )
    except Exception as exc:
        _fail_chunk(forest_chunk=forest_chunk, reason=str(exc))
        _log_progress(
            path=progress_path,
            event={
                "status": "chunk_failed",
                "chunk_id": str(forest_chunk.id),
                "bounds": list(forest_chunk.bounds),
                "error": str(exc),
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "peak_rss_mb": round(_peak_rss_mb(), 1),
                "source_gap": True,
            },
        )
        raise


def _finalise_build(
    *,
    build: ForestBuild,
    output_dir: Path,
    cache_dir: Path | None = None,
) -> None:
    build.refresh_from_db()
    if cache_dir is not None:
        _hydrate_chunk_provenance(build=build, cache_dir=cache_dir)
    _update_build_progress(build_id=build.id)
    build.refresh_from_db()
    completed_chunks = build.completed_chunk_count
    membership_count = GridBuildCell.objects.filter(build=build.grid_build).count()
    cell_count = build.cell_count
    duplicate_count = (
        ForestCell.objects.filter(build=build)
        .values("grid_build_cell_id")
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)
        .count()
    )
    if completed_chunks != build.planned_chunk_count or cell_count != membership_count or duplicate_count:
        ForestBuild.objects.filter(id=build.id).update(
            status=ForestBuild.Status.RUNNING,
            completed_chunk_count=completed_chunks,
            cell_count=cell_count,
            updated_at=timezone.now(),
        )
        return

    output_path = Path(output_dir) / build.version / "forest_layer_2000m.geojson.gz"
    if (
        output_path.is_file()
        and build.layer_path
        and layer.resolve_layer_path(value=build.layer_path).resolve() == output_path.resolve()
    ):
        try:
            existing = layer.validate_layer(path=output_path)
        except ValueError:
            existing = None
        if existing is not None and existing["sha256"] == build.layer_sha256:
            layer_sha256 = existing["sha256"]
            layer_gzip_bytes = existing["gzip_bytes"]
            layer_raw_bytes = build.layer_raw_bytes
        else:
            existing = None
    else:
        existing = None
    if existing is None:
        artifact = layer.write_forest_layer(
            rows=layer.rows_from_cells(cells=ForestCell.objects.filter(build=build)),
            output_path=output_path,
        )
        layer_sha256 = artifact.sha256
        layer_gzip_bytes = artifact.gzip_bytes
        layer_raw_bytes = artifact.raw_bytes
    forest_count = ForestCell.objects.filter(build=build, is_forest=True).count()
    weather_count = _distinct_weather_count(build_id=build.id)
    with transaction.atomic():
        locked = ForestBuild.objects.select_for_update().get(id=build.id)
        locked.completed_chunk_count = completed_chunks
        locked.cell_count = cell_count
        locked.forest_cell_count = forest_count
        locked.weather_cell_count = weather_count
        locked.layer_path = layer.stored_layer_path(path=output_path)
        locked.layer_sha256 = layer_sha256
        locked.layer_raw_bytes = layer_raw_bytes
        locked.layer_gzip_bytes = layer_gzip_bytes
        locked.status = ForestBuild.Status.COMPLETED
        locked.completed_at = locked.completed_at or timezone.now()
        locked.save(
            update_fields=[
                "completed_chunk_count",
                "cell_count",
                "forest_cell_count",
                "weather_cell_count",
                "layer_path",
                "layer_sha256",
                "layer_raw_bytes",
                "layer_gzip_bytes",
                "status",
                "completed_at",
                "updated_at",
            ]
        )


def regional_counts(*, build: ForestBuild) -> list[dict[str, Any]]:
    """Return forest, non-forest and unavailable counts for every region."""
    counts = {
        region["id"]: {
            "istat_code": region["istat_code"],
            "name": region["name"],
            "cell_count": 0,
            "forest_cell_count": 0,
            "nonforest_cell_count": 0,
            "unavailable_cell_count": 0,
            "weather_cell_count": 0,
        }
        for region in build.grid_build.regions.order_by("istat_code").values("id", "istat_code", "name")
    }
    weather_counts = {
        region_id: _distinct_weather_count(build_id=build.id, region_id=region_id)
        for region_id in counts
    }
    region_rows = (
        ForestCell.objects.filter(build=build)
        .values("grid_build_cell__owner_region_id")
        .annotate(
            cell_count=Count("id"),
            forest_cell_count=Count("id", filter=Q(is_forest=True)),
            nonforest_cell_count=Count("id", filter=Q(is_forest=False)),
            unavailable_cell_count=Count("id", filter=Q(is_forest__isnull=True)),
        )
    )
    for region_row in region_rows.iterator():
        row = counts.get(region_row["grid_build_cell__owner_region_id"])
        if row is None:
            continue
        row["cell_count"] = region_row["cell_count"]
        row["forest_cell_count"] = region_row["forest_cell_count"]
        row["nonforest_cell_count"] = region_row["nonforest_cell_count"]
        row["unavailable_cell_count"] = region_row["unavailable_cell_count"]
    for region_id, weather_count in weather_counts.items():
        counts[region_id]["weather_cell_count"] = weather_count
    return list(counts.values())


def build_national_forest(
    *,
    grid_build_version: str,
    build_version: str,
    cache_dir: Path,
    output_dir: Path,
    max_source_chunk_m: int | None = None,
    max_chunks: int | None = None,
    output_format: str = "jsonl",
    source_loader: Callable[..., Any] | None = None,
    progress_path: Path | None = None,
) -> BuildResult:
    """Create or resume one forest build, committing each source chunk."""
    if output_format != "jsonl":
        raise ValueError("The national forest command currently supports jsonl output only.")
    if max_source_chunk_m is not None and (
        max_source_chunk_m > SOURCE_CHUNK_LIMIT_M
        or max_source_chunk_m <= 0
        or max_source_chunk_m % GRID_CELL_SIZE_M
    ):
        raise ValueError("Source chunks must be positive multiples of 500 metres up to forty kilometres.")
    started = time.monotonic()
    grid_build = GridBuild.objects.get(version=grid_build_version)
    if grid_build.status != GridBuild.Status.COMPLETED:
        raise ForestBuildIncompleteError("The national grid build must be completed first.")
    request_options = {
        "bboxSR": 3035,
        "imageSR": 3035,
        "pixelType": "U8",
        "interpolation": "RSP_NearestNeighbor",
        "format": "tiff",
    }
    fingerprint = forest_build_fingerprint(
        grid_build_id=str(grid_build.id),
        grid_fingerprint=grid_build.fingerprint,
        request_options=request_options,
    )
    build, _ = _get_or_create_build(
        grid_build=grid_build,
        build_version=build_version,
        fingerprint=fingerprint,
        source_options=request_options,
    )
    _validate_build_inputs(build=build, grid_build=grid_build, fingerprint=fingerprint)
    if max_source_chunk_m is None:
        max_source_chunk_m = build.source_chunk_size_m or SOURCE_CHUNK_LIMIT_M
    if max_source_chunk_m > SOURCE_CHUNK_LIMIT_M:
        raise ValueError("Source chunks cannot exceed forty kilometres.")
    if max_source_chunk_m <= 0 or max_source_chunk_m % GRID_CELL_SIZE_M:
        raise ValueError("Source chunks must be positive multiples of 500 metres.")
    planned_chunks = _planned_chunk_rows(
        build=build,
        grid_build=grid_build,
        max_source_chunk_m=max_source_chunk_m,
    )
    _validate_source_chunk_layout(
        build=build,
        planned_chunks=planned_chunks,
        max_source_chunk_m=max_source_chunk_m,
    )
    if build.status == ForestBuild.Status.COMPLETED:
        _finalise_build(
            build=build,
            output_dir=Path(output_dir),
            cache_dir=Path(cache_dir),
        )
        build.refresh_from_db()
        return BuildResult(
            build=build,
            processed_chunks=0,
            reused_chunks=build.completed_chunk_count,
            elapsed_seconds=time.monotonic() - started,
            peak_rss_mb=_peak_rss_mb(),
            regional_counts=regional_counts(build=build),
        )

    source_loader = source_loader or source.cache_source_chunk
    progress_path = progress_path or Path(output_dir) / f"{build_version}.jsonl"
    with logical_job_lock(logical_key=f"national-forest:{build_version}", wait=False) as acquired:
        if not acquired:
            raise ForestBuildIncompleteError("Another worker is already building this forest version.")
        _prepare_build(
            build=build,
            grid_build=grid_build,
            max_source_chunk_m=max_source_chunk_m,
        )
        chunks = list(ForestChunk.objects.filter(build=build).order_by("south_n", "west_e"))
        completed_before = sum(chunk.status == ForestChunk.Status.COMPLETED for chunk in chunks)
        processed = 0
        for forest_chunk in chunks:
            if forest_chunk.status == ForestChunk.Status.COMPLETED:
                continue
            if max_chunks is not None and processed >= max_chunks:
                break
            _process_chunk(
                build=build,
                forest_chunk=forest_chunk,
                cache_dir=Path(cache_dir),
                source_loader=source_loader,
                progress_path=progress_path,
            )
            processed += 1
        _finalise_build(
            build=build,
            output_dir=Path(output_dir),
            cache_dir=Path(cache_dir),
        )
    build.refresh_from_db()
    return BuildResult(
        build=build,
        processed_chunks=processed,
        reused_chunks=completed_before,
        elapsed_seconds=time.monotonic() - started,
        peak_rss_mb=_peak_rss_mb(),
        regional_counts=regional_counts(build=build),
    )


def _peak_rss_mb() -> float:
    """Return process peak resident memory in megabytes."""
    raw_value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return raw_value / divisor
