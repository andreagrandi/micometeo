"""Sample area of 500 m squares and the 25 m pixel grid used to fill them.

Squares follow decision D1 in docs/decisions.md. Rows run north to south, like raster rows.
"""

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

from micometeo.finds.grid import CELL_SIZE_M

PIXEL_SIZE_M = 25
PIXELS_PER_SIDE = CELL_SIZE_M // PIXEL_SIZE_M
QUARTER_OFFSETS_M = [(125, 125), (375, 125), (125, 375), (375, 375)]
_TO_LAEA = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
_TO_WGS84 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)


@dataclass(frozen=True)
class SampleGrid:
    """Outer edges of the sample area in EPSG:3035 metres, on 500 m square corners."""

    west_e: int
    south_n: int
    east_e: int
    north_n: int

    @property
    def columns(self) -> int:
        return (self.east_e - self.west_e) // CELL_SIZE_M

    @property
    def rows(self) -> int:
        return (self.north_n - self.south_n) // CELL_SIZE_M

    @property
    def pixel_shape(self) -> tuple[int, int]:
        return (self.rows * PIXELS_PER_SIDE, self.columns * PIXELS_PER_SIDE)

    @property
    def pixel_transform(self) -> Affine:
        return from_origin(self.west_e, self.north_n, PIXEL_SIZE_M, PIXEL_SIZE_M)

    def corners(self) -> list[tuple[int, int]]:
        """Return the lower-left corner of every square, row by row from the north-west."""
        return [
            (self.west_e + column * CELL_SIZE_M, self.north_n - (row + 1) * CELL_SIZE_M)
            for row in range(self.rows)
            for column in range(self.columns)
        ]

    def bounds_degrees(self, *, margin: float = 0.0) -> tuple[float, float, float, float]:
        """Return west, south, east and north in WGS84 degrees, widened by the margin."""
        west, south, east, north = transform_bounds(
            "EPSG:3035", "EPSG:4326", self.west_e, self.south_n, self.east_e, self.north_n
        )
        return (west - margin, south - margin, east + margin, north + margin)


def build_grid(*, west: float, south: float, east: float, north: float) -> SampleGrid:
    """Return the smallest set of whole 500 m squares that covers the box in degrees."""
    eastings, northings = _TO_LAEA.transform(
        [west, east, west, east], [south, south, north, north]
    )
    return SampleGrid(
        west_e=math.floor(min(eastings) / CELL_SIZE_M) * CELL_SIZE_M,
        south_n=math.floor(min(northings) / CELL_SIZE_M) * CELL_SIZE_M,
        east_e=math.ceil(max(eastings) / CELL_SIZE_M) * CELL_SIZE_M,
        north_n=math.ceil(max(northings) / CELL_SIZE_M) * CELL_SIZE_M,
    )


def to_degrees(*, easting: float, northing: float) -> tuple[float, float]:
    """Return latitude and longitude of a point given in EPSG:3035 metres."""
    longitude, latitude = _TO_WGS84.transform(easting, northing)
    return latitude, longitude


def square_rows(*, grid: SampleGrid) -> list[dict[str, Any]]:
    """Return ID, corner and centre of every square in the grid."""
    rows = []
    for corner_e, corner_n in grid.corners():
        half = CELL_SIZE_M / 2
        latitude, longitude = to_degrees(easting=corner_e + half, northing=corner_n + half)
        rows.append(
            {
                "cell_id": f"{CELL_SIZE_M}m_E{corner_e}_N{corner_n}",
                "corner_e": corner_e,
                "corner_n": corner_n,
                "centre_latitude": round(latitude, 6),
                "centre_longitude": round(longitude, 6),
            }
        )
    return rows


def warp_to_grid(*, path: Path, grid: SampleGrid, resampling: Resampling) -> np.ndarray:
    """Reproject a raster onto the 25 m pixels of the grid. Missing pixels become NaN."""
    destination = np.full(grid.pixel_shape, np.nan, dtype="float32")
    with rasterio.open(path) as source:
        reproject(
            source=rasterio.band(source, 1),
            destination=destination,
            src_nodata=source.nodata,
            dst_transform=grid.pixel_transform,
            dst_crs="EPSG:3035",
            dst_nodata=np.nan,
            resampling=resampling,
        )
    return destination


def square_blocks(*, pixels: np.ndarray, grid: SampleGrid) -> np.ndarray:
    """Group 25 m pixels by square, giving shape rows times columns times 400."""
    side = PIXELS_PER_SIDE
    blocks = pixels.reshape(grid.rows, side, grid.columns, side).swapaxes(1, 2)
    return blocks.reshape(grid.rows * grid.columns, side * side)


def now_utc() -> str:
    """Return the current time in UTC as text."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_download_note(*, path: Path, details: dict[str, Any]) -> None:
    """Save the download time and details next to a raw file, for later cached runs."""
    note = {"downloaded_at": now_utc(), **details}
    note_path(path=path).write_text(json.dumps(note, indent=2), encoding="utf-8")


def read_download_note(*, path: Path) -> dict[str, Any]:
    """Return the download note saved next to a raw file."""
    return json.loads(note_path(path=path).read_text(encoding="utf-8"))


def note_path(*, path: Path) -> Path:
    return path.with_name(path.name + ".download.json")
