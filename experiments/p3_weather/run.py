"""P3a: rebuild the weather before each find, as looked back on and as known on that morning."""

import csv
import json
import random
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from micometeo.context import RunContext
from micometeo.weather import openmeteo
from micometeo.weather.features import (
    ERA5,
    IFS,
    LOOK_BACK,
    ON_THE_MORNING,
    ON_THE_MORNING_FROM_FORECAST_API,
    OUTPUT_COLUMNS,
    ROME,
    VALUE_COLUMNS,
    build_weather_features,
    daily_values,
    fetch_daily_values,
)

ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = ROOT / "reports"
SUMMARY_COLUMNS = [
    "area",
    "view",
    "window_days",
    "places",
    "places_with_complete_rain",
    "median_rain_mm",
    "mean_temperature_c",
]
DIFFERENCE_COLUMNS = [
    "area",
    "window_days",
    "places_compared",
    "median_abs_rain_difference_mm",
    "p90_abs_rain_difference_mm",
    "median_abs_temperature_difference_c",
]
DELAY_COLUMNS = [
    "checked_at",
    "today",
    "source",
    "dataset",
    "last_complete_rain_day",
    "days_missing_before_today",
    "last_day_complete_for_all_variables",
]
METRIC_COLUMNS = [
    "scope",
    "places",
    "requests",
    "cache_hits",
    "request_seconds",
    "estimated_quota_calls",
    "wall_seconds",
]


def write_csv(*, rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def place_from_find(*, find: dict[str, Any], assessment_date: date | None = None) -> dict[str, Any]:
    """Turn a find into a place assessed on the day of the find."""
    day = assessment_date or date.fromisoformat(str(find["event_date"]))
    return {
        "record_id": find["record_id"],
        "area": find["area"],
        "latitude": find["latitude"],
        "longitude": find["longitude"],
        "assessment_date": day,
        "target_date": day,
        "days_ahead": 0,
    }


def read_finds(*, path: Path) -> list[dict[str, Any]]:
    columns = ["record_id", "area", "event_date", "latitude", "longitude"]
    finds = pq.read_table(path, columns=columns).to_pylist()
    return sorted(finds, key=lambda find: find["record_id"])


def choose_sample(*, finds: list[dict[str, Any]], comparison_sample: int, seed: int) -> list[dict[str, Any]]:
    """Return all home finds and a seeded draw of comparison finds."""
    home = [find for find in finds if find["area"] == "home"]
    comparison = [find for find in finds if find["area"] == "comparison"]
    drawn = random.Random(seed).sample(comparison, min(comparison_sample, len(comparison)))
    return home + sorted(drawn, key=lambda find: find["record_id"])


def summary_rows(*, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return counts, median rain and mean temperature for each area, view and window."""
    result = []
    areas = sorted({row["area"] for row in rows})
    for area in [*areas, "all"]:
        for view in ("look_back", "on_the_morning"):
            for window in sorted({row["window_days"] for row in rows}):
                group = [
                    row
                    for row in rows
                    if row["view"] == view
                    and row["window_days"] == window
                    and area in (row["area"], "all")
                ]
                rain = [row["rain_mm"] for row in group if row["rain_mm"] is not None]
                temperature = [
                    row["mean_temperature_c"] for row in group if row["mean_temperature_c"] is not None
                ]
                result.append(
                    {
                        "area": area,
                        "view": view,
                        "window_days": window,
                        "places": len(group),
                        "places_with_complete_rain": len(rain),
                        "median_rain_mm": round(float(np.median(rain)), 2) if rain else None,
                        "mean_temperature_c": round(float(np.mean(temperature)), 2) if temperature else None,
                    }
                )
    return result


def difference_rows(*, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return how far the on the morning totals are from the look back totals."""
    paired: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    for row in rows:
        paired.setdefault((row["record_id"], row["window_days"]), {})[row["view"]] = row
    result = []
    areas = sorted({row["area"] for row in rows})
    for area in [*areas, "all"]:
        for window in sorted({row["window_days"] for row in rows}):
            rain, temperature = [], []
            for (_, window_days), views in paired.items():
                back, morning = views.get("look_back"), views.get("on_the_morning")
                if window_days != window or not back or not morning or area not in (back["area"], "all"):
                    continue
                if back["rain_mm"] is not None and morning["rain_mm"] is not None:
                    rain.append(abs(back["rain_mm"] - morning["rain_mm"]))
                if back["mean_temperature_c"] is not None and morning["mean_temperature_c"] is not None:
                    temperature.append(abs(back["mean_temperature_c"] - morning["mean_temperature_c"]))
            result.append(
                {
                    "area": area,
                    "window_days": window,
                    "places_compared": len(rain),
                    "median_abs_rain_difference_mm": round(float(np.median(rain)), 2) if rain else None,
                    "p90_abs_rain_difference_mm": round(float(np.percentile(rain, 90)), 2) if rain else None,
                    "median_abs_temperature_difference_c": (
                        round(float(np.median(temperature)), 2) if temperature else None
                    ),
                }
            )
    return result


def last_complete_day(*, daily: dict[date, dict[str, float | None]], today: date, columns: list[str]) -> date | None:
    """Return the latest Italian day before today that has a value for every given column."""
    days = [day for day, values in daily.items() if day < today and all(values.get(c) is not None for c in columns)]
    return max(days) if days else None


def delay_rows(*, client: openmeteo.OpenMeteo, settings: dict[str, Any], today: date, checked_at: str) -> list[dict[str, Any]]:
    """Ask each source for its last days and record the last complete day."""
    latitude, longitude = settings["check_latitude"], settings["check_longitude"]
    start = today - timedelta(days=settings["delay_check_days"])
    answers = [
        ("Open-Meteo Historical Weather API", model, client.archive_hourly(
            model=model, latitude=latitude, longitude=longitude, start=start, end=today
        ))
        for model in (ERA5, "era5", IFS)
    ]
    answers.append(
        (
            "Open-Meteo Forecast API",
            "best_match past_days",
            client.forecast_hourly(
                latitude=latitude, longitude=longitude, past_days=settings["delay_check_days"], today=today
            ),
        )
    )
    rows = []
    for source, dataset, hourly in answers:
        daily = daily_values(hourly=hourly)
        rain_day = last_complete_day(daily=daily, today=today, columns=["rain_mm"])
        all_day = last_complete_day(daily=daily, today=today, columns=VALUE_COLUMNS)
        rows.append(
            {
                "checked_at": checked_at,
                "today": today.isoformat(),
                "source": source,
                "dataset": dataset,
                "last_complete_rain_day": rain_day.isoformat() if rain_day else None,
                "days_missing_before_today": (today - rain_day).days - 1 if rain_day else None,
                "last_day_complete_for_all_variables": all_day.isoformat() if all_day else None,
            }
        )
    return rows


def today_check_rows(
    *, client: openmeteo.OpenMeteo, settings: dict[str, Any], home: list[dict[str, Any]], today: date, seed: int
) -> list[dict[str, Any]]:
    """Return on the morning totals for today from the Forecast API and from the archive."""
    chosen = random.Random(seed).sample(home, min(settings["today_check_home_places"], len(home)))
    places = [
        {
            "record_id": "pistoia_point",
            "area": "reference",
            "latitude": settings["check_latitude"],
            "longitude": settings["check_longitude"],
            "assessment_date": today,
            "target_date": today,
            "days_ahead": 0,
        },
        *(place_from_find(find=find, assessment_date=today) for find in chosen),
    ]
    windows = tuple(settings["windows"])
    missing_days = settings["reconstructed_missing_days"]
    forecast_daily = {
        place["record_id"]: daily_values(
            hourly=client.forecast_hourly(
                latitude=place["latitude"],
                longitude=place["longitude"],
                past_days=settings["forecast_past_days"],
                today=today,
            )
        )
        for place in places
    }
    from_forecast = build_weather_features(
        places=places,
        daily_by_dataset={"best_match_past_days": forecast_daily},
        windows=windows,
        reconstructed_missing_days=missing_days,
        views=(ON_THE_MORNING_FROM_FORECAST_API,),
    )
    from_archive = build_weather_features(
        places=places,
        daily_by_dataset=fetch_daily_values(
            places=places, client=client, windows=windows, reconstructed_missing_days=missing_days
        ),
        windows=windows,
        reconstructed_missing_days=missing_days,
        views=(ON_THE_MORNING,),
    )
    return from_forecast + from_archive


def metric_row(*, scope: str, places: int, client: openmeteo.OpenMeteo, wall_seconds: float) -> dict[str, Any]:
    metrics = client.metrics
    return {
        "scope": scope,
        "places": places,
        "requests": metrics.requests,
        "cache_hits": metrics.cache_hits,
        "request_seconds": round(metrics.request_seconds, 1),
        "estimated_quota_calls": round(metrics.quota_calls, 1),
        "wall_seconds": round(wall_seconds, 1),
    }


def add_sources(*, context: RunContext, downloaded_at: str, settings: dict[str, Any]) -> None:
    """Record both weather APIs with their licence and query template."""
    hourly = ",".join(openmeteo.HOURLY_VARIABLES)
    context.add_source(
        name="Open-Meteo Historical Weather API",
        url=openmeteo.ARCHIVE_URL,
        licence=openmeteo.LICENCE,
        version="v1",
        downloaded_at=downloaded_at,
        query={
            "latitude": "<place>",
            "longitude": "<place>",
            "start_date": "<assessment date minus 31 days>",
            "end_date": "<day before the assessment date>",
            "hourly": hourly,
            "models": f"{ERA5} or {IFS} or era5",
            "timezone": "GMT",
        },
    )
    context.add_source(
        name="Open-Meteo Forecast API",
        url=openmeteo.FORECAST_URL,
        licence=openmeteo.LICENCE,
        version="v1",
        downloaded_at=downloaded_at,
        query={
            "latitude": "<place>",
            "longitude": "<place>",
            "hourly": hourly,
            "past_days": settings["forecast_past_days"],
            "forecast_days": 1,
            "timezone": "GMT",
        },
    )


def run(context: RunContext) -> None:
    """Fetch the weather for the sample, write the totals and the check files."""
    started = time.monotonic()
    settings = context.config
    reports_dir = Path(settings.get("reports_dir") or REPORTS_DIR)
    if not reports_dir.is_absolute():
        reports_dir = ROOT / reports_dir
    finds_path = Path(settings["finds_path"])
    if not finds_path.is_absolute():
        finds_path = ROOT / finds_path
    context.add_input(finds_path)

    now = datetime.now(UTC)
    downloaded_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    today = now.astimezone(ROME).date()
    add_sources(context=context, downloaded_at=downloaded_at, settings=settings)

    finds = read_finds(path=finds_path)
    sample = choose_sample(finds=finds, comparison_sample=settings["comparison_sample"], seed=context.seed)
    places = [place_from_find(find=find) for find in sample]
    windows = tuple(settings["windows"])
    missing_days = settings["reconstructed_missing_days"]

    sample_client = openmeteo.OpenMeteo(cache_dir=context.raw_dir / "cache", pause_seconds=settings["pause_seconds"])
    daily = fetch_daily_values(
        places=places, client=sample_client, windows=windows, reconstructed_missing_days=missing_days
    )
    rows = build_weather_features(
        places=places, daily_by_dataset=daily, windows=windows, reconstructed_missing_days=missing_days
    )
    sample_seconds = time.monotonic() - started

    weather_path = context.output_dir / "weather_windows.parquet"
    pq.write_table(pa.Table.from_pylist(rows), weather_path)
    summary_path = reports_dir / "p3_summary.csv"
    write_csv(rows=summary_rows(rows=rows), columns=SUMMARY_COLUMNS, path=summary_path)
    differences_path = reports_dir / "p3_view_differences.csv"
    write_csv(rows=difference_rows(rows=rows), columns=DIFFERENCE_COLUMNS, path=differences_path)

    check_client = openmeteo.OpenMeteo(cache_dir=None, pause_seconds=settings["pause_seconds"])
    delays_path = reports_dir / "p3_delays.csv"
    write_csv(
        rows=delay_rows(client=check_client, settings=settings, today=today, checked_at=downloaded_at),
        columns=DELAY_COLUMNS,
        path=delays_path,
    )
    home = [find for find in sample if find["area"] == "home"]
    today_path = reports_dir / "p3_today_check.csv"
    today_rows = today_check_rows(client=check_client, settings=settings, home=home, today=today, seed=context.seed)
    write_csv(rows=today_rows, columns=OUTPUT_COLUMNS, path=today_path)

    wall = time.monotonic() - started
    metrics = [
        metric_row(scope="sample", places=len(places), client=sample_client, wall_seconds=sample_seconds),
        metric_row(scope="checks", places=len({row["record_id"] for row in today_rows}), client=check_client, wall_seconds=wall - sample_seconds),
    ]
    metrics_path = reports_dir / "p3_metrics.csv"
    write_csv(rows=metrics, columns=METRIC_COLUMNS, path=metrics_path)
    print(json.dumps(metrics, indent=2))
    for path in (weather_path, summary_path, differences_path, delays_path, today_path, metrics_path):
        context.add_output(path)
