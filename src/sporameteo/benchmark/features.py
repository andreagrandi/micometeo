"""Weather and habitat features for the P4b comparison, one row per case square or comparison point.

Weather comes from ERA5 hourly time series, one file per 0.25 degree cell, summed into Italian days.
Habitat comes from the Copernicus forest type tiles and the Copernicus 90 m elevation map.
"""

import io
import math
import re
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import cdsapi
import numpy as np
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
import rasterio
from pyproj import Transformer

from sporameteo.habitat.forest import LICENCE as FOREST_LICENCE
from sporameteo.habitat.forest import mask_unusable
from sporameteo.habitat.grid import read_download_note, write_download_note

MIN_YEAR = 2017
WINDOW_DAYS = (7, 14, 30)
SQUARE_SIZE_M = 500
FOREST_PIXEL_M = 100
FOREST_PIXELS_PER_SIDE = SQUARE_SIZE_M // FOREST_PIXEL_M
WEATHER_START = "2016-12-01"
ERA5_DATASET = "reanalysis-era5-single-levels-timeseries"
ERA5_URL = "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-timeseries"
ERA5_LICENCE = (
    "Copernicus licence for ERA5, free and open under CC-BY 4.0. Credit: Generated using "
    "Copernicus Climate Change Service information 2026, Hersbach et al."
)
DEM_URL = (
    "https://copernicus-dem-90m.s3.amazonaws.com/"
    "Copernicus_DSM_COG_30_{name}_DEM/Copernicus_DSM_COG_30_{name}_DEM.tif"
)
DEM_LICENCE = (
    "Copernicus WorldDEM-90 licence, free of charge and worldwide. Derived data must say: "
    "produced using Copernicus WorldDEM-90 © DLR e.V. 2010-2014 and © Airbus Defence and "
    "Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; "
    "all rights reserved"
)
DEM_NODATA = -32767.0
DEM_ARC_SECONDS = 3
METRES_PER_DEGREE_LATITUDE = 111_320.0
ROME = ZoneInfo("Europe/Rome")
EPOCH_DAY = date(1970, 1, 1).toordinal()
WEATHER_COLUMNS = [f"{name}_{days}d_{unit}" for name, unit in (("rain", "mm"), ("temp", "c")) for days in WINDOW_DAYS]
OUTPUT_COLUMNS = [
    "case_id", "set", "area", "block_id", "year", "assessment_date", "point_kind", "cell_id",
    "latitude", "longitude", "forest_share", "broadleaf_share", "altitude_m", "slope_deg",
    "rain_7d_mm", "rain_14d_mm", "rain_30d_mm", "temp_7d_c", "temp_14d_c", "temp_30d_c",
]  # fmt: skip
_TO_LAEA = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)


def source_record(*, name: str, url: str, licence: str, version: str, note: dict[str, Any]) -> dict[str, Any]:
    """Return the keyword arguments for RunContext.add_source from a download note."""
    return {
        "name": name,
        "url": url,
        "licence": licence,
        "version": version,
        "downloaded_at": note["downloaded_at"],
        "query": note["query"],
    }


# Weather


def era5_cell(*, latitude: float, longitude: float) -> tuple[float, float]:
    """Return the centre of the 0.25 degree ERA5 cell that holds the place."""
    return round(latitude * 4) / 4, round(longitude * 4) / 4


def era5_path(*, cell: tuple[float, float], weather_dir: Path) -> Path:
    return weather_dir / f"era5_lat{cell[0]:.2f}_lon{cell[1]:.2f}.zip"


def fetch_cell(*, cell: tuple[float, float], weather_dir: Path, end_date: str, start_date: str = WEATHER_START) -> Path:
    """Download the hourly series of one cell, unless it is saved, and write the download note.

    The file is written under a .part name and renamed when complete.
    """
    path = era5_path(cell=cell, weather_dir=weather_dir)
    if path.exists():
        return path
    weather_dir.mkdir(parents=True, exist_ok=True)
    query = {
        "variable": ["2m_temperature", "total_precipitation"],
        "location": {"latitude": cell[0], "longitude": cell[1]},
        "date": [f"{start_date}/{end_date}"],
        "data_format": "csv",
    }
    part = path.with_name(path.name + ".part")
    cdsapi.Client(quiet=True).retrieve(ERA5_DATASET, query, str(part))
    part.rename(path)
    write_download_note(path=path, details={"url": ERA5_URL, "query": query})
    return path


def fetch_missing(
    *, cells: list[tuple[float, float]], weather_dir: Path, end_date: str, workers: int, start_date: str = WEATHER_START
) -> list[tuple[float, float]]:
    """Download every cell whose file is missing, with several requests at once. Return the cells fetched."""
    missing = [cell for cell in cells if not era5_path(cell=cell, weather_dir=weather_dir).exists()]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(
            pool.map(
                lambda cell: fetch_cell(cell=cell, weather_dir=weather_dir, end_date=end_date, start_date=start_date),
                missing,
            )
        )
    return missing


@lru_cache(maxsize=8)
def _offsets_seconds(*, first_hour: int, last_hour: int) -> np.ndarray:
    """Return the Europe/Rome offset from UTC in seconds for each UTC hour in the range."""
    offsets = np.empty(last_hour - first_hour + 1, dtype="int64")
    for index in range(offsets.size):
        moment = datetime.fromtimestamp((first_hour + index) * 3600, tz=UTC).astimezone(ROME)
        offsets[index] = int(moment.utcoffset().total_seconds())
    return offsets


def local_day_numbers(*, hours: np.ndarray) -> np.ndarray:
    """Return the Italian calendar day, as days since 1970-01-01, of each instant given as UTC hours since 1970."""
    offsets = _offsets_seconds(first_hour=int(hours.min()), last_hour=int(hours.max()))
    local_hours = hours + offsets[hours - hours.min()] // 3600
    return local_hours // 24


def daily_values(*, hours: np.ndarray, values: np.ndarray, shift_hours: int, average: bool) -> tuple[int, np.ndarray]:
    """Return the first day number and one value per Italian day, NaN when any hour of the day is missing.

    The shift moves each value to an earlier instant, so rain of the hour ending at 01:00 counts for the hour before.
    """
    first_hour, last_hour = int(hours.min()), int(hours.max())
    full = np.full(last_hour - first_hour + 1, np.nan)
    full[hours - first_hour] = values
    full_hours = np.arange(first_hour, last_hour + 1)
    padded = np.arange(first_hour - 48, last_hour + 49)
    days = local_day_numbers(hours=full_hours - shift_hours)
    first_day = int(days[0])
    padded_days = local_day_numbers(hours=padded - shift_hours)
    index = days - first_day
    size = int(index.max()) + 1
    expected = np.bincount(padded_days[(padded_days >= first_day) & (padded_days <= days[-1])] - first_day, minlength=size)
    present = np.bincount(index, weights=~np.isnan(full), minlength=size)
    totals = np.bincount(index, weights=np.nan_to_num(full), minlength=size)
    if average:
        totals = totals / np.maximum(present, 1)
    totals[present != expected] = np.nan
    return first_day, totals


@dataclass(frozen=True)
class DailySeries:
    """Rain in mm and mean temperature in degrees Celsius for each Italian day from first_day."""

    first_day: int
    rain_mm: np.ndarray
    temp_c: np.ndarray


def read_cell_file(*, path: Path) -> DailySeries:
    """Read one ERA5 zip and return its daily rain and temperature."""
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".csv")]
        content = archive.read(names[0])
    table = pacsv.read_csv(
        io.BytesIO(content),
        convert_options=pacsv.ConvertOptions(
            column_types={"valid_time": pa.timestamp("s"), "t2m": pa.float64(), "tp": pa.float64()},
            include_columns=["valid_time", "t2m", "tp"],
        ),
    )
    hours = table["valid_time"].cast(pa.int64()).to_numpy() // 3600
    temperature = table["t2m"].to_numpy(zero_copy_only=False)
    rain = table["tp"].to_numpy(zero_copy_only=False)
    rain_first, rain_days = daily_values(hours=hours, values=rain * 1000.0, shift_hours=1, average=False)
    temp_first, temp_days = daily_values(hours=hours, values=temperature - 273.15, shift_hours=0, average=True)
    start = min(rain_first, temp_first)
    end = max(rain_first + rain_days.size, temp_first + temp_days.size)
    rain_all = np.full(end - start, np.nan)
    temp_all = np.full(end - start, np.nan)
    rain_all[rain_first - start : rain_first - start + rain_days.size] = rain_days
    temp_all[temp_first - start : temp_first - start + temp_days.size] = temp_days
    return DailySeries(first_day=start, rain_mm=rain_all, temp_c=temp_all)


def window_values(*, series: DailySeries, day_numbers: np.ndarray, days: int, kind: str) -> np.ndarray:
    """Return the rain sum or mean temperature over the days that end the day before each date.

    The result is NaN when any day of the window is missing or outside the series.
    """
    values = series.rain_mm if kind == "rain" else series.temp_c
    missing = np.isnan(values)
    sums = np.concatenate([[0.0], np.cumsum(np.where(missing, 0.0, values))])
    gaps = np.concatenate([[0], np.cumsum(missing)])
    end = day_numbers - series.first_day  # index of day D, the window stops before it
    start = end - days
    inside = (start >= 0) & (end <= values.size)
    safe_start = np.clip(start, 0, values.size)
    safe_end = np.clip(end, 0, values.size)
    total = sums[safe_end] - sums[safe_start]
    complete = inside & (gaps[safe_end] - gaps[safe_start] == 0)
    if kind == "temp":
        total = total / days
    return np.where(complete, total, np.nan)


def day_number(*, text: str) -> int:
    """Return an ISO date as days since 1970-01-01."""
    return date.fromisoformat(text).toordinal() - EPOCH_DAY


def weather_features(
    *, latitudes: np.ndarray, longitudes: np.ndarray, dates: list[str], weather_dir: Path
) -> tuple[dict[str, np.ndarray], list[tuple[float, float]], list[dict[str, Any]]]:
    """Return the six weather columns, the cells without a file, and the download records.

    Rows in a cell without a file get NaN.
    """
    rows = len(dates)
    result = {name: np.full(rows, np.nan) for name in WEATHER_COLUMNS}
    day_numbers = np.array([day_number(text=text) for text in dates], dtype="int64")
    keys = np.round(latitudes * 4).astype("int64") * 100_000 + np.round(longitudes * 4).astype("int64")
    missing: list[tuple[float, float]] = []
    sources: list[dict[str, Any]] = []
    for key in np.unique(keys):
        selected = np.nonzero(keys == key)[0]
        cell = era5_cell(latitude=float(latitudes[selected[0]]), longitude=float(longitudes[selected[0]]))
        path = era5_path(cell=cell, weather_dir=weather_dir)
        if not path.exists():
            missing.append(cell)
            continue
        series = read_cell_file(path=path)
        for days in WINDOW_DAYS:
            result[f"rain_{days}d_mm"][selected] = window_values(
                series=series, day_numbers=day_numbers[selected], days=days, kind="rain"
            )
            result[f"temp_{days}d_c"][selected] = window_values(
                series=series, day_numbers=day_numbers[selected], days=days, kind="temp"
            )
        sources.append(
            source_record(
                name=f"ERA5 hourly time series {path.name}",
                url=ERA5_URL,
                licence=ERA5_LICENCE,
                version="ERA5 reconstructed past weather, hourly, one 0.25 degree cell",
                note=read_download_note(path=path),
            )
        )
    return result, missing, sources


# Forest


def parse_square_id(*, cell_id: str) -> tuple[int, int]:
    """Return the lower-left corner (east, north) in EPSG:3035 metres of a square ID."""
    match = re.fullmatch(r"500m_E(\d+)_N(\d+)", cell_id)
    if match is None:
        raise ValueError(f"Not a 500 m square ID: {cell_id}")
    return int(match.group(1)), int(match.group(2))


def block_forest_shares(*, pixels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return forest share and broadleaf share for each 500 m square of a 100 m pixel array.

    Pixels are 0 no forest, 1 broadleaf, 2 conifer, above 2 unusable. Forest share counts usable pixels only.
    Broadleaf share is broadleaf over forest pixels, NaN where there is no forest.
    """
    values = mask_unusable(pixels=pixels)
    side = FOREST_PIXELS_PER_SIDE
    rows, columns = values.shape
    blocks = values.reshape(rows // side, side, columns // side, side)
    usable = (~np.isnan(blocks)).sum(axis=(1, 3))
    broadleaf = (blocks == 1).sum(axis=(1, 3))
    forest = broadleaf + (blocks == 2).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        forest_share = np.where(usable > 0, forest / np.maximum(usable, 1), np.nan)
        broadleaf_share = np.where(forest > 0, broadleaf / np.maximum(forest, 1), np.nan)
    return forest_share, broadleaf_share


def forest_features(*, east: np.ndarray, north: np.ndarray, tile_paths: list[Path]) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Return forest share, broadleaf share and download records for squares given by lower-left corners.

    Squares outside every tile get NaN. The tile boxes come from the file names.
    """
    forest = np.full(east.size, np.nan)
    broadleaf = np.full(east.size, np.nan)
    covered = np.zeros(east.size, dtype=bool)
    sources: list[dict[str, Any]] = []
    for path in tile_paths:
        match = re.search(r"_E(\d+)_N(\d+)_E(\d+)_N(\d+)\.tif$", path.name)
        if match is None:
            continue
        west, south, tile_east, tile_north = (int(part) for part in match.groups())
        column = (east - west) // SQUARE_SIZE_M
        row = (tile_north - north - SQUARE_SIZE_M) // SQUARE_SIZE_M
        inside = (
            ~covered
            & (east >= west)
            & (east + SQUARE_SIZE_M <= tile_east)
            & (north >= south)
            & (north + SQUARE_SIZE_M <= tile_north)
        )
        note = read_download_note(path=path)
        sources.append(
            source_record(
                name="Copernicus forest type 2018 tile",
                url=note["url"],
                licence=FOREST_LICENCE,
                version="Forest type 2018 from the EEA image service",
                note=note,
            )
        )
        if not inside.any():
            continue
        with rasterio.open(path) as source:
            pixels = source.read(1)
        forest_blocks, broadleaf_blocks = block_forest_shares(pixels=pixels)
        forest[inside] = forest_blocks[row[inside], column[inside]]
        broadleaf[inside] = broadleaf_blocks[row[inside], column[inside]]
        covered |= inside
    return forest, broadleaf, sources


# Terrain


def dem_tile_name(*, latitude: int, longitude: int) -> str:
    lat_part = f"{'N' if latitude >= 0 else 'S'}{abs(latitude):02d}_00"
    lon_part = f"{'E' if longitude >= 0 else 'W'}{abs(longitude):03d}_00"
    return f"{lat_part}_{lon_part}"


def download_dem_tile(*, latitude: int, longitude: int, dem_dir: Path) -> Path:
    """Save one 1 degree tile of the 90 m elevation map, unless it is saved. A tile over open sea does not exist."""
    name = dem_tile_name(latitude=latitude, longitude=longitude)
    path = dem_dir / f"copernicus_dem_glo90_{name}.tif"
    if path.exists():
        return path
    url = DEM_URL.format(name=name)
    dem_dir.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=300) as response:
        content = response.read()
    part = path.with_name(path.name + ".part")
    part.write_bytes(content)
    part.rename(path)
    write_download_note(path=path, details={"url": url, "query": {"tile": name}})
    return path


def tile_slope(*, altitude: np.ndarray, top: float, latitude_step: float) -> np.ndarray:
    """Return slope in degrees for a tile whose rows run north to south.

    Pixel sizes in metres come from the degree step and the latitude of each row.
    """
    row_latitudes = top - (np.arange(altitude.shape[0]) + 0.5) * latitude_step
    step_north = latitude_step * METRES_PER_DEGREE_LATITUDE
    step_east = step_north * np.cos(np.radians(row_latitudes))
    rise_north = -np.gradient(altitude, step_north, axis=0)
    rise_east = np.gradient(altitude, axis=1) / step_east[:, None]
    return np.degrees(np.arctan(np.hypot(rise_east, rise_north))).astype("float32")


def terrain_features(
    *, east: np.ndarray, north: np.ndarray, latitudes: np.ndarray, longitudes: np.ndarray, dem_dir: Path
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Return mean altitude, mean slope and download records for squares given by lower-left corners.

    Each value is the mean over the 90 m elevation pixels whose centre lies inside the 500 m square.
    Squares with no pixel get NaN. Tiles that do not exist, such as open sea, are skipped.
    """
    keys = (east // SQUARE_SIZE_M).astype("int64") * 10_000_000 + (north // SQUARE_SIZE_M).astype("int64")
    sorted_keys, first_index, inverse = np.unique(keys, return_index=True, return_inverse=True)
    sums_altitude = np.zeros(sorted_keys.size)
    sums_slope = np.zeros(sorted_keys.size)
    counts = np.zeros(sorted_keys.size)
    tiles = sorted(
        {
            (int(math.floor(latitude + dy)), int(math.floor(longitude + dx)))
            for latitude, longitude in zip(latitudes[first_index], longitudes[first_index])
            for dy in (-0.01, 0.01)
            for dx in (-0.01, 0.01)
        }
    )
    sources: list[dict[str, Any]] = []
    for tile_latitude, tile_longitude in tiles:
        try:
            path = download_dem_tile(latitude=tile_latitude, longitude=tile_longitude, dem_dir=dem_dir)
        except urllib.error.HTTPError as error:
            if error.code in (403, 404):
                continue
            raise
        note = read_download_note(path=path)
        sources.append(
            source_record(
                name=f"Copernicus DEM GLO-90 tile {path.stem}",
                url=note["url"],
                licence=DEM_LICENCE,
                version="Copernicus DEM GLO-90, 3 arc second",
                note=note,
            )
        )
        with rasterio.open(path) as source:
            altitude = source.read(1).astype("float32")
            transform = source.transform
        altitude[altitude == DEM_NODATA] = np.nan
        rows, columns = altitude.shape
        step = -transform.e
        slope = tile_slope(altitude=altitude, top=transform.f, latitude_step=step).ravel()
        grid_columns, grid_rows = np.meshgrid(np.arange(columns), np.arange(rows))
        pixel_east, pixel_north = _TO_LAEA.transform(
            transform.c + (grid_columns.ravel() + 0.5) * transform.a,
            transform.f - (grid_rows.ravel() + 0.5) * step,
        )
        pixel_keys = np.floor(pixel_east / SQUARE_SIZE_M).astype("int64") * 10_000_000 + np.floor(
            pixel_north / SQUARE_SIZE_M
        ).astype("int64")
        position = np.clip(np.searchsorted(sorted_keys, pixel_keys), 0, sorted_keys.size - 1)
        flat_altitude = altitude.ravel()
        hit = (sorted_keys[position] == pixel_keys) & ~np.isnan(flat_altitude) & ~np.isnan(slope)
        np.add.at(sums_altitude, position[hit], flat_altitude[hit])
        np.add.at(sums_slope, position[hit], slope[hit])
        np.add.at(counts, position[hit], 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_altitude = np.where(counts > 0, sums_altitude / np.maximum(counts, 1), np.nan)
        mean_slope = np.where(counts > 0, sums_slope / np.maximum(counts, 1), np.nan)
    return mean_altitude[inverse], mean_slope[inverse], sources


# Table


def build_feature_table(
    *, run_dir: Path, weather_dir: Path, forest_tiles: list[Path], dem_dir: Path
) -> tuple[pa.Table, list[tuple[float, float]], list[dict[str, Any]]]:
    """Build the feature table from a P4a run folder.

    Returns the table, the weather cells without a file, and the download records for add_source.
    Only cases from 2017 on and not in the buffer set are kept, with their comparison points.
    """
    cases = pq.read_table(run_dir / "cases.parquet").to_pylist()
    cases = [case for case in cases if case["year"] >= MIN_YEAR and case["set"] != "buffer"]
    by_case = {case["case_id"]: case for case in cases}
    points = [
        point for point in pq.read_table(run_dir / "comparison_points.parquet").to_pylist() if point["case_id"] in by_case
    ]
    rows: list[dict[str, Any]] = []
    for case in cases:
        rows.append({**case, "point_kind": "find"})
    for point in points:
        case = by_case[point["case_id"]]
        rows.append({**point, "block_id": case["block_id"], "year": case["year"]})
    corners = [parse_square_id(cell_id=row["cell_id"]) for row in rows]
    east = np.array([corner[0] for corner in corners], dtype="int64")
    north = np.array([corner[1] for corner in corners], dtype="int64")
    latitudes = np.array([row["latitude"] for row in rows])
    longitudes = np.array([row["longitude"] for row in rows])
    forest, broadleaf, forest_sources = forest_features(east=east, north=north, tile_paths=forest_tiles)
    altitude, slope, dem_sources = terrain_features(
        east=east, north=north, latitudes=latitudes, longitudes=longitudes, dem_dir=dem_dir
    )
    weather, missing, weather_sources = weather_features(
        latitudes=latitudes, longitudes=longitudes, dates=[row["assessment_date"] for row in rows], weather_dir=weather_dir
    )
    columns: dict[str, Any] = {
        name: [row[name] for row in rows]
        for name in ("case_id", "set", "area", "block_id", "year", "assessment_date", "point_kind", "cell_id", "latitude", "longitude")
    }
    columns.update(forest_share=forest, broadleaf_share=broadleaf, altitude_m=altitude, slope_deg=slope, **weather)
    table = pa.table({name: columns[name] for name in OUTPUT_COLUMNS})
    return table, missing, forest_sources + dem_sources + weather_sources


# Temperature at the height of each square

# Air cools by about 6.5 degrees per 1,000 m, the standard rate of the International Standard Atmosphere.
COOLING_PER_METRE = 0.0065
GRAVITY = 9.80665
OROGRAPHY_URL = "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels"


def cell_heights(*, path: Path) -> tuple[np.ndarray, rasterio.Affine]:
    """Return the ERA5 ground height in metres of each 0.25 degree cell, and the grid position of the file.

    The file holds ERA5 geopotential, which is height times gravity.
    """
    with rasterio.open(path) as source:
        return source.read(1).astype(float) / GRAVITY, source.transform


def correct_temperatures(*, table: dict[str, np.ndarray], heights: np.ndarray, transform: rasterio.Affine) -> dict[str, np.ndarray]:
    """Return the table with the 7, 14 and 30 day temperatures moved from the height of the weather cell to the height of the square.

    ERA5 gives temperature at the mean ground height of a 25 km cell, so a square 1,000 m higher is about 6.5 degrees colder.
    """
    columns, rows = ~transform @ (table["longitude"].astype(float), table["latitude"].astype(float))
    columns = np.floor(columns).astype(int)
    rows = np.floor(rows).astype(int)
    inside = (rows >= 0) & (rows < heights.shape[0]) & (columns >= 0) & (columns < heights.shape[1])
    cell_height = np.full(len(rows), np.nan)
    cell_height[inside] = heights[rows[inside], columns[inside]]
    shift = COOLING_PER_METRE * (table["altitude_m"].astype(float) - cell_height)
    corrected = dict(table)
    for days in WINDOW_DAYS:
        corrected[f"temp_{days}d_c"] = table[f"temp_{days}d_c"].astype(float) - shift
    return corrected
