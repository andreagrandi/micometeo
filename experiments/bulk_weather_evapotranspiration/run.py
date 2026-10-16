"""Bulk weather evapotranspiration: compute it from the file weather and compare it with the API.

The script reads the stored file weather and API answers of the bulk_weather run. It makes no network calls.
"""

import csv
import json
import statistics
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sporameteo.context import RunContext
from sporameteo.weather.evapotranspiration import (
    hourly_reference_evapotranspiration,
    top_of_atmosphere_radiation,
)

ROME = ZoneInfo("Europe/Rome")
APIS = ("archive", "forecast")
INPUT_VARIABLES = ("temperature_2m", "dew_point_2m", "shortwave_radiation", "wind_speed_10m")
CELL_COLUMNS = [
    "api",
    "cell",
    "place_height_m",
    "days",
    "median_abs_daily_difference_mm",
    "largest_abs_daily_difference_mm",
    "largest_difference_date",
    "largest_difference_sign",
    "total_ours_mm",
    "total_api_mm",
    "total_difference_mm",
]


def write_csv(*, rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    """Write rows to a CSV file with the given columns."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def read_api_et0(*, api_dir: Path, api_name: str, grid_points: dict[str, tuple[float, float]], heights: dict[str, float], tolerance: float) -> dict[str, dict[str, float]]:
    """Return the API evapotranspiration by cell and UTC hour text.

    Answers match by grid point coordinates. Cells that share a grid point differ in place height, so the height tells them apart.
    """
    answers = json.loads((api_dir / f"{api_name}_ecmwf_ifs.json").read_text(encoding="utf-8"))
    result: dict[str, dict[str, float]] = {}
    for answer in answers:
        matching = [
            cell
            for cell, (latitude, longitude) in grid_points.items()
            if abs(answer["latitude"] - latitude) < tolerance and abs(answer["longitude"] - longitude) < tolerance
            and abs(answer["elevation"] - heights[cell]) < 0.5
        ]
        if len(matching) != 1:
            raise ValueError(f"{api_name} answer at {answer['latitude']},{answer['longitude']} matches {len(matching)} cells")
        hourly = answer["hourly"]
        result[matching[0]] = {
            datetime.fromtimestamp(stamp, tz=UTC).strftime("%Y-%m-%d %H:%M"): value
            for stamp, value in zip(hourly["time"], hourly["et0_fao_evapotranspiration"], strict=True)
        }
    return result


def summarise(*, differences: list[float]) -> dict[str, float | int]:
    """Return the number of values, median absolute difference and largest absolute difference."""
    absolute = [abs(value) for value in differences]
    return {
        "count": len(absolute),
        "median_abs_difference_mm": round(statistics.median(absolute), 4),
        "largest_abs_difference_mm": round(max(absolute), 4),
    }


def run(context: RunContext) -> None:
    """Compute evapotranspiration for 20 cells and compare it with the API."""
    settings = context.config
    root = Path(__file__).resolve().parent.parent.parent
    pairs_path = root / settings["hourly_pairs_path"]
    match_path = root / settings["grid_match_path"]
    api_dir = root / settings["api_dir"]
    context.add_input(pairs_path)
    context.add_input(match_path)
    for api_name in APIS:
        context.add_input(api_dir / f"{api_name}_ecmwf_ifs.json")

    with match_path.open(encoding="utf-8") as handle:
        matches = {row["cell_key"]: row for row in csv.DictReader(handle)}
    grid_points = {cell: (float(row["file_latitude"]), float(row["file_longitude"])) for cell, row in matches.items()}
    heights = {cell: float(row["place_height_m"]) for cell, row in matches.items()}
    api_et0 = {
        api_name: read_api_et0(api_dir=api_dir, api_name=api_name, grid_points=grid_points, heights=heights, tolerance=settings["coordinate_tolerance"])
        for api_name in APIS
    }

    # inputs[(api, cell, hour)][variable] = (file value, api value)
    inputs: dict[tuple[str, str, str], dict[str, tuple[float, float]]] = defaultdict(dict)
    with pairs_path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["variable"] in INPUT_VARIABLES:
                inputs[(row["api"], row["cell"], row["hour_utc"])][row["variable"]] = (float(row["file"]), float(row["api_value"]))

    hourly_rows: list[dict[str, Any]] = []
    for (api_name, cell, hour_text), values in sorted(inputs.items()):
        if cell not in api_et0[api_name]:
            continue
        hour_end = datetime.strptime(hour_text, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        latitude, longitude = grid_points[cell]
        radiation = top_of_atmosphere_radiation(latitude=latitude, longitude=longitude, hour_end=hour_end)
        elevation = float(matches[cell]["place_height_m"])
        results = []
        for source in (0, 1):
            results.append(
                hourly_reference_evapotranspiration(
                    temperature_c=values["temperature_2m"][source],
                    dew_point_c=values["dew_point_2m"][source],
                    shortwave_radiation_w_m2=values["shortwave_radiation"][source],
                    wind_speed_10m_m_s=values["wind_speed_10m"][source],
                    elevation_m=elevation,
                    top_of_atmosphere_w_m2=radiation,
                )
            )
        hourly_rows.append(
            {
                "api": api_name,
                "cell": cell,
                "hour_utc": hour_text,
                "top_of_atmosphere_w_m2": round(radiation, 2),
                "ours_mm": round(results[0], 4),
                "ours_from_rounded_inputs_mm": round(results[1], 4),
                "api_mm": api_et0[api_name][cell][hour_text],
            }
        )
    hourly_path = context.output_dir / "hourly_pairs.csv"
    write_csv(
        rows=hourly_rows,
        columns=["api", "cell", "hour_utc", "top_of_atmosphere_w_m2", "ours_mm", "ours_from_rounded_inputs_mm", "api_mm"],
        path=hourly_path,
    )
    context.add_output(hourly_path)

    # Sum hours into days from midnight to midnight Europe/Rome.
    sums: dict[tuple[str, str, date], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0])
    for row in hourly_rows:
        moment = datetime.strptime(row["hour_utc"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        day_sum = sums[(row["api"], row["cell"], moment.astimezone(ROME).date())]
        day_sum[0] += row["ours_mm"]
        day_sum[1] += row["ours_from_rounded_inputs_mm"]
        day_sum[2] += row["api_mm"]
        day_sum[3] += 1
    daily_rows = []
    for (api_name, cell, day), (ours, rounded, api_value, hours) in sorted(sums.items()):
        expected = round((datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=ROME) - datetime.combine(day, datetime.min.time(), tzinfo=ROME)).total_seconds() / 3600)
        if hours != expected:
            continue
        daily_rows.append(
            {
                "api": api_name,
                "cell": cell,
                "date": day.isoformat(),
                "ours_mm": round(ours, 4),
                "ours_from_rounded_inputs_mm": round(rounded, 4),
                "api_mm": round(api_value, 4),
                "difference_mm": round(ours - api_value, 4),
            }
        )
    daily_path = context.output_dir / "daily_pairs.csv"
    write_csv(
        rows=daily_rows,
        columns=["api", "cell", "date", "ours_mm", "ours_from_rounded_inputs_mm", "api_mm", "difference_mm"],
        path=daily_path,
    )
    context.add_output(daily_path)

    cell_rows = []
    for api_name in APIS:
        for cell in sorted(api_et0[api_name]):
            days = [row for row in daily_rows if row["api"] == api_name and row["cell"] == cell]
            largest = max(days, key=lambda row: abs(row["difference_mm"]))
            total_ours = round(sum(row["ours_mm"] for row in days), 3)
            total_api = round(sum(row["api_mm"] for row in days), 3)
            cell_rows.append(
                {
                    "api": api_name,
                    "cell": cell,
                    "place_height_m": matches[cell]["place_height_m"],
                    "days": len(days),
                    "median_abs_daily_difference_mm": round(statistics.median(abs(row["difference_mm"]) for row in days), 4),
                    "largest_abs_daily_difference_mm": round(abs(largest["difference_mm"]), 4),
                    "largest_difference_date": largest["date"],
                    "largest_difference_sign": "ours higher" if largest["difference_mm"] > 0 else "ours lower",
                    "total_ours_mm": total_ours,
                    "total_api_mm": total_api,
                    "total_difference_mm": round(total_ours - total_api, 3),
                }
            )
    cells_path = root / "reports" / "bulk_weather_evapotranspiration_cells.csv"
    write_csv(rows=cell_rows, columns=CELL_COLUMNS, path=cells_path)
    context.add_output(cells_path)

    archive_cells = [row for row in cell_rows if row["api"] == "archive"]
    summary = {
        "cells": len({row["cell"] for row in cell_rows}),
        "hourly_from_file_weather": summarise(differences=[row["ours_mm"] - row["api_mm"] for row in hourly_rows]),
        "hourly_from_rounded_api_inputs": summarise(differences=[row["ours_from_rounded_inputs_mm"] - row["api_mm"] for row in hourly_rows]),
        "daily_from_file_weather": summarise(differences=[row["difference_mm"] for row in daily_rows]),
        "daily_from_rounded_api_inputs": summarise(differences=[row["ours_from_rounded_inputs_mm"] - row["api_mm"] for row in daily_rows]),
        "archive_cells_with_total_difference_over_tolerance": sum(
            1 for row in archive_cells if abs(row["total_difference_mm"]) > settings["total_tolerance_mm"]
        ),
        "total_tolerance_mm": settings["total_tolerance_mm"],
    }
    summary_path = context.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    context.add_output(summary_path)
