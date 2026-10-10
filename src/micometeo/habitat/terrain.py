"""Altitude, slope steepness and slope direction from the Copernicus 30 m elevation map."""

import math
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.merge import merge

from micometeo.habitat.grid import (
    PIXEL_SIZE_M,
    SampleGrid,
    square_blocks,
    write_download_note,
)

LAYER_ID = "copernicus_dem_glo30"
TILE_URL = (
    "https://copernicus-dem-30m.s3.amazonaws.com/"
    "Copernicus_DSM_COG_10_{name}_DEM/Copernicus_DSM_COG_10_{name}_DEM.tif"
)
LICENCE = (
    "Copernicus WorldDEM-30 licence, free of charge and worldwide. Derived data must say: "
    "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and "
    "Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; "
    "all rights reserved"
)
NODATA = -32767.0
RAW_NAME = "copernicus_dem_glo30.tif"


def tile_urls(*, west: float, south: float, east: float, north: float) -> list[str]:
    """Return the URL of every 1 degree tile that touches the box."""
    urls = []
    for latitude in range(math.floor(south), math.floor(north) + 1):
        for longitude in range(math.floor(west), math.floor(east) + 1):
            lat_part = f"{'N' if latitude >= 0 else 'S'}{abs(latitude):02d}_00"
            lon_part = f"{'E' if longitude >= 0 else 'W'}{abs(longitude):03d}_00"
            urls.append(TILE_URL.format(name=f"{lat_part}_{lon_part}"))
    return urls


def last_modified(*, url: str) -> str:
    """Return the Last-Modified header of a file on the web."""
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.headers.get("Last-Modified", "")


def download_dem(*, bounds: tuple[float, float, float, float], raw_dir: Path) -> Path:
    """Save the part of the elevation map inside the bounds, unless it is already saved."""
    path = raw_dir / RAW_NAME
    if path.exists():
        return path
    west, south, east, north = bounds
    urls = tile_urls(west=west, south=south, east=east, north=north)
    sources = [rasterio.open(f"/vsicurl/{url}") for url in urls]
    try:
        altitude, transform = merge(sources, bounds=bounds, nodata=NODATA, dtype="float32")
        profile = {
            "driver": "GTiff",
            "height": altitude.shape[1],
            "width": altitude.shape[2],
            "count": 1,
            "dtype": "float32",
            "crs": sources[0].crs,
            "transform": transform,
            "nodata": NODATA,
            "compress": "deflate",
        }
    finally:
        for source in sources:
            source.close()
    with rasterio.open(path, "w", **profile) as target:
        target.write(altitude[0], 1)
    write_download_note(
        path=path,
        details={
            "tiles": urls,
            "last_modified": [last_modified(url=url) for url in urls],
            "bounds": list(bounds),
        },
    )
    return path


def slope_and_aspect(
    *, altitude: np.ndarray, pixel_size: float
) -> tuple[np.ndarray, np.ndarray]:
    """Return slope in degrees and the direction the slope faces, clockwise from north.

    Rows run north to south. Flat pixels have no direction and get NaN.
    """
    rise_north, rise_east = np.gradient(altitude, pixel_size)
    rise_north = -rise_north
    steepness = np.hypot(rise_east, rise_north)
    slope = np.degrees(np.arctan(steepness))
    aspect = np.degrees(np.arctan2(-rise_east, -rise_north)) % 360
    aspect[steepness == 0] = np.nan
    return slope.astype("float32"), aspect.astype("float32")


def circular_mean(*, degrees: np.ndarray) -> tuple[float, float]:
    """Return the mean direction in degrees and the mean resultant length from 0 to 1.

    A length near 0 means the directions point every way.
    """
    values = degrees[~np.isnan(degrees)]
    if values.size == 0:
        return math.nan, 0.0
    radians = np.radians(values)
    east = float(np.mean(np.sin(radians)))
    north = float(np.mean(np.cos(radians)))
    return math.degrees(math.atan2(east, north)) % 360, math.hypot(east, north)


def coverage_reliability(*, valid_share: float) -> str | None:
    """Return high, low or None for a square from the share of pixels with a value."""
    if valid_share >= 0.95:
        return "high"
    if valid_share >= 0.5:
        return "low"
    return None


def summarise_terrain(
    *, altitude: np.ndarray, grid: SampleGrid, settings: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return altitude, slope and slope direction with reliability for every square."""
    slope, aspect = slope_and_aspect(altitude=altitude, pixel_size=PIXEL_SIZE_M)
    altitude_blocks = square_blocks(pixels=altitude, grid=grid)
    slope_blocks = square_blocks(pixels=slope, grid=grid)
    aspect_blocks = square_blocks(pixels=aspect, grid=grid)
    rows = []
    for altitude_block, slope_block, aspect_block in zip(
        altitude_blocks, slope_blocks, aspect_blocks
    ):
        row: dict[str, Any] = {}
        altitude_reliability = coverage_reliability(
            valid_share=float(np.mean(~np.isnan(altitude_block)))
        )
        slope_reliability = coverage_reliability(
            valid_share=float(np.mean(~np.isnan(slope_block)))
        )
        row["altitude_m"] = (
            round(float(np.nanmean(altitude_block)), 1) if altitude_reliability else None
        )
        row["altitude_m_reliability"] = altitude_reliability
        mean_slope = float(np.nanmean(slope_block)) if slope_reliability else None
        row["slope_deg"] = round(mean_slope, 1) if mean_slope is not None else None
        row["slope_deg_reliability"] = slope_reliability
        direction, resultant = circular_mean(degrees=aspect_block)
        aspect_reliability = slope_reliability
        if aspect_reliability and (
            mean_slope < settings["flat_slope_deg"]
            or resultant < settings["min_resultant_length"]
        ):
            aspect_reliability = "low"
        has_aspect = aspect_reliability is not None and not math.isnan(direction)
        row["aspect_deg"] = round(direction, 1) if has_aspect else None
        row["aspect_deg_reliability"] = aspect_reliability if has_aspect else None
        for column in ("altitude_m", "slope_deg", "aspect_deg"):
            row[f"{column}_source"] = LAYER_ID if row[column] is not None else None
        rows.append(row)
    return rows
