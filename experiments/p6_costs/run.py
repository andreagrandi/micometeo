"""P6a: measure the daily work and the stored data for the home area, and estimate requests per user.

Counts squares, weather cells and map images over the home area, times the scoring of one day and writes the sizes.
"""

import csv
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.ops import transform, unary_union

from sporameteo.context import RunContext
from sporameteo.finds.roads import GADM_URL, load_gadm
from sporameteo.habitat.grid import now_utc

ROOT = Path(__file__).resolve().parents[2]
SIZE_COLUMNS = ["item", "value", "unit", "kind", "source"]
USER_COLUMNS = [
    "active_users",
    "sessions_per_day",
    "api_requests_per_day",
    "api_mb_per_day",
    "page_mb_per_day",
    "api_requests_per_month",
    "transfer_gb_per_month",
    "kind",
]
_TO_LAEA = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)


def home_area(*, settings: dict[str, Any], raw_dir: Path) -> Any:
    """Return the home area outline in longitude and latitude, decision D4."""
    regions = {
        feature["properties"]["GID_1"]: shape(feature["geometry"])
        for feature in load_gadm(name="ITA_1", raw_dir=raw_dir)
    }
    emilia = settings["emilia_apennines"]
    emilia_box = box(emilia["west"], emilia["south"], emilia["east"], emilia["north"])
    return unary_union(
        [regions[settings["tuscany_gid"]], regions[emilia["gid"]].intersection(emilia_box)]
    )


def square_centres(*, area_laea: Any, size_m: int) -> tuple[np.ndarray, np.ndarray]:
    """Return the corners of the grid squares whose centre lies inside the area."""
    west, south, east, north = area_laea.bounds
    eastings = np.arange(math.floor(west / size_m) * size_m, east, size_m)
    northings = np.arange(math.floor(south / size_m) * size_m, north, size_m)
    grid_e, grid_n = np.meshgrid(eastings, northings)
    corner_e, corner_n = grid_e.ravel(), grid_n.ravel()
    shapely.prepare(area_laea)
    inside = shapely.contains_xy(area_laea, corner_e + size_m / 2, corner_n + size_m / 2)
    return corner_e[inside].astype(np.int64), corner_n[inside].astype(np.int64)


def weather_cells(*, area: Any, cell_degrees: float) -> int:
    """Count weather cells of a regular latitude and longitude grid that touch the area."""
    west, south, east, north = area.bounds
    count = 0
    shapely.prepare(area)
    for i in range(math.floor(west / cell_degrees), math.ceil(east / cell_degrees)):
        for j in range(math.floor(south / cell_degrees), math.ceil(north / cell_degrees)):
            cell = box(
                i * cell_degrees, j * cell_degrees, (i + 1) * cell_degrees, (j + 1) * cell_degrees
            )
            if area.intersects(cell):
                count += 1
    return count


def tile_count(*, area: Any, zoom: int) -> int:
    """Count the 512 pixel map images at one zoom level that touch the area."""
    scale = 2**zoom

    def tile_x(longitude: float) -> int:
        return int((longitude + 180) / 360 * scale)

    def tile_y(latitude: float) -> int:
        sin_lat = math.sin(math.radians(latitude))
        return int((0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale)

    def lon_of(x: int) -> float:
        return x / scale * 360 - 180

    def lat_of(y: int) -> float:
        return math.degrees(math.atan(math.sinh(math.pi - 2 * math.pi * y / scale)))

    west, south, east, north = area.bounds
    shapely.prepare(area)
    count = 0
    for x in range(tile_x(west), tile_x(east) + 1):
        for y in range(tile_y(north), tile_y(south) + 1):
            if area.intersects(box(lon_of(x), lat_of(y + 1), lon_of(x + 1), lat_of(y))):
                count += 1
    return count


def score_one_day(
    *, square_count: int, days_ahead: int, rng: np.random.Generator
) -> dict[str, np.ndarray]:
    """Apply the published weather rules of decision D8 to made-up weather for every square."""
    shape_ = (square_count, days_ahead)
    rain_30_to_8 = rng.gamma(shape=2.0, scale=25.0, size=shape_)
    cooling = rng.normal(loc=0.5, scale=1.5, size=shape_)
    mean_14 = rng.normal(loc=13.0, scale=4.0, size=shape_)
    altitude = rng.uniform(low=0.0, high=2000.0, size=(square_count, 1))
    points = (
        (rain_30_to_8 >= 30).astype(np.int8)
        + (cooling >= 1).astype(np.int8)
        + ((mean_14 >= 10) & (mean_14 <= 15)).astype(np.int8)
        + ((altitude >= 200) & (altitude <= 2000)).astype(np.int8)
    )
    score = (points * 25).astype(np.int8)
    reliability = np.broadcast_to(
        np.array([2, 2, 2, 1, 1, 1, 0, 0][:days_ahead], dtype=np.int8), shape_
    )
    return {"score": score, "reliability": reliability}


def write_day(
    *, corner_e: np.ndarray, corner_n: np.ndarray, scores: dict[str, np.ndarray], path: Path
) -> int:
    """Write one day of scores as a compressed Parquet file and return its size in bytes."""
    square_count, days_ahead = scores["score"].shape
    table = pa.table(
        {
            "easting": pa.array(np.repeat(corner_e, days_ahead).astype(np.int32)),
            "northing": pa.array(np.repeat(corner_n, days_ahead).astype(np.int32)),
            "days_ahead": pa.array(np.tile(np.arange(days_ahead, dtype=np.int8), square_count)),
            "score": pa.array(scores["score"].ravel()),
            "reliability": pa.array(np.ascontiguousarray(scores["reliability"]).ravel()),
        }
    )
    pq.write_table(table, path, compression="zstd")
    return path.stat().st_size


def user_rows(*, users: dict[str, Any], days_per_month: int = 30) -> list[dict[str, Any]]:
    """Estimate requests and transfer for each number of active users."""
    rows = []
    per_session = users["square_requests_per_session"] + users["other_requests_per_session"]
    for active in users["active_users"]:
        sessions = active * users["sessions_per_user_per_day"]
        requests = sessions * per_session
        api_mb = sessions * users["square_requests_per_session"] * users["square_request_kb"] / 1024
        page_mb = sessions * users["cold_load_share"] * users["page_kb"] / 1024
        rows.append(
            {
                "active_users": active,
                "sessions_per_day": sessions,
                "api_requests_per_day": requests,
                "api_mb_per_day": round(api_mb, 1),
                "page_mb_per_day": round(page_mb, 1),
                "api_requests_per_month": requests * days_per_month,
                "transfer_gb_per_month": round((api_mb + page_mb) * days_per_month / 1024, 2),
                "kind": "estimated",
            }
        )
    return rows


def write_csv(*, rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def run(context: RunContext) -> None:
    """Measure the home area, the daily scoring and the stored data, then estimate user traffic."""
    settings = context.config
    rng = np.random.default_rng(context.seed)
    area = home_area(settings=settings, raw_dir=context.raw_dir)
    context.add_source(
        name="GADM 4.1 area outlines",
        url=GADM_URL.format(name="ITA_1"),
        licence="GADM licence, free for non-commercial use",
        version="4.1",
        downloaded_at=now_utc(),
        query={"files": ["ITA_1"], "home": [settings["tuscany_gid"], settings["emilia_apennines"]]},
    )
    area_laea = transform(_TO_LAEA.transform, area)
    size_m = settings["square_size_m"]
    corner_e, corner_n = square_centres(area_laea=area_laea, size_m=size_m)
    square_count = len(corner_e)

    weather = settings["weather"]
    days_ahead = weather["days_ahead"]
    sizes: list[dict[str, Any]] = [
        {"item": "home area", "value": round(area_laea.area / 1e6), "unit": "km2", "kind": "measured", "source": "GADM 4.1 outline, decision D4"},
        {"item": "500 m squares in the home area", "value": square_count, "unit": "squares", "kind": "measured", "source": "square centres inside the outline"},
    ]
    for degrees in weather["cell_degrees"]:
        cells = weather_cells(area=area, cell_degrees=degrees)
        calls = cells * max(1.0, weather["variables"] / 10) * max(1.0, weather["days_per_request"] / 14)
        sizes.append({"item": f"weather cells of {degrees} degrees", "value": cells, "unit": "cells", "kind": "measured", "source": "cells that touch the outline"})
        sizes.append({"item": f"Open-Meteo calls per day, cells of {degrees} degrees", "value": round(calls), "unit": "calls", "kind": "estimated", "source": "one request per cell, Open-Meteo counts 37 days as 37/14 calls"})

    started = time.perf_counter()
    scores = score_one_day(square_count=square_count, days_ahead=days_ahead, rng=rng)
    score_seconds = time.perf_counter() - started
    day_path = context.output_dir / "scores_one_day.parquet"
    started = time.perf_counter()
    day_bytes = write_day(corner_e=corner_e, corner_n=corner_n, scores=scores, path=day_path)
    write_seconds = time.perf_counter() - started
    context.add_output(day_path)

    storage = settings["storage"]
    values = square_count * days_ahead * weather["species"]
    sizes += [
        {"item": "scores per day", "value": values, "unit": "values", "kind": "measured", "source": f"{square_count} squares, {days_ahead} days from today to 7 days ahead, 1 species"},
        {"item": "time to score one day with the D8 rules", "value": round(score_seconds, 2), "unit": "seconds", "kind": "measured", "source": "numpy on made-up weather, laptop in the run record"},
        {"item": "time to write one day of scores", "value": round(write_seconds, 2), "unit": "seconds", "kind": "measured", "source": "Parquet with zstd compression"},
        {"item": "one day of scores on disk", "value": round(day_bytes / 1024**2, 2), "unit": "MB", "kind": "measured", "source": "Parquet with zstd compression, made-up scores"},
        {"item": f"scores kept online, {storage['days_online']} days", "value": round(day_bytes * storage["days_online"] / 1024**2, 1), "unit": "MB", "kind": "estimated", "source": "one day on disk times days kept"},
        {"item": f"scores archive, {storage['days_archived']} days", "value": round(day_bytes * storage["days_archived"] / 1024**3, 2), "unit": "GB", "kind": "estimated", "source": "one day on disk times days kept"},
    ]
    for zoom in settings["tiles"]["zooms"]:
        sizes.append({"item": f"map images of 512 px at zoom {zoom}", "value": tile_count(area=area, zoom=zoom), "unit": "images", "kind": "measured", "source": "images that touch the outline"})

    reports_dir = ROOT / settings["reports_dir"]
    sizes_path = reports_dir / "p6_sizes.csv"
    write_csv(rows=sizes, columns=SIZE_COLUMNS, path=sizes_path)
    users_path = reports_dir / "p6_users.csv"
    write_csv(rows=user_rows(users=settings["users"]), columns=USER_COLUMNS, path=users_path)
    for path in (sizes_path, users_path):
        context.add_output(path)
