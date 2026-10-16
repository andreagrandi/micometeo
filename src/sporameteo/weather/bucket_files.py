"""Read weather from the Open-Meteo files in the public bucket, without the API.

The grid and height-matching code is copied from experiments/bulk_weather/run.py and matches the API exactly.
"""

import http.client
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import numpy as np
import omfiles

from sporameteo.weather.evapotranspiration import evapotranspiration_series, top_of_atmosphere_series

BUCKET_HOST = "openmeteo.s3.amazonaws.com"
DOMAIN_PATH = "data/ecmwf_ifs"
DEM_PATH = "data/copernicus_dem90/static"
LATITUDE_LINES = 1280
CHUNK_HOURS = 504
ROME = ZoneInfo("Europe/Rome")
F = np.float32
DY = F(180) / (F(2 * LATITUDE_LINES) + F(0.5))
LAPSE_RATE = F(0.0065)
SEA_HEIGHT = -999
MERGE_GAP_POINTS = 12
READ_AHEAD_BYTES = 32_768
READ_THREADS = 8
READ_VARIABLES = (
    "precipitation",
    "temperature_2m",
    "soil_moisture_0_to_7cm",
    "soil_temperature_0_to_7cm",
    "dew_point_2m",
    "shortwave_radiation",
    "wind_u_component_10m",
    "wind_v_component_10m",
)
HEIGHT_CORRECTED = {"temperature_2m", "dew_point_2m", "soil_temperature_0_to_7cm"}
BYTES_PER_CELL_PER_CHUNK_FILE = 3_540
"""Measured on 16 October 2026: 28.3 MB for 333 Tuscany cells over 24 chunk files."""


class OmReader(Protocol):
    """The part of an open .om file that this module uses."""

    def read_array(self, ranges: tuple[slice, ...]) -> np.ndarray: ...


class WeatherFileSource(Protocol):
    """Where the files come from. The bucket in production, a local folder in tests."""

    def open_om(self, *, path: str) -> OmReader: ...

    def read_json(self, *, path: str) -> dict[str, Any]: ...

    def modified(self, *, path: str) -> datetime: ...

    def bytes_read(self) -> int: ...

    def request_count(self) -> int: ...


class BucketFile:
    """Give omfiles byte ranges of one bucket file over HTTPS, with counts and a read-ahead cache."""

    def __init__(self, *, read_ahead_bytes: int = READ_AHEAD_BYTES) -> None:
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
                if response.status >= 500 and attempt < 3:
                    response.read()
                    time.sleep(2 * (attempt + 1))
                    continue
                if response.status not in (200, 206):
                    raise RuntimeError(f"{method} {path} answered {response.status}")
                if method != "GET":
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


class BucketSource:
    """Read files from the public bucket over HTTPS and count the bytes and requests."""

    def __init__(self, *, read_ahead_bytes: int = READ_AHEAD_BYTES) -> None:
        self.read_ahead_bytes = read_ahead_bytes
        self._files: list[BucketFile] = []

    def open_om(self, *, path: str) -> OmReader:
        bucket_file = BucketFile(read_ahead_bytes=self.read_ahead_bytes)
        self._files.append(bucket_file)
        return omfiles.OmFileReader.from_fsspec(bucket_file, path)

    def read_json(self, *, path: str) -> dict[str, Any]:
        bucket_file = BucketFile(read_ahead_bytes=self.read_ahead_bytes)
        self._files.append(bucket_file)
        return json.loads(bucket_file.cat_file(path))

    def modified(self, *, path: str) -> datetime:
        """Return the Last-Modified time that the bucket gave for a file read so far."""
        for bucket_file in self._files:
            text = bucket_file.last_modified.get(path)
            if text:
                return parsedate_to_datetime(text).astimezone(UTC)
        raise KeyError(path)

    def bytes_read(self) -> int:
        return sum(bucket_file.bytes for bucket_file in self._files)

    def request_count(self) -> int:
        return sum(bucket_file.requests for bucket_file in self._files)


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


def read_place_heights(*, source: WeatherFileSource, cells: dict[str, tuple[float, float]]) -> dict[str, float]:
    """Read each place's height from the Copernicus 90 m elevation files."""
    by_file: dict[int, list[tuple[str, int, int]]] = {}
    for key, (latitude, longitude) in cells.items():
        whole_degree, row, column = dem_position(latitude=latitude, longitude=longitude)
        by_file.setdefault(whole_degree, []).append((key, row, column))
    heights: dict[str, float] = {}
    for whole_degree in sorted(by_file):
        om_file = source.open_om(path=f"{DEM_PATH}/lat_{whole_degree}.om")
        for key, row, column in sorted(by_file[whole_degree], key=lambda item: (item[1], item[2])):
            value = om_file.read_array((slice(row, row + 1), slice(column, column + 1)))
            heights[key] = float(np.asarray(value).reshape(-1)[0])
    return heights


def read_grid_heights(*, source: WeatherFileSource, points: list[int]) -> dict[int, float]:
    """Read grid point heights from the static height file."""
    om_file = source.open_om(path=f"{DOMAIN_PATH}/static/HSURF.om")
    heights: dict[int, float] = {}
    for first, last in point_runs(points=points, merge_gap=MERGE_GAP_POINTS):
        block = om_file.read_array((slice(0, 1), slice(first, last))).reshape(-1)
        for offset in range(last - first):
            heights[first + offset] = float(block[offset])
    return heights


def match_cells(*, source: WeatherFileSource, cells: dict[str, tuple[float, float]]) -> dict[str, Match]:
    """Return the grid point and height correction for each cell, keyed by cell key.

    The cells map a key to a latitude and longitude.
    """
    place_heights = read_place_heights(source=source, cells=cells)
    surrounding = [point for latitude, longitude in cells.values() for point in surrounding_points(latitude=latitude, longitude=longitude)[0]]
    grid_heights = read_grid_heights(source=source, points=surrounding)
    return {
        key: choose_point(latitude=latitude, longitude=longitude, place_height=place_heights[key], heights=grid_heights)
        for key, (latitude, longitude) in cells.items()
    }


def read_newest_run(*, source: WeatherFileSource) -> datetime:
    """Return the start time of the newest forecast run held in the files."""
    meta = source.read_json(path=f"{DOMAIN_PATH}/static/meta.json")
    return datetime.fromtimestamp(int(meta["last_run_initialisation_time"]), tz=UTC)


def local_window_hours(*, first_day: date, last_day: date) -> tuple[int, int]:
    """Return the first hour and the hour after the last, counted from 1970 in UTC, for local Rome dates."""
    start = datetime.combine(first_day, datetime.min.time(), tzinfo=ROME).astimezone(UTC)
    end = datetime.combine(last_day + timedelta(days=1), datetime.min.time(), tzinfo=ROME).astimezone(UTC)
    return int(start.timestamp()) // 3600, int(end.timestamp()) // 3600


def chunk_path(*, variable: str, chunk: int) -> str:
    return f"{DOMAIN_PATH}/{variable}/chunk_{chunk}.om"


def chunk_paths(*, first_hour: int, last_hour: int) -> list[str]:
    """Return the chunk files that hold the hours from first_hour to last_hour, counted from 1970 in UTC."""
    chunks = range(first_hour // CHUNK_HOURS, last_hour // CHUNK_HOURS + 1)
    return [chunk_path(variable=variable, chunk=chunk) for variable in READ_VARIABLES for chunk in chunks]


@dataclass
class CellHours:
    """Hourly values of one cell. A missing hour is None. Times are seconds since 1970 in UTC."""

    timestamps: tuple[int, ...]
    precipitation: tuple[float | None, ...]
    temperature: tuple[float | None, ...]
    soil_moisture: tuple[float | None, ...]
    soil_temperature: tuple[float | None, ...]
    et0: tuple[float | None, ...]


@dataclass
class HoursRead:
    """The hours of every cell, and the modification time of each chunk file that was read."""

    cells: dict[str, CellHours]
    file_modified: dict[str, datetime]


def _read_chunk(*, source: WeatherFileSource, path: str, runs: list[tuple[int, int]]) -> dict[int, np.ndarray]:
    om_file = source.open_om(path=path)
    values: dict[int, np.ndarray] = {}
    for first, last in runs:
        block = om_file.read_array((slice(0, 1), slice(first, last), slice(None))).reshape(last - first, -1)
        for offset in range(last - first):
            values[first + offset] = block[offset]
    return values


def _clean(values: np.ndarray) -> tuple[float | None, ...]:
    return tuple(None if math.isnan(value) else float(value) for value in values)


def read_cell_hours(
    *, source: WeatherFileSource, matches: dict[str, Match], first_day: date, last_day: date, threads: int = READ_THREADS
) -> HoursRead:
    """Read the hours of the Rome days first_day to last_day for every matched cell.

    The values include the closing midnight hour, because rain and evapotranspiration of the last day end at that hour.
    Evapotranspiration is missing for an hour when any of its inputs is missing.
    """
    first_hour, end_hour = local_window_hours(first_day=first_day, last_day=last_day)
    count = end_hour - first_hour + 1
    chunks = range(first_hour // CHUNK_HOURS, end_hour // CHUNK_HOURS + 1)
    runs = point_runs(points=[match.point for match in matches.values()], merge_gap=MERGE_GAP_POINTS)
    tasks = [(variable, chunk) for variable in READ_VARIABLES for chunk in chunks]

    def read_one(task: tuple[str, int]) -> dict[int, np.ndarray]:
        return _read_chunk(source=source, path=chunk_path(variable=task[0], chunk=task[1]), runs=runs)

    with ThreadPoolExecutor(max_workers=threads) as pool:
        results = list(pool.map(read_one, tasks))
    by_chunk = {task: values for task, values in zip(tasks, results, strict=True)}
    file_modified = {path: source.modified(path=path) for path in (chunk_path(variable=v, chunk=c) for v, c in tasks)}

    offset = first_hour - chunks[0] * CHUNK_HOURS
    timestamps = tuple((first_hour + index) * 3600 for index in range(count))
    cells: dict[str, CellHours] = {}
    toa_cache: dict[tuple[float, float], np.ndarray] = {}
    for key, match in matches.items():
        series: dict[str, np.ndarray] = {}
        for variable in READ_VARIABLES:
            joined = np.concatenate([by_chunk[(variable, chunk)][match.point] for chunk in chunks]).astype(np.float64)
            window = joined[offset : offset + count]
            if len(window) < count:
                window = np.concatenate([window, np.full(count - len(window), np.nan)])
            if variable in HEIGHT_CORRECTED:
                window = window + match.correction
            series[variable] = window
        arrays = {
            "temperature": series["temperature_2m"].reshape(1, -1),
            "dew_point": series["dew_point_2m"].reshape(1, -1),
            "shortwave_radiation": series["shortwave_radiation"].reshape(1, -1),
            "wind_speed": np.hypot(series["wind_u_component_10m"], series["wind_v_component_10m"]).reshape(1, -1),
        }
        position = point_coordinates(point=match.point)
        if position not in toa_cache:
            toa_cache[position] = top_of_atmosphere_series(latitude=position[0], longitude=position[1], first_hour=first_hour, count=count)
        elevation = match.place_height if not math.isnan(match.place_height) else match.point_height
        et0 = evapotranspiration_series(arrays=arrays, row=0, elevation=elevation, toa=toa_cache[position], hours=range(count))
        cells[key] = CellHours(
            timestamps=timestamps,
            precipitation=_clean(series["precipitation"]),
            temperature=_clean(series["temperature_2m"]),
            soil_moisture=_clean(series["soil_moisture_0_to_7cm"]),
            soil_temperature=_clean(series["soil_temperature_0_to_7cm"]),
            et0=_clean(et0),
        )
    return HoursRead(cells=cells, file_modified=file_modified)


def estimate_read_bytes(*, cell_count: int, first_day: date, last_day: date) -> int:
    """Return the expected download size of one read of the chunk files, without any network call.

    The size of the height files is not included.
    """
    first_hour, end_hour = local_window_hours(first_day=first_day, last_day=last_day)
    chunk_files = len(READ_VARIABLES) * (end_hour // CHUNK_HOURS - first_hour // CHUNK_HOURS + 1)
    return cell_count * chunk_files * BYTES_PER_CELL_PER_CHUNK_FILE
