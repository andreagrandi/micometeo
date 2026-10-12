"""Fetch and validate Copernicus HRL Forest Type 2018 source chunks."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import fcntl
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine, from_origin

SOURCE_RELEASE = "2018"
SERVICE_URL = (
    "https://image.discomap.eea.europa.eu/arcgis/rest/services/"
    "GioLandPublic/HRL_ForestType_2018/ImageServer"
)
SERVICE_METADATA_URL = f"{SERVICE_URL}?f=pjson"
EXPORT_URL = f"{SERVICE_URL}/exportImage"
CATALOGUE_URL = (
    "https://sdi.eea.europa.eu/catalogue/srv/api/records/"
    "59b0620c-7bb4-4c82-b3ce-f16715573137"
)
SOURCE_RESOLUTION_M = 10
SOURCE_CRS = "EPSG:3035"
# The live ImageServer currently returns this older EPSG:3035 WKT.  PROJ
# distinguishes its explicit ETRS89 datum code from the newer EPSG datum
# ensemble, although both identify the same canonical projected CRS here.
LEGACY_EPSG3035_WKT = (
    'PROJCS["ETRS89-extended / LAEA Europe",GEOGCS["ETRS89",'
    'DATUM["European_Terrestrial_Reference_System_1989",'
    'SPHEROID["GRS 1980",6378137,298.257222101004,AUTHORITY["EPSG","7019"]],'
    'AUTHORITY["EPSG","6258"]],PRIMEM["Greenwich",0],'
    'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
    'AUTHORITY["EPSG","4258"]],PROJECTION["Lambert_Azimuthal_Equal_Area"],'
    'PARAMETER["latitude_of_center",52],PARAMETER["longitude_of_center",10],'
    'PARAMETER["false_easting",4321000],PARAMETER["false_northing",3210000],'
    'UNIT["metre",1],AXIS["Easting",EAST],AXIS["Northing",NORTH],'
    'AUTHORITY["EPSG","3035"]]'
)
# GDAL writes the same known legacy CRS with these explicit unit authorities
# and its own axis order when it serialises a GeoTIFF CRS.
LEGACY_EPSG3035_RASTERIO_WKT = (
    'PROJCS["ETRS89-extended / LAEA Europe",GEOGCS["ETRS89",'
    'DATUM["European_Terrestrial_Reference_System_1989",'
    'SPHEROID["GRS 1980",6378137,298.257222101,AUTHORITY["EPSG","7019"]],'
    'AUTHORITY["EPSG","6258"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],'
    'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
    'AUTHORITY["EPSG","4258"]],PROJECTION["Lambert_Azimuthal_Equal_Area"],'
    'PARAMETER["latitude_of_center",52],PARAMETER["longitude_of_center",10],'
    'PARAMETER["false_easting",4321000],PARAMETER["false_northing",3210000],'
    'UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Northing",NORTH],'
    'AXIS["Easting",EAST],AUTHORITY["EPSG","3035"]]'
)
_CURRENT_CRS = CRS.from_string(SOURCE_CRS)
_LEGACY_CRS = CRS.from_wkt(LEGACY_EPSG3035_WKT)
_LEGACY_CRS_WKT = _LEGACY_CRS.to_wkt()
RESAMPLING = "nearest"
MAX_WIDTH = 15_000
MAX_HEIGHT = 4_100
MAX_SOURCE_CHUNK_M = 40_000
PIXEL_CODES = frozenset({0, 1, 2, 254, 255})
LICENCE = (
    "Copernicus Land Monitoring Service data, free and open access under EU Regulation "
    "1159/2013."
)
CREDIT = (
    "© European Union, Copernicus Land Monitoring Service 2018, "
    "European Environment Agency"
)


class ForestSourceError(RuntimeError):
    """Report a transport, cache or GeoTIFF validation failure."""


@dataclass(frozen=True)
class CachedForestChunk:
    """Describe one validated source chunk in the local cache."""

    cache_key: str
    path: Path
    metadata: dict[str, Any]
    reused: bool


def source_metadata() -> dict[str, Any]:
    """Return the fixed source facts recorded with every forest build."""
    return {
        "release": SOURCE_RELEASE,
        "service_url": SERVICE_URL,
        "service_metadata_url": SERVICE_METADATA_URL,
        "export_url": EXPORT_URL,
        "catalogue_url": CATALOGUE_URL,
        "resolution_m": SOURCE_RESOLUTION_M,
        "crs": SOURCE_CRS,
        "resampling": RESAMPLING,
        "licence": LICENCE,
        "credit": CREDIT,
        "pixel_codes": sorted(PIXEL_CODES),
        "max_width": MAX_WIDTH,
        "max_height": MAX_HEIGHT,
    }


def _normalise_bounds(*, bounds: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Validate and return a positive aligned EPSG:3035 request box."""
    if len(bounds) != 4:
        raise ValueError("Forest source bounds must have four edges.")
    converted = tuple(int(value) for value in bounds)
    if any(value != original for value, original in zip(converted, bounds, strict=True)):
        raise ValueError("Forest source bounds must be integer metre edges.")
    west, south, east, north = converted
    if east <= west or north <= south:
        raise ValueError("Forest source bounds must have positive width and height.")
    if any(value % SOURCE_RESOLUTION_M for value in (west, south, east, north)):
        raise ValueError("Forest source bounds must be aligned to ten metres.")
    width = (east - west) // SOURCE_RESOLUTION_M
    height = (north - south) // SOURCE_RESOLUTION_M
    if width > MAX_WIDTH or height > MAX_HEIGHT:
        raise ValueError("Forest source requests exceed the ArcGIS image size limits.")
    return west, south, east, north


def build_request(
    *,
    bounds: tuple[int, int, int, int],
    resolution_m: int = SOURCE_RESOLUTION_M,
    service_url: str = SERVICE_URL,
) -> dict[str, Any]:
    """Return exact ArcGIS exportImage parameters for one source chunk."""
    west, south, east, north = _normalise_bounds(bounds=bounds)
    if resolution_m != SOURCE_RESOLUTION_M:
        raise ValueError("Forest source resolution must be ten metres.")
    width = (east - west) // resolution_m
    height = (north - south) // resolution_m
    return {
        "bbox": f"{west},{south},{east},{north}",
        "bboxSR": 3035,
        "size": f"{width},{height}",
        "imageSR": 3035,
        "format": "tiff",
        "pixelType": "U8",
        "interpolation": "RSP_NearestNeighbor",
        "f": "image",
    }


def request_url(*, request_options: dict[str, Any]) -> str:
    """Return the export URL with stable query ordering."""
    options = dict(request_options)
    service_url = str(options.pop("service_url", SERVICE_URL))
    query = urllib.parse.urlencode(options)
    return f"{service_url.rstrip('/')}/exportImage?{query}"


def cache_key(
    *,
    bounds: tuple[int, int, int, int],
    release: str = SOURCE_RELEASE,
    resolution_m: int = SOURCE_RESOLUTION_M,
    service_url: str = SERVICE_URL,
    request_options: dict[str, Any] | None = None,
) -> str:
    """Hash bounds and every request input into one stable cache key."""
    options = request_options or build_request(
        bounds=bounds,
        resolution_m=resolution_m,
        service_url=service_url,
    )
    identity = {
        "bounds": list(_normalise_bounds(bounds=bounds)),
        "release": release,
        "resolution_m": resolution_m,
        "service_url": service_url,
        "request_options": options,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def raster_path(*, cache_dir: Path, key: str) -> Path:
    """Return the GeoTIFF path for a cache key."""
    return Path(cache_dir) / f"{key}.tif"


def sidecar_path(*, cache_dir: Path, key: str) -> Path:
    """Return the JSON sidecar path for a cache key."""
    return Path(cache_dir) / f"{key}.json"


def sha256_path(*, path: Path) -> str:
    """Return the SHA256 digest of one file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def expected_shape(*, bounds: tuple[int, int, int, int]) -> tuple[int, int]:
    """Return source raster height and width for one request box."""
    west, south, east, north = _normalise_bounds(bounds=bounds)
    return (north - south) // SOURCE_RESOLUTION_M, (east - west) // SOURCE_RESOLUTION_M


def validate_raster(*, path: Path, bounds: tuple[int, int, int, int]) -> dict[str, Any]:
    """Validate one GeoTIFF's CRS, transform, size, type and source codes."""
    west, south, east, north = _normalise_bounds(bounds=bounds)
    expected_height, expected_width = expected_shape(bounds=bounds)
    try:
        with rasterio.open(path) as source:
            if source.count != 1:
                raise ForestSourceError("Forest source GeoTIFF must contain one band.")
            if (source.height, source.width) != (expected_height, expected_width):
                raise ForestSourceError("Forest source GeoTIFF dimensions do not match its request.")
            if source.crs is None or not _is_allowed_crs(source.crs):
                raise ForestSourceError("Forest source GeoTIFF must use EPSG:3035.")
            expected_transform = from_origin(west, north, SOURCE_RESOLUTION_M, SOURCE_RESOLUTION_M)
            if not _same_transform(source.transform, expected_transform):
                raise ForestSourceError("Forest source GeoTIFF transform does not match its request.")
            if not _same_bounds(source.bounds, (west, south, east, north)):
                raise ForestSourceError("Forest source GeoTIFF bounds do not match its request.")
            if source.dtypes[0].lower() != "uint8":
                raise ForestSourceError("Forest source GeoTIFF must use unsigned eight-bit pixels.")
            observed: set[int] = set()
            for _, window in source.block_windows(1):
                observed.update(np.unique(source.read(1, window=window)).tolist())
            unsupported = observed - PIXEL_CODES
            if unsupported:
                raise ForestSourceError(
                    f"Forest source GeoTIFF contains unsupported code(s): {sorted(unsupported)}."
                )
            return {
                "width": source.width,
                "height": source.height,
                "crs": SOURCE_CRS,
                "crs_wkt": source.crs.to_wkt(),
                "transform": tuple(source.transform),
                "bounds": [west, south, east, north],
                "dtype": source.dtypes[0],
                "codes": sorted(observed),
            }
    except ForestSourceError:
        raise
    except (OSError, rasterio.errors.RasterioIOError) as exc:
        raise ForestSourceError(f"Forest source is not a readable GeoTIFF: {exc}") from exc


def _is_allowed_crs(value: CRS) -> bool:
    """Accept current EPSG:3035 or the exact legacy WKT returned by the service."""
    if value == _CURRENT_CRS:
        return True
    actual_wkt = value.to_wkt()
    return actual_wkt in {
        LEGACY_EPSG3035_WKT,
        LEGACY_EPSG3035_RASTERIO_WKT,
        _LEGACY_CRS_WKT,
    }


def _same_transform(actual: Affine, expected: Affine) -> bool:
    return all(abs(left - right) <= 1e-7 for left, right in zip(actual, expected, strict=True))


def _same_bounds(actual: Any, expected: tuple[int, int, int, int]) -> bool:
    return all(abs(float(left) - right) <= 1e-6 for left, right in zip(actual, expected, strict=True))


def _read_json(*, path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ForestSourceError(f"Forest source sidecar is not an object: {path}.")
    return value


def _write_json(*, path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        json.dump(value, temporary, sort_keys=True, indent=2)
        temporary.write("\n")
    os.replace(temporary_path, path)


def _cached_metadata(
    *,
    key: str,
    bounds: tuple[int, int, int, int],
    request_options: dict[str, Any],
    path: Path,
    retrieved_at: str,
    validation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "cache_key": key,
        "bounds": list(bounds),
        "release": SOURCE_RELEASE,
        "resolution_m": SOURCE_RESOLUTION_M,
        "service_url": SERVICE_URL,
        "request_options": request_options,
        "request_url": request_url(request_options=request_options),
        "retrieved_at": retrieved_at,
        "sha256": sha256_path(path=path),
        "raw_bytes": path.stat().st_size,
        "source_path": str(path),
        "source_crs_wkt": validation["crs_wkt"],
        **source_metadata(),
    }


@contextmanager
def _cache_key_lock(*, cache_dir: Path, key: str) -> Iterator[None]:
    """Serialize inspection and publication for one cache key."""
    lock_path = Path(cache_dir) / f".{key}.lock"
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _cache_source_chunk_locked(
    *,
    normalised_bounds: tuple[int, int, int, int],
    cache_dir: Path,
    key: str,
    options: dict[str, Any],
    timeout_seconds: int,
) -> CachedForestChunk:
    """Inspect, fetch and publish one cache key while its lock is held."""
    path = raster_path(cache_dir=cache_dir, key=key)
    sidecar = sidecar_path(cache_dir=cache_dir, key=key)
    for temporary_path in cache_dir.glob(f".{key}.*.tmp"):
        temporary_path.unlink(missing_ok=True)

    if path.is_file() or sidecar.is_file():
        if not path.is_file() or not sidecar.is_file():
            path.unlink(missing_ok=True)
            sidecar.unlink(missing_ok=True)
        else:
            metadata = _read_json(path=sidecar)
            expected_digest = str(metadata.get("sha256", ""))
            if expected_digest != sha256_path(path=path):
                raise ForestSourceError(f"Forest source cache checksum mismatch for {key}.")
            validation = validate_raster(path=path, bounds=normalised_bounds)
            changed = False
            if metadata.get("source_crs_wkt") != validation["crs_wkt"]:
                metadata["source_crs_wkt"] = validation["crs_wkt"]
                changed = True
            if metadata.get("source_path") != str(path):
                metadata["source_path"] = str(path)
                changed = True
            if changed:
                _write_json(path=sidecar, value=metadata)
            return CachedForestChunk(cache_key=key, path=path, metadata=metadata, reused=True)

    temporary_path: Path | None = None
    try:
        url = request_url(request_options=options)
        request = urllib.request.Request(url=url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=cache_dir,
                prefix=f".{key}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    temporary.write(block)
        validation = validate_raster(path=temporary_path, bounds=normalised_bounds)
        os.replace(temporary_path, path)
        temporary_path = None
        metadata = _cached_metadata(
            key=key,
            bounds=normalised_bounds,
            request_options=options,
            path=path,
            retrieved_at=datetime.now(UTC).isoformat(),
            validation=validation,
        )
        _write_json(path=sidecar, value=metadata)
        return CachedForestChunk(cache_key=key, path=path, metadata=metadata, reused=False)
    except ForestSourceError:
        raise
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise ForestSourceError(f"Could not download forest source chunk {key}: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def cache_source_chunk(
    *,
    bounds: tuple[int, int, int, int],
    cache_dir: Path,
    timeout_seconds: int = 300,
    request_options: dict[str, Any] | None = None,
) -> CachedForestChunk:
    """Reuse or atomically download and validate one source GeoTIFF."""
    normalised_bounds = _normalise_bounds(bounds=bounds)
    options = dict(request_options or build_request(bounds=normalised_bounds))
    key = cache_key(bounds=normalised_bounds, request_options=options)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    with _cache_key_lock(cache_dir=cache_dir, key=key):
        return _cache_source_chunk_locked(
            normalised_bounds=normalised_bounds,
            cache_dir=cache_dir,
            key=key,
            options=options,
            timeout_seconds=timeout_seconds,
        )


# Short aliases make the cache operation convenient to use from the build
# service and retain the same naming pattern as the national terrain app.
cache_chunk = cache_source_chunk
download_source_chunk = cache_source_chunk
build_query = build_request
validate_source_raster = validate_raster
cache_raster = cache_source_chunk
SOURCE_CATALOGUE_URL = CATALOGUE_URL
SERVICE_CATALOGUE_URL = CATALOGUE_URL
