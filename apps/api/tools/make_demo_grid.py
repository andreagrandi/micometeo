"""Generate the demo grid file for the demo API.

Run with `uv run python apps/api/tools/make_demo_grid.py`.
"""

import gzip
import json
from pathlib import Path

import numpy as np
from pyproj import Transformer

BOX = {"west": 10.62, "south": 43.72, "east": 11.05, "north": 44.18}
SIZE_M = 500
OUTPUT = Path(__file__).resolve().parent.parent / "micometeo_api" / "demo_grid.json.gz"


def main() -> None:
    """Write demo_grid.json.gz with every square whose centre is inside the box."""
    to_metres = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
    to_degrees = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)

    corner_lons = [BOX["west"], BOX["east"], BOX["east"], BOX["west"]]
    corner_lats = [BOX["south"], BOX["south"], BOX["north"], BOX["north"]]
    xs, ys = to_metres.transform(corner_lons, corner_lats)
    x_start = int(min(xs) // SIZE_M * SIZE_M) - SIZE_M
    x_end = int(max(xs) // SIZE_M * SIZE_M) + SIZE_M
    y_start = int(min(ys) // SIZE_M * SIZE_M) - SIZE_M
    y_end = int(max(ys) // SIZE_M * SIZE_M) + SIZE_M

    grid_x, grid_y = np.meshgrid(
        np.arange(x_start, x_end + SIZE_M, SIZE_M),
        np.arange(y_start, y_end + SIZE_M, SIZE_M),
    )
    grid_x = grid_x.ravel()
    grid_y = grid_y.ravel()
    centre_lon, centre_lat = to_degrees.transform(
        grid_x + SIZE_M / 2, grid_y + SIZE_M / 2
    )
    inside = (
        (centre_lon >= BOX["west"])
        & (centre_lon <= BOX["east"])
        & (centre_lat >= BOX["south"])
        & (centre_lat <= BOX["north"])
    )
    grid_x = grid_x[inside]
    grid_y = grid_y[inside]

    offsets = [(0, 0), (SIZE_M, 0), (SIZE_M, SIZE_M), (0, SIZE_M)]
    corner_columns = []
    for dx, dy in offsets:
        lon, lat = to_degrees.transform(grid_x + dx, grid_y + dy)
        corner_columns.append((np.round(lon, 5), np.round(lat, 5)))

    cells = []
    for index in range(len(grid_x)):
        row: list = [f"{SIZE_M}m_E{int(grid_x[index])}_N{int(grid_y[index])}"]
        for lon, lat in corner_columns:
            row.extend([float(lon[index]), float(lat[index])])
        cells.append(row)

    # Each cell is [cell_id, lon, lat, ...] for the lower left, lower right,
    # upper right and upper left corners.
    payload = {"box": BOX, "cell_size_m": SIZE_M, "cells": cells}
    # Gzipped to stay under the 500 KB limit of the commit hook. A fixed mtime keeps the file the same on every run.
    data = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    OUTPUT.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))
    print(f"Wrote {len(cells)} squares to {OUTPUT}")


if __name__ == "__main__":
    main()
