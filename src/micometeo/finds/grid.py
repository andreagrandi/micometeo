"""Grid square IDs for points, following decision D1 in docs/decisions.md."""

import math

from pyproj import Transformer

CELL_SIZE_M = 500
_TO_LAEA = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)


def cell_id(*, latitude: float, longitude: float, size_m: int = CELL_SIZE_M) -> str:
    """Return the ID of the square of size_m metres in EPSG:3035 that holds the point."""
    easting, northing = _TO_LAEA.transform(longitude, latitude)
    corner_e = math.floor(easting / size_m) * size_m
    corner_n = math.floor(northing / size_m) * size_m
    return f"{size_m}m_E{corner_e}_N{corner_n}"
