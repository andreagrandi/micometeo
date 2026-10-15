"""Grid square IDs for points, following decision D1 in docs/decisions.md."""

import math
import re
from typing import NamedTuple

from pyproj import Transformer

CELL_SIZE_M = 500
_CELL_ID_RE = re.compile(r"^(?P<size>\d+)m_E(?P<e>-?\d+)_N(?P<n>-?\d+)$")
_TO_LAEA = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)


class CellAddress(NamedTuple):
    """Store the size and lower-left corner encoded by a cell ID."""

    size_m: int
    corner_e: int
    corner_n: int


def format_cell_id(*, corner_e: int, corner_n: int, size_m: int = CELL_SIZE_M) -> str:
    """Return a validated lower-left-corner ID for one aligned square."""
    _validate_size(size_m=size_m)
    _validate_corner(corner=corner_e, size_m=size_m, name="easting")
    _validate_corner(corner=corner_n, size_m=size_m, name="northing")
    return f"{size_m}m_E{corner_e}_N{corner_n}"


def parse_cell_id(value: str, *, expected_size_m: int | None = None) -> CellAddress:
    """Parse and validate a lower-left-corner cell ID."""
    if not isinstance(value, str):
        raise ValueError("Cell ID must be text.")
    match = _CELL_ID_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"Malformed cell ID: {value!r}.")
    address = CellAddress(
        size_m=int(match.group("size")),
        corner_e=int(match.group("e")),
        corner_n=int(match.group("n")),
    )
    _validate_size(size_m=address.size_m)
    _validate_corner(corner=address.corner_e, size_m=address.size_m, name="easting")
    _validate_corner(corner=address.corner_n, size_m=address.size_m, name="northing")
    if expected_size_m is not None and address.size_m != expected_size_m:
        raise ValueError(f"Cell ID uses {address.size_m} m, expected {expected_size_m} m.")
    return address


def _validate_size(*, size_m: int) -> None:
    if not isinstance(size_m, int) or isinstance(size_m, bool) or size_m <= 0:
        raise ValueError("Cell size must be a positive integer.")


def _validate_corner(*, corner: int, size_m: int, name: str) -> None:
    if corner % size_m != 0:
        raise ValueError(f"The {name} corner must be aligned to the cell size.")


def _corner_for_point(*, latitude: float, longitude: float, size_m: int) -> tuple[int, int]:
    _validate_size(size_m=size_m)
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        raise ValueError("Latitude and longitude must be numbers.")
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError("Latitude and longitude must be finite.")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Latitude or longitude is outside WGS84 bounds.")
    easting, northing = _TO_LAEA.transform(longitude, latitude)
    if not math.isfinite(easting) or not math.isfinite(northing):
        raise ValueError("The coordinate cannot be transformed to EPSG:3035.")
    return (math.floor(easting / size_m) * size_m, math.floor(northing / size_m) * size_m)


def cell_id(*, latitude: float, longitude: float, size_m: int = CELL_SIZE_M) -> str:
    """Return the ID of the square of size_m metres in EPSG:3035 that holds the point."""
    corner_e, corner_n = _corner_for_point(
        latitude=latitude,
        longitude=longitude,
        size_m=size_m,
    )
    return format_cell_id(corner_e=corner_e, corner_n=corner_n, size_m=size_m)
