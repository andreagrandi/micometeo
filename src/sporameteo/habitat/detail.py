"""Real level of detail of a layer, measured from its own values.

Real detail is the average length of a stretch of identical values along rows and columns.
A layer whose values only change every 1 km cannot tell apart two 500 m squares.
"""

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

METRES_PER_DEGREE = 111_320


def is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def run_lengths(*, line: Sequence[Any], tolerance: float) -> list[int]:
    """Return the lengths of stretches whose values stay within the tolerance of their first value.

    Missing values end a stretch and are not counted.
    """
    runs = []
    length = 0
    start = None
    for value in line:
        if is_missing(value):
            if length:
                runs.append(length)
            length = 0
            start = None
            continue
        if start is not None and same_value(first=start, second=value, tolerance=tolerance):
            length += 1
            continue
        if length:
            runs.append(length)
        start = value
        length = 1
    if length:
        runs.append(length)
    return runs


def same_value(*, first: Any, second: Any, tolerance: float) -> bool:
    if isinstance(first, str) or isinstance(second, str):
        return first == second
    return abs(float(first) - float(second)) <= tolerance


def mean_run_length(*, lines: Sequence[Sequence[Any]], tolerance: float) -> float:
    """Return the average stretch length over all lines, or NaN if no line has a value."""
    runs = [run for line in lines for run in run_lengths(line=line, tolerance=tolerance)]
    return float(np.mean(runs)) if runs else math.nan


def real_detail_m(
    *,
    values: Sequence[Sequence[Any]],
    tolerance: float,
    spacing_east_m: float,
    spacing_north_m: float,
) -> float:
    """Return the real detail in metres, averaged over the east-west and north-south directions."""
    rows = [list(row) for row in values]
    columns = [list(column) for column in zip(*rows)]
    along_rows = mean_run_length(lines=rows, tolerance=tolerance) * spacing_east_m
    along_columns = mean_run_length(lines=columns, tolerance=tolerance) * spacing_north_m
    return round((along_rows + along_columns) / 2, 1)


def mixed_square_share(*, blocks: Sequence[Sequence[Any]]) -> float:
    """Return the share of squares holding more than one distinct value.

    Squares with no value are left out. A high share means the layer tells apart areas
    smaller than a square, even when its values change only every few hundred metres.
    """
    counted = 0
    mixed = 0
    for block in blocks:
        values = {value for value in block if not is_missing(value)}
        if values:
            counted += 1
            mixed += len(values) > 1
    return round(mixed / counted, 3) if counted else math.nan


def native_values(
    *, path: Path, bounds: tuple[float, float, float, float]
) -> tuple[list[list[Any]], float, float]:
    """Return the raw pixels inside the bounds in degrees, with pixel spacing east and north in metres.

    Missing pixels become NaN.
    """
    with rasterio.open(path) as source:
        native_bounds = transform_bounds("EPSG:4326", source.crs, *bounds)
        window = from_bounds(*native_bounds, transform=source.transform)
        window = window.round_offsets().round_lengths()
        values = source.read(1, window=window).astype("float64")
        if source.nodata is not None:
            values[values == source.nodata] = np.nan
        spacing_east, spacing_north = source.res
        if source.crs.is_geographic:
            latitude = (bounds[1] + bounds[3]) / 2
            spacing_north = spacing_north * METRES_PER_DEGREE
            spacing_east = spacing_east * METRES_PER_DEGREE * math.cos(math.radians(latitude))
    return values.tolist(), spacing_east, spacing_north
