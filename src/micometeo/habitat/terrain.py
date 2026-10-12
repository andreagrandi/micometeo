"""Altitude, slope steepness and slope direction from the Copernicus 30 m elevation map."""

import math
import urllib.request
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.merge import merge
from rasterio.transform import Affine, from_origin
from rasterio.warp import transform_bounds

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
    "all rights reserved. "
    "The organisations in charge of the Copernicus programme by law or by delegation do not "
    "incur any liability for any use of the Copernicus WorldDEM-30"
)
NODATA = -32767.0
RAW_NAME = "copernicus_dem_glo30.tif"
ALGORITHM_VERSION = "national-terrain-v2"
SOURCE_RELEASE = "Copernicus DEM GLO-30 public AWS copy, 2021"
SOURCE_URL = "https://registry.opendata.aws/copernicus-dem/"
SOURCE_README_URL = "https://copernicus-dem-30m.s3.amazonaws.com/readme.html"
SOURCE_DATASET_URL = (
    "https://dataspace.copernicus.eu/explore-data/data-collections/"
    "copernicus-contributing-missions/collections-description/COP-DEM"
)
SOURCE_CRS = "EPSG:4326"
SOURCE_VERTICAL_DATUM = "EGM2008"
SOURCE_NATIVE_PIXEL_M = 30.0
PROCESSING_PIXEL_M = PIXEL_SIZE_M
MARGIN_PIXELS = 1
REPROJECT_METHOD = "coordinate-exact-four-pixel-bilinear"


def tile_urls(*, west: float, south: float, east: float, north: float) -> list[str]:
    """Return the URL of every 1 degree tile that touches the box."""
    urls = []
    for latitude in range(math.floor(south), math.floor(north) + 1):
        for longitude in range(math.floor(west), math.floor(east) + 1):
            lat_part = f"{'N' if latitude >= 0 else 'S'}{abs(latitude):02d}_00"
            lon_part = f"{'E' if longitude >= 0 else 'W'}{abs(longitude):03d}_00"
            urls.append(TILE_URL.format(name=f"{lat_part}_{lon_part}"))
    return urls


def tile_names(*, west: float, south: float, east: float, north: float) -> list[str]:
    """Return stable GLO-30 names for every one degree tile touching a box."""
    names = []
    for latitude in range(math.floor(south), math.floor(north) + 1):
        for longitude in range(math.floor(west), math.floor(east) + 1):
            lat_part = f"{'N' if latitude >= 0 else 'S'}{abs(latitude):02d}_00"
            lon_part = f"{'E' if longitude >= 0 else 'W'}{abs(longitude):03d}_00"
            names.append(f"{lat_part}_{lon_part}")
    return names


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
    values = np.asarray(altitude, dtype="float32")
    if values.ndim != 2 or min(values.shape) < 2:
        raise ValueError("Altitude must be a two-dimensional array with at least two rows and columns.")
    valid = np.isfinite(values)
    # np.gradient has no missing-value semantics. Restore the source mask after
    # calculating the derivative so a source gap cannot become a terrain value.
    rise_north, rise_east = np.gradient(values, pixel_size)
    rise_north = -rise_north
    steepness = np.hypot(rise_east, rise_north)
    slope = np.degrees(np.arctan(steepness))
    aspect = np.degrees(np.arctan2(-rise_east, -rise_north)) % 360
    invalid = ~valid | ~np.isfinite(steepness)
    slope[invalid] = np.nan
    aspect[invalid | (steepness == 0)] = np.nan
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
    return summarise_terrain_arrays(
        altitude=altitude,
        slope=slope,
        aspect=aspect,
        grid=grid,
        settings=settings,
    )


def summarise_terrain_arrays(
    *,
    altitude: np.ndarray,
    slope: np.ndarray,
    aspect: np.ndarray,
    grid: SampleGrid,
    settings: dict[str, Any],
) -> list[dict[str, Any]]:
    """Summarise precomputed terrain arrays using the pilot quality rules."""
    if altitude.shape != slope.shape or altitude.shape != aspect.shape:
        raise ValueError("Altitude, slope and aspect arrays must have the same shape.")
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
        row["altitude_m_valid_fraction"] = float(np.mean(np.isfinite(altitude_block)))
        mean_slope = float(np.nanmean(slope_block)) if slope_reliability else None
        row["slope_deg"] = round(mean_slope, 1) if mean_slope is not None else None
        row["slope_deg_reliability"] = slope_reliability
        row["slope_deg_valid_fraction"] = float(np.mean(np.isfinite(slope_block)))
        direction, resultant = circular_mean(degrees=aspect_block)
        aspect_reliability = slope_reliability
        if aspect_reliability and (
            mean_slope < settings["flat_slope_deg"]
            or resultant < settings["min_resultant_length"]
        ):
            aspect_reliability = "low"
        is_flat = mean_slope is not None and mean_slope < settings["flat_slope_deg"]
        has_aspect = aspect_reliability is not None and not math.isnan(direction) and not is_flat
        row["aspect_deg"] = round(direction, 1) % 360 if has_aspect else None
        row["aspect_deg_reliability"] = aspect_reliability
        row["aspect_deg_valid_fraction"] = float(np.mean(np.isfinite(aspect_block)))
        row["source_gap"] = (
            row["altitude_m_valid_fraction"] < 1.0
            or row["slope_deg_valid_fraction"] < 1.0
        )
        for column in ("altitude_m", "slope_deg", "aspect_deg"):
            row[f"{column}_source"] = LAYER_ID if row[column] is not None else None
        rows.append(row)
    return rows


@dataclass(frozen=True)
class ProcessingWindow:
    """Describe one 25 metre raster window with a one-pixel margin."""

    west_e: int
    south_n: int
    east_e: int
    north_n: int
    margin_pixels: int = MARGIN_PIXELS

    @property
    def expanded_west_e(self) -> int:
        return self.west_e - self.margin_pixels * PROCESSING_PIXEL_M

    @property
    def expanded_south_n(self) -> int:
        return self.south_n - self.margin_pixels * PROCESSING_PIXEL_M

    @property
    def expanded_east_e(self) -> int:
        return self.east_e + self.margin_pixels * PROCESSING_PIXEL_M

    @property
    def expanded_north_n(self) -> int:
        return self.north_n + self.margin_pixels * PROCESSING_PIXEL_M

    @property
    def core_shape(self) -> tuple[int, int]:
        return (
            (self.north_n - self.south_n) // PROCESSING_PIXEL_M,
            (self.east_e - self.west_e) // PROCESSING_PIXEL_M,
        )

    @property
    def expanded_shape(self) -> tuple[int, int]:
        rows, columns = self.core_shape
        side = self.margin_pixels * 2
        return rows + side, columns + side

    @property
    def expanded_transform(self) -> Affine:
        return from_origin(
            self.expanded_west_e,
            self.expanded_north_n,
            PROCESSING_PIXEL_M,
            PROCESSING_PIXEL_M,
        )


def source_bounds_for_window(
    *, window: ProcessingWindow, native_pixel_m: float = SOURCE_NATIVE_PIXEL_M
) -> tuple[float, float, float, float]:
    """Return a densified WGS84 box including one native source pixel."""
    west, south, east, north = transform_bounds(
        "EPSG:3035",
        "EPSG:4326",
        window.expanded_west_e,
        window.expanded_south_n,
        window.expanded_east_e,
        window.expanded_north_n,
        densify_pts=21,
    )
    # One native pixel around the footprint protects bilinear samples at tile edges.
    longitude_margin = native_pixel_m / 100_000
    latitude_margin = native_pixel_m / 100_000
    return (
        west - longitude_margin,
        south - latitude_margin,
        east + longitude_margin,
        north + latitude_margin,
    )


def _align_bounds_to_source_grid(
    *, bounds: tuple[float, float, float, float], transform: Affine
) -> tuple[float, float, float, float]:
    """Align a source box to the source raster's native pixel grid."""
    if transform.b != 0 or transform.d != 0 or transform.a <= 0 or transform.e >= 0:
        raise ValueError("Source elevation tile must use an unrotated north-up grid.")
    west, south, east, north = bounds
    pixel_width = transform.a
    pixel_height = abs(transform.e)
    origin_west = transform.c
    origin_north = transform.f
    left = origin_west + math.floor((west - origin_west) / pixel_width) * pixel_width
    right = origin_west + math.ceil((east - origin_west) / pixel_width) * pixel_width
    top = origin_north - math.floor((origin_north - north) / pixel_height) * pixel_height
    bottom = origin_north - math.ceil((origin_north - south) / pixel_height) * pixel_height
    return left, bottom, right, top


def mosaic_source_tiles(
    *,
    tile_paths: Iterable[Path],
    bounds: tuple[float, float, float, float],
) -> tuple[np.ndarray, Affine, str, float | int | None]:
    """Mosaic bounded source windows before one canonical reprojection."""
    paths = list(tile_paths)
    if not paths:
        raise ValueError("At least one source tile is required.")
    sources = [rasterio.open(path) for path in paths]
    try:
        source_crs = sources[0].crs
        if source_crs is None:
            raise ValueError("Source elevation tile has no coordinate system.")
        source_bounds = bounds
        if source_crs.to_string() != SOURCE_CRS:
            source_bounds = transform_bounds(
                SOURCE_CRS,
                source_crs,
                *bounds,
                densify_pts=21,
            )
        source_bounds = _align_bounds_to_source_grid(
            bounds=source_bounds,
            transform=sources[0].transform,
        )
        source_transform = sources[0].transform
        values, transform = merge(
            sources,
            bounds=source_bounds,
            nodata=NODATA,
            dtype="float32",
            res=(source_transform.a, abs(source_transform.e)),
        )
        return values[0], transform, source_crs.to_string(), NODATA
    finally:
        for source in sources:
            source.close()


def reproject_mosaic_to_window(
    *,
    mosaic: np.ndarray,
    source_transform: Affine,
    source_crs: str,
    source_nodata: float | int | None,
    window: ProcessingWindow,
) -> np.ndarray:
    """Reproject one bounded mosaic with fixed four-pixel bilinear sampling."""
    rows, columns = window.expanded_shape
    eastings = window.expanded_west_e + (
        np.arange(columns, dtype="float64") + 0.5
    ) * PROCESSING_PIXEL_M
    northings = window.expanded_north_n - (
        np.arange(rows, dtype="float64") + 0.5
    ) * PROCESSING_PIXEL_M
    destination_e, destination_n = np.meshgrid(eastings, northings)
    transformer = Transformer.from_crs("EPSG:3035", source_crs, always_xy=True)
    source_e, source_n = transformer.transform(destination_e, destination_n)
    inverse = ~source_transform
    source_column, source_row = inverse @ (source_e, source_n)
    source_column -= 0.5
    source_row -= 0.5
    column_0 = np.floor(source_column).astype("int64")
    row_0 = np.floor(source_row).astype("int64")
    fraction_column = source_column - column_0
    fraction_row = source_row - row_0
    valid = (
        (row_0 >= 0)
        & (column_0 >= 0)
        & (row_0 + 1 < mosaic.shape[0])
        & (column_0 + 1 < mosaic.shape[1])
    )
    total = np.zeros((rows, columns), dtype="float64")
    weight = np.zeros((rows, columns), dtype="float64")
    nodata = NODATA if source_nodata is None else source_nodata
    neighbours = (
        (0, 0, (1 - fraction_row) * (1 - fraction_column)),
        (0, 1, (1 - fraction_row) * fraction_column),
        (1, 0, fraction_row * (1 - fraction_column)),
        (1, 1, fraction_row * fraction_column),
    )
    for row_offset, column_offset, neighbour_weight in neighbours:
        values = np.zeros((rows, columns), dtype="float64")
        values[valid] = mosaic[
            row_0[valid] + row_offset,
            column_0[valid] + column_offset,
        ]
        neighbour_valid = valid & np.isfinite(values) & (values != nodata)
        total[neighbour_valid] += values[neighbour_valid] * neighbour_weight[neighbour_valid]
        weight[neighbour_valid] += neighbour_weight[neighbour_valid]
    destination = np.full((rows, columns), np.nan, dtype="float32")
    valid_destination = weight > 0
    destination[valid_destination] = (
        total[valid_destination] / weight[valid_destination]
    ).astype("float32")
    return destination


def crop_processing_margin(*, values: np.ndarray, window: ProcessingWindow) -> np.ndarray:
    """Remove the margin after calculating derivatives on the expanded window."""
    margin = window.margin_pixels
    rows, columns = window.core_shape
    return values[margin : margin + rows, margin : margin + columns]


def summarise_processing_window(
    *,
    altitude: np.ndarray,
    window: ProcessingWindow,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Calculate terrain on an expanded window and return only its core squares."""
    if settings is None:
        settings = {"flat_slope_deg": 5.0, "min_resultant_length": 0.3}
    expected_shape = window.expanded_shape
    if altitude.shape != expected_shape:
        raise ValueError(f"Altitude shape {altitude.shape} does not match {expected_shape}.")
    slope, aspect = slope_and_aspect(altitude=altitude, pixel_size=PROCESSING_PIXEL_M)
    core_altitude = crop_processing_margin(values=altitude, window=window)
    core_slope = crop_processing_margin(values=slope, window=window)
    core_aspect = crop_processing_margin(values=aspect, window=window)
    grid = SampleGrid(
        west_e=window.west_e,
        south_n=window.south_n,
        east_e=window.east_e,
        north_n=window.north_n,
    )
    return summarise_terrain_arrays(
        altitude=core_altitude,
        slope=core_slope,
        aspect=core_aspect,
        grid=grid,
        settings=settings,
    )
