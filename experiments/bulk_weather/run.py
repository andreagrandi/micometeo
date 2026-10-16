"""Bulk weather: read the Italy weather from Open-Meteo files on AWS.

The script measures a first load and a night read, then compares 20 Tuscany cells with the API.
"""

import csv
import http.client
import json
import math
import random
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import omfiles

from sporameteo.context import RunContext
from sporameteo.weather import openmeteo

BUCKET_HOST = "openmeteo.s3.amazonaws.com"
BUCKET_URL = f"https://{BUCKET_HOST}/"
DOMAIN_PATH = "data/ecmwf_ifs"
DEM_PATH = "data/copernicus_dem90/static"
LATITUDE_LINES = 1280
CHUNK_HOURS = 504
ROME = ZoneInfo("Europe/Rome")
F = np.float32
DY = F(180) / (F(2 * LATITUDE_LINES) + F(0.5))
# The API adds 0.65 degrees for every 100 m that the grid point lies above the place.
LAPSE_RATE = F(0.0065)
HEIGHT_CORRECTED = {"temperature_2m", "dew_point_2m", "soil_temperature_0_to_7cm"}
SEA_HEIGHT = -999
MAX_FIRST_LOAD_BYTES = 1_000_000_000
API_VARIABLES = {
    "precipitation": "precipitation",
    "temperature_2m": "temperature_2m",
    "soil_moisture_0_to_7cm": "soil_moisture_0_to_7cm",
    "soil_temperature_0_to_7cm": "soil_temperature_0_to_7cm",
    "dew_point_2m": "dew_point_2m",
    "shortwave_radiation": "shortwave_radiation",
    "wind_speed_10m": "wind_speed_10m",
    "et0_fao_evapotranspiration": "et0_fao_evapotranspiration",
}
READ_COLUMNS = ["read", "files", "megabytes", "requests", "minutes", "points", "hours_needed"]
MATCH_COLUMNS = [
    "cell_key",
    "group",
    "place_height_m",
    "api_elevation_m",
    "nearest_point",
    "chosen_point",
    "chosen_height_m",
    "correction_c",
    "file_latitude",
    "file_longitude",
    "archive_latitude",
    "archive_longitude",
    "forecast_latitude",
    "forecast_longitude",
    "matches_archive",
    "matches_forecast",
]
DIFFERENCE_COLUMNS = [
    "api",
    "variable",
    "hours",
    "api_decimals",
    "median_abs_difference",
    "p95_abs_difference",
    "max_abs_difference",
    "share_within_rounding",
    "missing_in_files",
    "missing_in_api",
]
COVERAGE_COLUMNS = ["variable", "first_hour_utc", "last_hour_utc", "missing_cell_hours_in_window"]


class BucketReader:
    """Give omfiles byte ranges of one bucket file over HTTPS, with counts and a read-ahead cache."""

    def __init__(self, *, read_ahead_bytes: int) -> None:
        self.read_ahead_bytes = read_ahead_bytes
        self.requests = 0
        self.bytes = 0
        self.last_modified: dict[str, str] = {}
        self._sizes: dict[str, int] = {}
        self._segments: list[tuple[str, int, bytes]] = []
        self._connection: http.client.HTTPSConnection | None = None

    def _send(self, *, method: str, path: str, headers: dict[str, str]) -> http.client.HTTPResponse:
        for attempt in range(4):
            if self._connection is None:
                self._connection = http.client.HTTPSConnection(BUCKET_HOST, timeout=60)
            try:
                self._connection.request(method, "/" + path, headers=headers)
                response = self._connection.getresponse()
                body_needed = method == "GET"
                if response.status >= 500 and attempt < 3:
                    response.read()
                    time.sleep(2 * (attempt + 1))
                    continue
                if response.status not in (200, 206):
                    raise RuntimeError(f"{method} {path} answered {response.status}")
                if not body_needed:
                    response.read()
                return response
            except (OSError, http.client.HTTPException):
                self._connection.close()
                self._connection = None
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"{method} {path} failed")

    def size(self, path: str) -> int:
        if path not in self._sizes:
            response = self._send(method="HEAD", path=path, headers={})
            self.requests += 1
            self._sizes[path] = int(response.getheader("Content-Length"))
            self.last_modified[path] = response.getheader("Last-Modified") or ""
        return self._sizes[path]

    def cat_file(self, path: str, start: int | None = None, end: int | None = None, **kwargs: Any) -> bytes:
        start = 0 if start is None else start
        end = self.size(path) if end is None else end
        for segment_path, segment_start, data in self._segments:
            if segment_path == path and segment_start <= start and end <= segment_start + len(data):
                return data[start - segment_start : end - segment_start]
        fetch_end = min(self.size(path), max(end, start + self.read_ahead_bytes))
        response = self._send(method="GET", path=path, headers={"Range": f"bytes={start}-{fetch_end - 1}"})
        data = response.read()
        self.requests += 1
        self.bytes += len(data)
        self._segments = [*self._segments[-7:], (path, start, data)]
        return data[: end - start]


@dataclass
class ReadTotals:
    """What one read cost."""

    requests: int = 0
    bytes: int = 0
    files: set[str] = field(default_factory=set)
    last_modified: dict[str, str] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, *, reader: BucketReader) -> None:
        with self.lock:
            self.requests += reader.requests
            self.bytes += reader.bytes
            self.files.update(reader.last_modified)
            self.last_modified.update(reader.last_modified)


def open_file(*, reader: BucketReader, path: str) -> omfiles.OmFileReader:
    return omfiles.OmFileReader.from_fsspec(reader, path)


def swift_round(value: np.floating) -> int:
    """Round half away from zero, like Swift's round."""
    return int(math.copysign(math.floor(abs(float(value)) + 0.5), float(value)))


def row_width(*, y: int) -> int:
    return 20 + 4 * y if y < LATITUDE_LINES else (2 * LATITUDE_LINES - y - 1) * 4 + 20


def row_start(*, y: int) -> int:
    if y >= LATITUDE_LINES:
        raise ValueError("Only the northern half of the grid is supported.")
    return 2 * y * y + 18 * y


def point_row(*, point: int) -> int:
    y = int((math.sqrt(2 * point + 81) - 9) / 2)
    while row_start(y=y + 1) <= point:
        y += 1
    while row_start(y=y) > point:
        y -= 1
    return y


def point_coordinates(*, point: int) -> tuple[float, float]:
    """Return the latitude and longitude the API gives a grid point."""
    y = point_row(point=point)
    x = point - row_start(y=y)
    dx = F(360) / F(row_width(y=y))
    longitude = F(x) * dx
    latitude = F(LATITUDE_LINES - y - 1) * DY + DY / F(2)
    return float(latitude), float(longitude - F(360) if longitude >= F(180) else longitude)


def surrounding_points(*, latitude: float, longitude: float) -> tuple[list[int], list[np.float32], int]:
    """Return the 3 by 3 grid points around a place, their squared distances and the nearest one."""
    lat = F(latitude)
    lon = F(longitude)
    centre_y = max(1, min(2 * LATITUDE_LINES - 2, swift_round(F(LATITUDE_LINES) - F(1) - ((lat - DY / F(2)) / DY))))
    points: list[int] = []
    distances: list[np.float32] = []
    for j in range(3):
        y = centre_y + j - 1
        nx = row_width(y=y)
        dx = F(360) / F(nx)
        x_centre = swift_round(lon / dx)
        point_latitude = F(LATITUDE_LINES - y - 1) * DY + DY / F(2)
        start = max(0, 1 - x_centre)
        for i in range(3):
            x = x_centre + (i + start) % 3 - 1
            points.append(row_start(y=y) + (x + 2 * nx) % nx)
            distances.append((point_latitude - lat) ** 2 + (F(x) * dx - lon) ** 2)
    nearest = min(range(9), key=lambda index: (distances[index], index))
    return points, distances, nearest


@dataclass
class Match:
    """The grid point the API would use for one cell, and its height correction."""

    nearest_point: int
    point: int
    point_height: float
    place_height: float
    correction: float


def choose_point(*, latitude: float, longitude: float, place_height: float, heights: dict[int, float]) -> Match:
    """Copy the API's height-aware choice for cell_selection=land."""
    points, distances, nearest = surrounding_points(latitude=latitude, longitude=longitude)
    centre = points[nearest]
    centre_height = F(heights[centre])
    if math.isnan(place_height):
        return Match(nearest_point=centre, point=centre, point_height=float(centre_height), place_height=place_height, correction=0.0)
    place = F(place_height)
    if abs(centre_height - place) <= F(100):
        return Match(nearest_point=centre, point=centre, point_height=float(place), place_height=place_height, correction=0.0)
    best_delta = F(np.finfo(np.float32).max)
    best_point = -1
    best_height = F(np.nan)
    for point, distance in zip(points, distances, strict=True):
        height = F(heights[point])
        if np.isnan(height) or height <= F(SEA_HEIGHT):
            continue
        distance_km = np.sqrt(distance) * F(111)
        delta = abs(height - place) + distance_km * F(30)
        if delta < best_delta and distance_km < F(50):
            best_delta = delta
            best_point = point
            best_height = height
    if np.isnan(best_height) or best_delta > F(1500):
        best_point = centre
        best_height = centre_height
    correction = 0.0 if best_height <= F(SEA_HEIGHT) else float((best_height - place) * LAPSE_RATE)
    return Match(nearest_point=centre, point=best_point, point_height=float(best_height), place_height=place_height, correction=correction)


def point_runs(*, points: list[int], merge_gap: int) -> list[tuple[int, int]]:
    """Group sorted grid points into ranges that one read can cover."""
    runs: list[tuple[int, int]] = []
    for point in sorted(set(points)):
        if runs and point - runs[-1][1] <= merge_gap:
            runs[-1] = (runs[-1][0], point + 1)
        else:
            runs.append((point, point + 1))
    return runs


def read_points(*, path: str, runs: list[tuple[int, int]], read_ahead_bytes: int, totals: ReadTotals) -> dict[int, np.ndarray]:
    """Read every hour of the given grid point ranges from one file."""
    reader = BucketReader(read_ahead_bytes=read_ahead_bytes)
    om_file = open_file(reader=reader, path=path)
    values: dict[int, np.ndarray] = {}
    for first, last in runs:
        block = om_file.read_array((slice(0, 1), slice(first, last), slice(None)))
        block = block.reshape(last - first, -1)
        for offset in range(last - first):
            values[first + offset] = block[offset]
    totals.add(reader=reader)
    return values


def read_heights(*, points: list[int], merge_gap: int, read_ahead_bytes: int, totals: ReadTotals) -> dict[int, float]:
    """Read grid point heights from the static height file."""
    reader = BucketReader(read_ahead_bytes=read_ahead_bytes)
    om_file = open_file(reader=reader, path=f"{DOMAIN_PATH}/static/HSURF.om")
    heights: dict[int, float] = {}
    for first, last in point_runs(points=points, merge_gap=merge_gap):
        block = om_file.read_array((slice(0, 1), slice(first, last))).reshape(-1)
        for offset in range(last - first):
            heights[first + offset] = float(block[offset])
    totals.add(reader=reader)
    return heights


def dem_position(*, latitude: float, longitude: float) -> tuple[int, int, int]:
    """Return the elevation file, row and column the API reads for a place."""
    lat = F(latitude)
    lon = F(longitude)
    whole_degree = math.floor(float(lat))
    row = int(lat * F(1200) + F(90 * 1200)) % 1200
    if not -50 <= whole_degree < 50:
        raise ValueError("Only latitudes with 1200 columns per degree are supported.")
    column = int((lon + F(180)) * F(1200))
    return whole_degree, row, column


def read_place_heights(
    *, cells: list[tuple[float, float]], threads: int, read_ahead_bytes: int, totals: ReadTotals
) -> dict[tuple[float, float], float]:
    """Read each place's height from the Copernicus 90 m elevation files."""
    by_file: dict[int, list[tuple[tuple[float, float], int, int]]] = {}
    for cell in cells:
        whole_degree, row, column = dem_position(latitude=cell[0], longitude=cell[1])
        by_file.setdefault(whole_degree, []).append((cell, row, column))

    def read_one(whole_degree: int) -> dict[tuple[float, float], float]:
        reader = BucketReader(read_ahead_bytes=read_ahead_bytes)
        om_file = open_file(reader=reader, path=f"{DEM_PATH}/lat_{whole_degree}.om")
        result: dict[tuple[float, float], float] = {}
        for cell, row, column in sorted(by_file[whole_degree], key=lambda item: (item[1], item[2])):
            value = om_file.read_array((slice(row, row + 1), slice(column, column + 1)))
            result[cell] = float(np.asarray(value).reshape(-1)[0])
        totals.add(reader=reader)
        return result

    heights: dict[tuple[float, float], float] = {}
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for part in pool.map(read_one, sorted(by_file)):
            heights.update(part)
    return heights


def local_window_hours(*, first_day: date, last_day: date) -> tuple[int, int]:
    """Return the first hour and the hour after the last, counted from 1970 in UTC, for local Rome dates."""
    start = datetime.combine(first_day, datetime.min.time(), tzinfo=ROME).astimezone(UTC)
    end = datetime.combine(last_day + timedelta(days=1), datetime.min.time(), tzinfo=ROME).astimezone(UTC)
    return int(start.timestamp()) // 3600, int(end.timestamp()) // 3600


def hour_text(*, hour: int) -> str:
    return datetime.fromtimestamp(hour * 3600, tz=UTC).strftime("%Y-%m-%d %H:%M")


def read_weather(
    *,
    variables: list[str],
    points: list[int],
    first_hour: int,
    end_hour: int,
    settings: dict[str, Any],
) -> tuple[dict[str, dict[int, np.ndarray]], ReadTotals, float]:
    """Read all variables for the points and hours, and return values, costs and seconds."""
    chunks = range(first_hour // CHUNK_HOURS, (end_hour - 1) // CHUNK_HOURS + 1)
    runs = point_runs(points=points, merge_gap=settings["merge_gap_points"])
    totals = ReadTotals()
    tasks = [(variable, chunk) for variable in variables for chunk in chunks]

    def read_one(task: tuple[str, int]) -> tuple[str, int, dict[int, np.ndarray]]:
        variable, chunk = task
        path = f"{DOMAIN_PATH}/{variable}/chunk_{chunk}.om"
        values = read_points(path=path, runs=runs, read_ahead_bytes=settings["read_ahead_bytes"], totals=totals)
        return variable, chunk, values

    started = time.monotonic()
    by_chunk: dict[str, dict[int, dict[int, np.ndarray]]] = {variable: {} for variable in variables}
    with ThreadPoolExecutor(max_workers=settings["threads"]) as pool:
        for variable, chunk, values in pool.map(read_one, tasks):
            by_chunk[variable][chunk] = values
    seconds = time.monotonic() - started

    series: dict[str, dict[int, np.ndarray]] = {}
    for variable in variables:
        series[variable] = {
            point: np.concatenate([by_chunk[variable][chunk][point] for chunk in chunks]) for point in set(points)
        }
    return series, totals, seconds


def write_csv(*, rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def pick_comparison_cells(
    *, tuscany: list[tuple[float, float]], matches: dict[tuple[float, float], Match], count: int, seed: int
) -> list[tuple[tuple[float, float], str]]:
    """Pick the cells with the largest moves away from the nearest point, then random cells."""
    moved = sorted(
        (cell for cell in tuscany if matches[cell].point != matches[cell].nearest_point),
        key=lambda cell: (-abs(matches[cell].point_height - matches[cell].place_height), cell),
    )
    chosen = [(cell, "moved") for cell in moved[: count // 2]]
    rest = sorted(cell for cell in tuscany if cell not in {item[0] for item in chosen})
    random.Random(seed).shuffle(rest)
    chosen += [(cell, "random") for cell in rest[: count - len(chosen)]]
    return chosen


def fetch_api(
    *, url: str, query: dict[str, Any], cache_path: Path, days: int, places: int, pause_seconds: float, metrics: dict[str, float]
) -> list[dict[str, Any]]:
    """Ask the API once for all places, or read the saved answer."""
    if cache_path.exists():
        metrics["cache_hits"] += 1
        answer = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        metrics["requests"] += 1
        metrics["counted_calls"] += places * openmeteo.quota_weight(variables=len(API_VARIABLES), days=days)
        answer = openmeteo.get_json(url=url + "?" + urllib.parse.urlencode(query))
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(answer), encoding="utf-8")
        time.sleep(pause_seconds)
    return answer if isinstance(answer, list) else [answer]


def api_query(*, cells: list[tuple[float, float]], first_day: date, last_day: date) -> dict[str, Any]:
    return {
        "latitude": ",".join(f"{cell[0]:.2f}" for cell in cells),
        "longitude": ",".join(f"{cell[1]:.2f}" for cell in cells),
        "hourly": ",".join(API_VARIABLES),
        "models": "ecmwf_ifs",
        "cell_selection": "land",
        "start_date": first_day.isoformat(),
        "end_date": last_day.isoformat(),
        "timezone": "Europe/Rome",
        "timeformat": "unixtime",
        "wind_speed_unit": "ms",
    }


def file_value(*, series: dict[str, dict[int, np.ndarray]], variable: str, match: Match, index: int) -> float:
    """Return the value a file reader would give for one API variable and hour."""
    if variable == "wind_speed_10m":
        u = series["wind_u_component_10m"][match.point][index]
        v = series["wind_v_component_10m"][match.point][index]
        return float(np.sqrt(u * u + v * v))
    value = float(series[variable][match.point][index])
    if variable in HEIGHT_CORRECTED:
        value += match.correction
    return value


def decimals_of(*, values: list[float]) -> int:
    longest = 0
    for value in values:
        text = repr(value)
        if "." in text and "e" not in text:
            longest = max(longest, len(text.split(".")[1].rstrip("0")))
    return longest


def compare(
    *,
    api_name: str,
    answers: list[dict[str, Any]],
    cells: list[tuple[float, float]],
    matches: dict[tuple[float, float], Match],
    series: dict[str, dict[int, np.ndarray]],
    first_hour: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return per-variable difference rows and the hourly pairs behind them."""
    rows: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    for variable in API_VARIABLES:
        if variable == "et0_fao_evapotranspiration":
            continue
        api_values: list[float] = []
        differences: list[float] = []
        missing_in_files = 0
        missing_in_api = 0
        for cell, answer in zip(cells, answers, strict=True):
            hourly = answer["hourly"]
            for timestamp, api_value in zip(hourly["time"], hourly[variable], strict=True):
                index = timestamp // 3600 - first_hour
                value = file_value(series=series, variable=variable, match=matches[cell], index=index)
                if api_value is None:
                    missing_in_api += 1
                    continue
                if math.isnan(value):
                    missing_in_files += 1
                    continue
                api_values.append(api_value)
                differences.append(value - api_value)
                pairs.append(
                    {
                        "api": api_name,
                        "variable": variable,
                        "cell": f"{cell[0]:.2f},{cell[1]:.2f}",
                        "hour_utc": hour_text(hour=timestamp // 3600),
                        "file": round(value, 4),
                        "api_value": api_value,
                    }
                )
        absolute = np.abs(np.array(differences)) if differences else np.array([np.nan])
        decimals = decimals_of(values=api_values)
        tolerance = 0.5 * 10 ** (-decimals) + 1e-6
        rows.append(
            {
                "api": api_name,
                "variable": variable,
                "hours": len(differences),
                "api_decimals": decimals,
                "median_abs_difference": round(float(np.median(absolute)), 4),
                "p95_abs_difference": round(float(np.percentile(absolute, 95)), 4),
                "max_abs_difference": round(float(np.max(absolute)), 4),
                "share_within_rounding": round(float(np.mean(absolute <= tolerance)), 4),
                "missing_in_files": missing_in_files,
                "missing_in_api": missing_in_api,
            }
        )
    return rows, pairs


def coverage_rows(
    *, series: dict[str, dict[int, np.ndarray]], first_chunk_hour: int, window_start: int, window_end: int
) -> list[dict[str, Any]]:
    """Return the first and last hour with a value in the files read, and the gaps in the window."""
    rows = []
    for variable, by_point in series.items():
        stack = np.stack(list(by_point.values()))
        has_value = ~np.isnan(stack).all(axis=0)
        filled = np.flatnonzero(has_value)
        window = stack[:, window_start - first_chunk_hour : window_end - first_chunk_hour]
        rows.append(
            {
                "variable": variable,
                "first_hour_utc": hour_text(hour=first_chunk_hour + int(filled[0])) if filled.size else "",
                "last_hour_utc": hour_text(hour=first_chunk_hour + int(filled[-1])) if filled.size else "",
                "missing_cell_hours_in_window": int(np.isnan(window).sum()),
            }
        )
    return rows


def read_row(*, name: str, totals: ReadTotals, seconds: float, points: int, hours: int) -> dict[str, Any]:
    return {
        "read": name,
        "files": len(totals.files),
        "megabytes": round(totals.bytes / 1_000_000, 2),
        "requests": totals.requests,
        "minutes": round(seconds / 60, 2),
        "points": points,
        "hours_needed": hours,
    }


def run(context: RunContext) -> None:
    """Match cells to grid points, read the files twice, compare with the API and write the results."""
    settings = context.config
    root = Path(__file__).resolve().parent.parent.parent
    reports_dir = root / "reports"
    assessment_date = date.fromisoformat(settings["assessment_date"])
    variables = list(settings["variables"])

    cells_path = root / settings["cells_path"]
    stored_path = root / settings["stored_points_path"]
    context.add_input(cells_path)
    context.add_input(stored_path)
    cell_lists = json.loads(cells_path.read_text(encoding="utf-8"))
    italy = [tuple(cell) for cell in cell_lists["italy"]]
    tuscany = [tuple(cell) for cell in cell_lists["tuscany"]]
    stored = json.loads(stored_path.read_text(encoding="utf-8"))

    meta_reader = BucketReader(read_ahead_bytes=0)
    meta_path = f"{DOMAIN_PATH}/static/meta.json"
    meta = json.loads(meta_reader.cat_file(meta_path))
    downloaded_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    context.add_source(
        name="Open-Meteo open data on AWS, ecmwf_ifs",
        url=BUCKET_URL + DOMAIN_PATH,
        licence="CC BY 4.0",
        version=f"meta.json last_run_initialisation_time {meta['last_run_initialisation_time']}",
        downloaded_at=downloaded_at,
        query={"variables": variables, "assessment_date": settings["assessment_date"]},
    )

    # Static reads: place heights and grid point heights. Both files never change.
    static_totals = ReadTotals()
    static_started = time.monotonic()
    place_heights = read_place_heights(
        cells=italy, threads=settings["threads"], read_ahead_bytes=settings["read_ahead_bytes"], totals=static_totals
    )
    neighbours = [
        point
        for cell in italy
        for point in surrounding_points(latitude=cell[0], longitude=cell[1])[0]
    ]
    grid_heights = read_heights(
        points=neighbours,
        merge_gap=settings["merge_gap_points"],
        read_ahead_bytes=settings["read_ahead_bytes"],
        totals=static_totals,
    )
    static_seconds = time.monotonic() - static_started
    matches = {
        cell: choose_point(latitude=cell[0], longitude=cell[1], place_height=place_heights[cell], heights=grid_heights)
        for cell in italy
    }
    points = sorted({match.point for match in matches.values()})

    # First load: 30 past days, today and 7 days ahead.
    first_day = assessment_date - timedelta(days=settings["past_days"])
    last_day = assessment_date + timedelta(days=settings["days_ahead"])
    window_start, window_end = local_window_hours(first_day=first_day, last_day=last_day)
    series, first_totals, first_seconds = read_weather(
        variables=variables, points=points, first_hour=window_start, end_hour=window_end, settings=settings
    )
    first_chunk_hour = (window_start // CHUNK_HOURS) * CHUNK_HOURS
    if first_totals.bytes > MAX_FIRST_LOAD_BYTES:
        raise RuntimeError(f"The Italy first load downloaded {first_totals.bytes} bytes, over the 1 GB stop rule.")

    # One night: the newest completed day, today and 7 days ahead.
    night_start, night_end = local_window_hours(first_day=assessment_date - timedelta(days=1), last_day=last_day)
    _, night_totals, night_seconds = read_weather(
        variables=variables, points=points, first_hour=night_start, end_hour=night_end, settings=settings
    )

    reads = [
        read_row(name="static heights, once", totals=static_totals, seconds=static_seconds, points=len(grid_heights), hours=0),
        read_row(name="first load, 38 days", totals=first_totals, seconds=first_seconds, points=len(points), hours=window_end - window_start),
        read_row(name="one night, 9 days", totals=night_totals, seconds=night_seconds, points=len(points), hours=night_end - night_start),
    ]
    reads_path = reports_dir / "bulk_weather_reads.csv"
    write_csv(rows=reads, columns=READ_COLUMNS, path=reads_path)
    context.add_output(reads_path)

    coverage = coverage_rows(
        series=series, first_chunk_hour=first_chunk_hour, window_start=window_start, window_end=window_end
    )
    coverage_path = reports_dir / "bulk_weather_coverage.csv"
    write_csv(rows=coverage, columns=COVERAGE_COLUMNS, path=coverage_path)
    context.add_output(coverage_path)

    # The grid match for every Tuscany cell with a stored archive answer.
    stored_checked = 0
    stored_matching = 0
    stored_height_matching = 0
    stored_mismatches: list[dict[str, Any]] = []
    for row in stored:
        cell = (round(row["requested_latitude"], 2), round(row["requested_longitude"], 2))
        if cell not in matches:
            continue
        stored_checked += 1
        latitude, longitude = point_coordinates(point=matches[cell].point)
        if abs(latitude - row["returned_latitude"]) < 1e-4 and abs(longitude - row["returned_longitude"]) < 1e-4:
            stored_matching += 1
        else:
            stored_mismatches.append({"cell": row["cell_key"], "file": [latitude, longitude], "api": [row["returned_latitude"], row["returned_longitude"]]})
        if row["reference_elevation_m"] is not None and abs(place_heights[cell] - row["reference_elevation_m"]) < 0.5:
            stored_height_matching += 1

    # The API comparison for 20 Tuscany cells.
    comparison = pick_comparison_cells(tuscany=tuscany, matches=matches, count=settings["comparison_cells"], seed=context.seed)
    compared_cells = [cell for cell, _ in comparison]
    api_dir = context.raw_dir / "api" / settings["assessment_date"]
    api_metrics = {"requests": 0, "cache_hits": 0, "counted_calls": 0.0}
    archive_last = assessment_date - timedelta(days=1)
    archive_answers = fetch_api(
        url=openmeteo.ARCHIVE_URL,
        query=api_query(cells=compared_cells, first_day=first_day, last_day=archive_last),
        cache_path=api_dir / "archive_ecmwf_ifs.json",
        days=settings["past_days"],
        places=len(compared_cells),
        pause_seconds=settings["pause_seconds"],
        metrics=api_metrics,
    )
    forecast_answers = fetch_api(
        url=openmeteo.FORECAST_URL,
        query=api_query(cells=compared_cells, first_day=assessment_date, last_day=last_day),
        cache_path=api_dir / "forecast_ecmwf_ifs.json",
        days=settings["days_ahead"] + 1,
        places=len(compared_cells),
        pause_seconds=settings["pause_seconds"],
        metrics=api_metrics,
    )
    context.add_source(
        name="Open-Meteo archive and forecast APIs, models=ecmwf_ifs",
        url=openmeteo.ARCHIVE_URL + " " + openmeteo.FORECAST_URL,
        licence=openmeteo.LICENCE,
        version="v1",
        downloaded_at=downloaded_at,
        query={"cells": [f"{cell[0]:.2f},{cell[1]:.2f}" for cell in compared_cells]},
    )

    match_rows = []
    for (cell, group), archive, forecast in zip(comparison, archive_answers, forecast_answers, strict=True):
        match = matches[cell]
        latitude, longitude = point_coordinates(point=match.point)
        match_rows.append(
            {
                "cell_key": f"{cell[0]:.2f},{cell[1]:.2f}",
                "group": group,
                "place_height_m": round(match.place_height, 1),
                "api_elevation_m": archive.get("elevation"),
                "nearest_point": match.nearest_point,
                "chosen_point": match.point,
                "chosen_height_m": round(match.point_height, 1),
                "correction_c": round(match.correction, 3),
                "file_latitude": round(latitude, 5),
                "file_longitude": round(longitude, 5),
                "archive_latitude": archive["latitude"],
                "archive_longitude": archive["longitude"],
                "forecast_latitude": forecast["latitude"],
                "forecast_longitude": forecast["longitude"],
                "matches_archive": abs(latitude - archive["latitude"]) < 1e-4 and abs(longitude - archive["longitude"]) < 1e-4,
                "matches_forecast": abs(latitude - forecast["latitude"]) < 1e-4 and abs(longitude - forecast["longitude"]) < 1e-4,
            }
        )
    match_path = reports_dir / "bulk_weather_grid_match.csv"
    write_csv(rows=match_rows, columns=MATCH_COLUMNS, path=match_path)
    context.add_output(match_path)

    archive_rows, archive_pairs = compare(
        api_name="archive", answers=archive_answers, cells=compared_cells, matches=matches, series=series, first_hour=first_chunk_hour
    )
    forecast_rows, forecast_pairs = compare(
        api_name="forecast", answers=forecast_answers, cells=compared_cells, matches=matches, series=series, first_hour=first_chunk_hour
    )
    differences_path = reports_dir / "bulk_weather_differences.csv"
    write_csv(rows=archive_rows + forecast_rows, columns=DIFFERENCE_COLUMNS, path=differences_path)
    context.add_output(differences_path)
    pairs_path = context.output_dir / "hourly_pairs.csv"
    write_csv(
        rows=archive_pairs + forecast_pairs,
        columns=["api", "variable", "cell", "hour_utc", "file", "api_value"],
        path=pairs_path,
    )
    context.add_output(pairs_path)

    summary = {
        "meta": meta,
        "meta_times_utc": {
            key: datetime.fromtimestamp(meta[key], tz=UTC).isoformat()
            for key in ("data_end_time", "last_run_initialisation_time", "last_run_availability_time")
        },
        "window_utc": [hour_text(hour=window_start), hour_text(hour=window_end - 1)],
        "night_window_utc": [hour_text(hour=night_start), hour_text(hour=night_end - 1)],
        "italy_cells": len(italy),
        "tuscany_cells": len(tuscany),
        "grid_points_read": len(points),
        "cells_moved_from_nearest": sum(1 for match in matches.values() if match.point != match.nearest_point),
        "cells_with_correction": sum(1 for match in matches.values() if match.correction != 0.0),
        "cells_without_place_height": sum(1 for match in matches.values() if math.isnan(match.place_height)),
        "stored_archive_checked": stored_checked,
        "stored_archive_matching_point": stored_matching,
        "stored_archive_matching_height": stored_height_matching,
        "stored_archive_mismatches": stored_mismatches[:20],
        "api": api_metrics,
        "file_last_modified": first_totals.last_modified,
    }
    summary_path = context.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    context.add_output(summary_path)
