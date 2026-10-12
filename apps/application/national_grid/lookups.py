"""Look up completed national-grid cells by ID or WGS84 coordinates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from pyproj import Transformer
from shapely import transform
from shapely.geometry import mapping
from shapely.wkb import loads

from micometeo.finds.grid import CELL_SIZE_M, cell_id as point_cell_id, parse_cell_id

from .models import GridBuild, GridBuildCell

_TO_WGS84 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)


@dataclass(frozen=True)
class LookupResult:
    """Return a stable lookup status and, when found, its geometries."""

    status: str
    build_version: str | None = None
    cell_id: str | None = None
    corner_e: int | None = None
    corner_n: int | None = None
    land_share: float | None = None
    owner_region: dict[str, str] | None = None
    full_geometry: dict[str, Any] | None = None
    land_geometry: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "build_version": self.build_version,
            "cell_id": self.cell_id,
            "corner_e": self.corner_e,
            "corner_n": self.corner_n,
            "land_share": self.land_share,
            "owner_region": self.owner_region,
            "full_geometry": self.full_geometry,
            "land_geometry": self.land_geometry,
        }


def lookup_national_grid(
    *,
    cell_id: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    build_version: str | None = None,
) -> LookupResult:
    """Look up one completed-build membership without nearest-cell fallback."""
    if cell_id is not None and (latitude is not None or longitude is not None):
        return LookupResult(status="invalid")
    if cell_id is None and (latitude is None or longitude is None):
        return LookupResult(status="invalid")
    if latitude is not None or longitude is not None:
        if latitude is None or longitude is None or not _valid_coordinate(
            latitude=latitude, longitude=longitude
        ):
            return LookupResult(status="invalid")
        try:
            cell_id = point_cell_id(latitude=latitude, longitude=longitude)
        except ValueError:
            return LookupResult(status="invalid")
    try:
        address = parse_cell_id(cell_id, expected_size_m=CELL_SIZE_M)
    except ValueError:
        return LookupResult(status="invalid")
    build = _find_build(build_version=build_version)
    if build is None:
        return LookupResult(status="unknown_build", build_version=build_version)
    if build.status != GridBuild.Status.COMPLETED:
        return LookupResult(status="unfinished_build", build_version=build.version)
    membership = (
        GridBuildCell.objects.select_related("cell", "owner_region")
        .filter(build=build, cell_id=cell_id)
        .first()
    )
    if membership is None:
        return LookupResult(status="outside", build_version=build.version, cell_id=cell_id)
    return LookupResult(
        status="found",
        build_version=build.version,
        cell_id=membership.cell_id,
        corner_e=address.corner_e,
        corner_n=address.corner_n,
        land_share=membership.land_share,
        owner_region={
            "istat_code": membership.owner_region.istat_code,
            "name": membership.owner_region.name,
        },
        full_geometry=_wgs84_geometry(membership.cell.geometry),
        land_geometry=_wgs84_geometry(membership.land_geometry),
    )


def _find_build(*, build_version: str | None) -> GridBuild | None:
    query = GridBuild.objects.all()
    if build_version is not None:
        return query.filter(version=build_version).first()
    return query.filter(status=GridBuild.Status.COMPLETED).order_by("-completed_at", "-created_at").first()


def _valid_coordinate(*, latitude: float, longitude: float) -> bool:
    return (
        not isinstance(latitude, bool)
        and not isinstance(longitude, bool)
        and math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )


def _wgs84_geometry(geometry: Any) -> dict[str, Any]:
    transformed = transform(loads(bytes(geometry.wkb)), _TO_WGS84.transform, interleaved=False)
    return mapping(transformed)


def lookup_by_cell_id(*, cell_id: str, build_version: str | None = None) -> LookupResult:
    """Look up one cell ID in a completed build."""
    return lookup_national_grid(cell_id=cell_id, build_version=build_version)


def lookup_by_coordinates(
    *, latitude: float, longitude: float, build_version: str | None = None
) -> LookupResult:
    """Look up the cell containing one WGS84 coordinate."""
    return lookup_national_grid(
        latitude=latitude,
        longitude=longitude,
        build_version=build_version,
    )
