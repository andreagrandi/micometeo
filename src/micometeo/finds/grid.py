"""Grid square IDs for points, following decision D1 in docs/decisions.md."""

import math

from pyproj import Transformer

CELL_SIZE_M = 500
_TO_LAEA = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)


def cell_id(*, latitude: float, longitude: float) -> str:
    """Return the ID of the 500 m square in EPSG:3035 that holds the point."""
    easting, northing = _TO_LAEA.transform(longitude, latitude)
    corner_e = math.floor(easting / CELL_SIZE_M) * CELL_SIZE_M
    corner_n = math.floor(northing / CELL_SIZE_M) * CELL_SIZE_M
    return f"{CELL_SIZE_M}m_E{corner_e}_N{corner_n}"
