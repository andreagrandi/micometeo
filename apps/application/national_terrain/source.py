"""Cache and provenance handling for Copernicus DEM GLO-30 tiles."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import rasterio
from rasterio.transform import Affine

from micometeo.habitat import terrain


class TerrainSourceError(RuntimeError):
    """Report a source failure that leaves a build unfinished."""


class ConfirmedMissingTile(TerrainSourceError):
    """Report a source tile that the server explicitly does not provide."""


@dataclass(frozen=True)
class CachedTile:
    """Describe one cached source tile and its local path."""

    tile_name: str
    path: Path | None
    status: str
    metadata: dict[str, Any]
    reused: bool


_TILE_NAME_PATTERN = re.compile(
    r"^(?P<latitude>[NS])(?P<latitude_degrees>\d{2})_00_"
    r"(?P<longitude>[EW])(?P<longitude_degrees>\d{3})_00$"
)
_MIN_ITALY_LATITUDE = 35
_MAX_ITALY_LATITUDE = 47
_NATIVE_ARCSECOND = 1.0 / 3600.0
_NATIVE_TILE_PIXELS = 3600


def tile_url(*, tile_name: str) -> str:
    """Return the public 2021 AWS URL for one GLO-30 tile."""
    return terrain.TILE_URL.format(name=tile_name)


def sidecar_path(*, cache_dir: Path, tile_name: str) -> Path:
    """Return the JSON sidecar path for one stable tile name."""
    return cache_dir / f"{tile_name}.json"


def raster_path(*, cache_dir: Path, tile_name: str) -> Path:
    """Return the local raster path for one stable tile name."""
    return cache_dir / f"{tile_name}.tif"


def sha256_path(*, path: Path) -> str:
    """Return the SHA256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_fingerprint(*, records: list[dict[str, Any]]) -> str:
    """Return a stable fingerprint for source statuses and metadata."""
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def cache_tile(
    *,
    tile_name: str,
    cache_dir: Path,
    url: str | None = None,
    timeout_seconds: int = 60,
) -> CachedTile:
    """Reuse or atomically download and validate one source tile."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    resolved_url = url or tile_url(tile_name=tile_name)
    with _cache_tile_lock(cache_dir=cache_dir, tile_name=tile_name):
        return _cache_tile_locked(
            tile_name=tile_name,
            cache_dir=cache_dir,
            url=resolved_url,
            timeout_seconds=timeout_seconds,
        )


def _cache_tile_locked(
    *, tile_name: str, cache_dir: Path, url: str, timeout_seconds: int
) -> CachedTile:
    """Inspect, fetch, validate and publish one tile while its lock is held."""
    raster = raster_path(cache_dir=cache_dir, tile_name=tile_name)
    sidecar = sidecar_path(cache_dir=cache_dir, tile_name=tile_name)
    if sidecar.is_file():
        metadata = _read_json(path=sidecar)
        if metadata.get("status") == "confirmed_missing":
            return CachedTile(
                tile_name=tile_name,
                path=None,
                status="confirmed_missing",
                metadata=metadata,
                reused=True,
            )
        if metadata.get("status") == "available" and raster.is_file():
            expected = str(metadata.get("sha256", ""))
            if expected and sha256_path(path=raster) == expected:
                _validate_raster(path=raster, tile_name=tile_name)
                return CachedTile(
                    tile_name=tile_name,
                    path=raster,
                    status="available",
                    metadata=metadata,
                    reused=True,
                )
            raise TerrainSourceError(f"Cached checksum mismatch for {tile_name}.")

    check_cache_space(cache_dir=cache_dir, required_bytes=128 * 1024 * 1024)
    request = urllib.request.Request(url=url, method="GET")
    temporary_path: Path | None = None
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            last_modified = response.headers.get("Last-Modified", "")
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=cache_dir, prefix=f".{tile_name}.", suffix=".tmp", delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    temporary.write(block)
        raster_details = _validate_raster(path=temporary_path, tile_name=tile_name)
        digest = sha256_path(path=temporary_path)
        stat = temporary_path.stat()
        metadata = _available_metadata(
            tile_name=tile_name,
            url=url,
            last_modified=last_modified,
            size_bytes=stat.st_size,
            sha256=digest,
            raster_details=raster_details,
        )
        os.replace(temporary_path, raster)
        temporary_path = None
        _write_json(path=sidecar, value=metadata)
        return CachedTile(
            tile_name=tile_name,
            path=raster,
            status="available",
            metadata=metadata,
            reused=False,
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            metadata = _missing_metadata(tile_name=tile_name, url=url, error=str(exc))
            _write_json(path=sidecar, value=metadata)
            return CachedTile(
                tile_name=tile_name,
                path=None,
                status="confirmed_missing",
                metadata=metadata,
                reused=False,
            )
        metadata = _failed_metadata(tile_name=tile_name, url=url, error=str(exc))
        _write_json(path=sidecar, value=metadata)
        raise TerrainSourceError(f"Could not download {tile_name}: {exc}") from exc
    except (OSError, ValueError, rasterio.errors.RasterioIOError) as exc:
        metadata = _failed_metadata(tile_name=tile_name, url=url, error=str(exc))
        _write_json(path=sidecar, value=metadata)
        raise TerrainSourceError(f"Could not validate {tile_name}: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def check_cache_space(*, cache_dir: Path, required_bytes: int) -> None:
    """Ensure a tile download fits before opening a network response."""
    if required_bytes < 0:
        raise ValueError("required_bytes must not be negative.")
    cache_dir.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(cache_dir).free
    if free_bytes < required_bytes:
        raise TerrainSourceError(
            f"Insufficient free disk space for a source tile: {free_bytes} bytes available, "
            f"{required_bytes} required."
        )


def _available_metadata(
    *,
    tile_name: str,
    url: str,
    last_modified: str,
    size_bytes: int,
    sha256: str,
    raster_details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "tile_name": tile_name,
        "status": "available",
        "url": url,
        "release": terrain.SOURCE_RELEASE,
        "last_modified": last_modified or "",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "size_bytes": size_bytes,
        "sha256": sha256,
        "crs": raster_details["crs"],
        "native_pixel_m": terrain.SOURCE_NATIVE_PIXEL_M,
        "vertical_datum": terrain.SOURCE_VERTICAL_DATUM,
        "raster_width": raster_details["width"],
        "raster_height": raster_details["height"],
        "raster_dtype": raster_details["dtype"],
        "raster_nodata": raster_details["nodata"],
        "area_or_point": raster_details["area_or_point"],
        "credit": terrain.LICENCE,
        "source_registry": terrain.SOURCE_URL,
        "source_readme": terrain.SOURCE_README_URL,
        "source_dataset": terrain.SOURCE_DATASET_URL,
    }


def _missing_metadata(*, tile_name: str, url: str, error: str) -> dict[str, Any]:
    return {
        "tile_name": tile_name,
        "status": "confirmed_missing",
        "url": url,
        "release": terrain.SOURCE_RELEASE,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "error": error,
        "crs": terrain.SOURCE_CRS,
        "native_pixel_m": terrain.SOURCE_NATIVE_PIXEL_M,
        "vertical_datum": terrain.SOURCE_VERTICAL_DATUM,
        "credit": terrain.LICENCE,
        "source_registry": terrain.SOURCE_URL,
        "source_readme": terrain.SOURCE_README_URL,
        "source_dataset": terrain.SOURCE_DATASET_URL,
    }


def _failed_metadata(*, tile_name: str, url: str, error: str) -> dict[str, Any]:
    return {
        "tile_name": tile_name,
        "status": "failed",
        "url": url,
        "release": terrain.SOURCE_RELEASE,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "error": error,
        "crs": terrain.SOURCE_CRS,
        "native_pixel_m": terrain.SOURCE_NATIVE_PIXEL_M,
        "vertical_datum": terrain.SOURCE_VERTICAL_DATUM,
        "credit": terrain.LICENCE,
        "source_registry": terrain.SOURCE_URL,
        "source_readme": terrain.SOURCE_README_URL,
        "source_dataset": terrain.SOURCE_DATASET_URL,
    }


def _validate_raster(*, path: Path, tile_name: str) -> dict[str, Any]:
    latitude, longitude = _tile_coordinates(tile_name=tile_name)
    expected_transform = Affine(
        _NATIVE_ARCSECOND,
        0.0,
        longitude - (_NATIVE_ARCSECOND / 2),
        0.0,
        -_NATIVE_ARCSECOND,
        latitude + 1.0 + (_NATIVE_ARCSECOND / 2),
    )
    with rasterio.open(path) as source:
        if (
            source.count != 1
            or source.width != _NATIVE_TILE_PIXELS
            or source.height != _NATIVE_TILE_PIXELS
        ):
            raise ValueError("GLO-30 elevation tile must be one 3600 by 3600 band.")
        if source.crs is None or source.crs.to_epsg() != 4326:
            raise ValueError("GLO-30 elevation tile must use EPSG:4326.")
        if source.dtypes[0] != "float32":
            raise ValueError("GLO-30 elevation tile must use float32 values.")
        if source.nodata is not None:
            raise ValueError("GLO-30 elevation tile must have no declared nodata value.")
        for actual, expected in zip(source.transform, expected_transform, strict=True):
            if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError(
                    f"GLO-30 elevation tile {tile_name!r} has an unexpected "
                    "one-arcsecond transform."
                )
        if source.tags().get("AREA_OR_POINT") != "Point":
            raise ValueError("GLO-30 elevation tile must declare AREA_OR_POINT=Point.")
        return {
            "crs": source.crs.to_string(),
            "width": source.width,
            "height": source.height,
            "dtype": source.dtypes[0],
            "nodata": source.nodata,
            "area_or_point": source.tags()["AREA_OR_POINT"],
        }


def _tile_coordinates(*, tile_name: str) -> tuple[int, int]:
    match = _TILE_NAME_PATTERN.fullmatch(tile_name)
    if match is None:
        raise ValueError(f"Unsupported GLO-30 tile name: {tile_name!r}.")
    latitude = int(match["latitude_degrees"])
    if match["latitude"] == "S":
        latitude = -latitude
    longitude = int(match["longitude_degrees"])
    if match["longitude"] == "W":
        longitude = -longitude
    if not _MIN_ITALY_LATITUDE <= latitude <= _MAX_ITALY_LATITUDE:
        raise ValueError(
            f"GLO-30 tile latitude {latitude} is outside the supported Italy range "
            f"{_MIN_ITALY_LATITUDE} to {_MAX_ITALY_LATITUDE}."
        )
    return latitude, longitude


def _read_json(*, path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Source sidecar is not an object: {path}")
    return value


def _write_json(*, path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


@contextmanager
def _cache_tile_lock(*, cache_dir: Path, tile_name: str) -> Iterator[None]:
    """Serialize inspection and publication for one source tile."""
    lock_path = cache_dir / f".{tile_name}.lock"
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
