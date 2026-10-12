"""Read and validate the cached ISTAT regional boundary archive."""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import shapefile
from shapely import transform
from pyproj import CRS, Transformer
from shapely.geometry import MultiPolygon, shape

ARCHIVE_DATASET = "ISTAT regional boundaries 2026-01-01"
ARCHIVE_VERSION = "2026-01-01"
HTTP_MODIFIED = "2026-03-06T09:47:36Z"
SOURCE_CRS = "EPSG:32632"
GRID_CRS = "EPSG:3035"
ARCHIVE_SHA256 = "a9075f8d839dcb2b409099703da7bdd37cc214f8967fa7372b32305875ad046f"
OFFICIAL_URL = (
    "https://www.istat.it/storage/cartografia/confini_amministrativi/"
    "non_generalizzati/2026/Limiti01012026.zip"
)
SOURCE_PAGE = (
    "https://www.istat.it/notizia/confini-delle-unita-amministrative-a-fini-statistici-"
    "al-1-gennaio-2018-2/"
)
LICENSE_URL = "https://www.istat.it/note-legali/"
LICENSE = "CC BY 4.0 unless otherwise indicated"
CREDIT = "ISTAT, Confini delle Regioni al 1 gennaio 2026"
REGION_MEMBERS = (
    "Reg01012026/Reg01012026_WGS84.shp",
    "Reg01012026/Reg01012026_WGS84.shx",
    "Reg01012026/Reg01012026_WGS84.dbf",
    "Reg01012026/Reg01012026_WGS84.prj",
)


@dataclass(frozen=True)
class RegionBoundary:
    """Hold one validated region in the national grid CRS."""

    istat_code: str
    name: str
    geometry: MultiPolygon


@dataclass(frozen=True)
class BoundarySource:
    """Hold transformed regions and provenance for one boundary archive."""

    regions: tuple[RegionBoundary, ...]
    metadata: dict[str, Any]


class BoundarySourceError(ValueError):
    """Report a missing, changed or malformed boundary source."""


def archive_sha256(*, archive_path: Path) -> str:
    """Return the SHA256 hash of a boundary archive."""
    digest = hashlib.sha256()
    with archive_path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_boundary_source(
    *,
    archive_path: Path,
    expected_sha256: str = ARCHIVE_SHA256,
    downloaded_on: date | str | None = None,
    source_url: str = OFFICIAL_URL,
    source_page: str = SOURCE_PAGE,
    license_url: str = LICENSE_URL,
    credit: str = CREDIT,
) -> BoundarySource:
    """Validate the archive and return all 20 regions transformed to EPSG:3035."""
    archive_path = Path(archive_path)
    if not archive_path.is_file():
        raise BoundarySourceError(f"Boundary archive does not exist: {archive_path}.")
    actual_sha256 = archive_sha256(archive_path=archive_path)
    if actual_sha256 != expected_sha256:
        raise BoundarySourceError(
            f"Boundary archive hash mismatch: expected {expected_sha256}, got {actual_sha256}."
        )

    try:
        with zipfile.ZipFile(archive_path) as archive:
            _validate_members(archive=archive)
            regions = _read_regions(archive=archive)
    except (OSError, zipfile.BadZipFile, shapefile.ShapefileException) as exc:
        raise BoundarySourceError(f"Cannot read the boundary archive: {exc}") from exc

    if len(regions) != 20 or len({region.istat_code for region in regions}) != 20:
        raise BoundarySourceError("The boundary archive must contain 20 distinct regions.")
    download_date = downloaded_on.isoformat() if isinstance(downloaded_on, date) else downloaded_on
    return BoundarySource(
        regions=tuple(sorted(regions, key=lambda region: region.istat_code)),
        metadata={
            "dataset": ARCHIVE_DATASET,
            "version": ARCHIVE_VERSION,
            "archive_sha256": actual_sha256,
            "archive_size_bytes": archive_path.stat().st_size,
            "members": list(REGION_MEMBERS),
            "source_url": source_url,
            "source_page": source_page,
            "http_modified": HTTP_MODIFIED,
            "downloaded_on": download_date,
            "license": LICENSE,
            "license_url": license_url,
            "credit": credit,
            "source_crs": SOURCE_CRS,
            "grid_crs": GRID_CRS,
            "transformation": "ISTAT EPSG:32632 coordinates transformed once to EPSG:3035 before clipping.",
        },
    )


def _validate_members(*, archive: zipfile.ZipFile) -> None:
    names = set(archive.namelist())
    missing = [member for member in REGION_MEMBERS if member not in names]
    if missing:
        raise BoundarySourceError(f"Boundary archive is missing members: {', '.join(missing)}.")


def _read_regions(*, archive: zipfile.ZipFile) -> list[RegionBoundary]:
    buffers = {member: io.BytesIO(archive.read(member)) for member in REGION_MEMBERS}
    try:
        reader = shapefile.Reader(
            shp=buffers[REGION_MEMBERS[0]],
            shx=buffers[REGION_MEMBERS[1]],
            dbf=buffers[REGION_MEMBERS[2]],
            encoding="utf-8",
        )
        fields = {field[0] for field in reader.fields[1:]}
        if not {"COD_REG", "DEN_REG"}.issubset(fields):
            raise BoundarySourceError("The region DBF must contain COD_REG and DEN_REG.")
        projection = CRS.from_wkt(buffers[REGION_MEMBERS[3]].getvalue().decode("utf-8"))
        if projection != CRS.from_epsg(32632):
            raise BoundarySourceError(f"Expected EPSG:32632 source CRS, got {projection.to_string()}.")
        transformer = Transformer.from_crs(SOURCE_CRS, GRID_CRS, always_xy=True)
        result: list[RegionBoundary] = []
        for record, source_shape in zip(reader.records(), reader.shapes(), strict=True):
            code = _istat_code(record["COD_REG"])
            name = str(record["DEN_REG"]).strip()
            if not code or not name:
                raise BoundarySourceError("Region records must have a code and name.")
            geometry = shape(source_shape.__geo_interface__)
            if geometry.is_empty or not geometry.is_valid:
                raise BoundarySourceError(f"Invalid geometry for region {code}.")
            transformed = transform(geometry, transformer.transform, interleaved=False)
            if transformed.is_empty or not transformed.is_valid:
                raise BoundarySourceError(f"Invalid transformed geometry for region {code}.")
            if transformed.geom_type == "Polygon":
                transformed = MultiPolygon([transformed])
            elif transformed.geom_type != "MultiPolygon":
                raise BoundarySourceError(f"Unexpected geometry type for region {code}.")
            result.append(RegionBoundary(istat_code=code, name=name, geometry=transformed))
        return result
    finally:
        for buffer in buffers.values():
            buffer.close()


def _istat_code(value: object) -> str:
    text = str(value).strip()
    if text.isdigit():
        return text.zfill(2)
    return text


read_boundaries = read_boundary_source
load_boundary_source = read_boundary_source
