"""Soil acidity and texture from ISRIC SoilGrids 2.0, read from its 250 m files."""

from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

from sporameteo.habitat.grid import SampleGrid, square_blocks, write_download_note

FILE_URL = "https://files.isric.org/soilgrids/latest/data/{prop}/{prop}_{depth}_{stat}.vrt"
LICENCE = "CC BY 4.0"
STATS = ["mean", "Q0.05", "Q0.95"]
COLUMNS = {"phh2o": "soil_ph", "clay": "clay_pct", "sand": "sand_pct", "silt": "silt_pct"}
# SoilGrids stores pH times 10 and texture in g/kg. Both become plain units at 0.1.
SCALE = 0.1


def layer_id(*, prop: str, depth: str) -> str:
    return f"soilgrids_{prop}_{depth}"


def raw_name(*, prop: str, depth: str, stat: str) -> str:
    return f"soilgrids_{prop}_{depth}_{stat}.tif"


def download_soil(
    *,
    prop: str,
    depth: str,
    stat: str,
    bounds: tuple[float, float, float, float],
    raw_dir: Path,
) -> Path:
    """Save the 250 m pixels inside the bounds in their own map projection, unless saved."""
    path = raw_dir / raw_name(prop=prop, depth=depth, stat=stat)
    if path.exists():
        return path
    url = FILE_URL.format(prop=prop, depth=depth, stat=stat)
    with rasterio.open(f"/vsicurl/{url}") as source:
        native_bounds = transform_bounds("EPSG:4326", source.crs, *bounds)
        window = from_bounds(*native_bounds, transform=source.transform)
        window = window.round_offsets(op="floor").round_lengths(op="ceil")
        values = source.read(1, window=window)
        profile = {
            "driver": "GTiff",
            "height": values.shape[0],
            "width": values.shape[1],
            "count": 1,
            "dtype": values.dtype,
            "crs": source.crs,
            "transform": source.window_transform(window),
            "nodata": source.nodata,
        }
    with rasterio.open(path, "w", **profile) as target:
        target.write(values, 1)
    write_download_note(path=path, details={"url": url, "bounds": list(bounds)})
    return path


def soil_reliability(*, range_width: float, max_range: float) -> str:
    """Return medium when the 90 percent range is within the limit, low otherwise.

    SoilGrids values come from a model, so none is high.
    """
    return "medium" if range_width <= max_range else "low"


def summarise_soil(
    *,
    prop: str,
    depth: str,
    pixels: dict[str, np.ndarray],
    grid: SampleGrid,
    max_range: float,
) -> list[dict[str, Any]]:
    """Return one soil value with source and reliability for every square."""
    column = COLUMNS[prop]
    mean_blocks = square_blocks(pixels=pixels["mean"], grid=grid)
    low_blocks = square_blocks(pixels=pixels["Q0.05"], grid=grid)
    high_blocks = square_blocks(pixels=pixels["Q0.95"], grid=grid)
    rows = []
    for mean_block, low_block, high_block in zip(mean_blocks, low_blocks, high_blocks):
        if np.all(np.isnan(mean_block)):
            rows.append({column: None, f"{column}_source": None, f"{column}_reliability": None})
            continue
        value = float(np.nanmean(mean_block)) * SCALE
        range_widths = high_block - low_block
        if np.all(np.isnan(range_widths)):
            reliability = "low"
        else:
            reliability = soil_reliability(
                range_width=float(np.nanmean(range_widths)) * SCALE, max_range=max_range
            )
        rows.append(
            {
                column: round(value, 2),
                f"{column}_source": layer_id(prop=prop, depth=depth),
                f"{column}_reliability": reliability,
            }
        )
    return rows
