"""P3b: compare forecasts published in the past with the weather that fell, and survey the sources."""

import csv
import json
import random
import time
from collections.abc import Callable
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
    FORECAST_FIRST_RUN,
    IFS,
    LOOK_BACK,
    ROME,
    ForecastRun,
    build_weather_features,
    daily_values,
    forecast_value_rows,
    latest_run_before,
)

ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = ROOT / "reports"
SURVEY_COLUMNS = ["api", "model", "first_day", "max_days_ahead", "variables", "run_time_known", "note"]
TESTABLE_COLUMNS = [
    "area",
    "year",
    "finds",
    "testable_7_days_ahead_single_runs",
    "testable_7_days_ahead_previous_runs_best_match",
]
RAIN_COLUMNS = [
    "area",
    "days_ahead",
    "period",
    "places",
    "median_actual_rain_mm",
    "median_forecast_rain_mm",
    "mean_difference_mm",
    "median_abs_difference_mm",
    "p90_abs_difference_mm",
    "correlation",
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
SURVEY_NOTE = "First day comes from a binary search that assumes data continues after it starts."
PREVIOUS_DAYS = range(1, 8)
SURVEY_LAG_DAYS = 30


def write_csv(*, rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def read_finds(*, path: Path) -> list[dict[str, Any]]:
    columns = ["record_id", "area", "event_date", "latitude", "longitude"]
    finds = pq.read_table(path, columns=columns).to_pylist()
    return sorted(finds, key=lambda find: find["record_id"])


def find_day(*, find: dict[str, Any]) -> date:
    return date.fromisoformat(str(find["event_date"]))


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


def series_of(*, hourly: dict[str, Any], name: str, model: str) -> list[Any]:
    """Return an hourly series by name, with or without the model suffix the API may add."""
    return hourly.get(name) or hourly.get(f"{name}_{model}") or []


def has_full_day(*, hourly: dict[str, Any], name: str, model: str) -> bool:
    series = series_of(hourly=hourly, name=name, model=model)
    return len(series) == 24 and all(value is not None for value in series)


def first_available_day(*, first: date, last: date, is_available: Callable[[date], bool]) -> date | None:
    """Return the first day with data, by binary search. Return None when the last day has none."""
    if not is_available(last):
        return None
    while first < last:
        middle = first + timedelta(days=(last - first).days // 2)
        if is_available(middle):
            last = middle
        else:
            first = middle + timedelta(days=1)
    return first


def day_query(*, settings: dict[str, Any], model: str, day: date, hourly: list[str]) -> dict[str, Any]:
    return {
        "latitude": settings["check_latitude"],
        "longitude": settings["check_longitude"],
        "start_date": day.isoformat(),
        "end_date": day.isoformat(),
        "hourly": ",".join(hourly),
        "models": model,
        "timezone": "GMT",
    }


def run_query(*, settings: dict[str, Any], model: str, day: date, hourly: list[str], forecast_days: int) -> dict[str, Any]:
    return {
        "latitude": settings["check_latitude"],
        "longitude": settings["check_longitude"],
        "hourly": ",".join(hourly),
        "models": model,
        "run": f"{day.isoformat()}T00:00",
        "forecast_days": forecast_days,
        "timezone": "GMT",
    }


def survey_api(
    *, client: openmeteo.OpenMeteo, settings: dict[str, Any], api: str, model: str, today: date
) -> dict[str, Any]:
    """Return the survey row of one model on one API, probing the check point only."""
    first = date.fromisoformat(settings["survey_start"])
    recent = today - timedelta(days=SURVEY_LAG_DAYS)
    hourly_names = list(openmeteo.HOURLY_VARIABLES)
    url = {
        "previous_runs": openmeteo.PREVIOUS_RUNS_URL,
        "single_runs": openmeteo.SINGLE_RUNS_URL,
        "historical_forecast": openmeteo.HISTORICAL_FORECAST_URL,
    }[api]

    def ask(*, day: date, kind: str, names: list[str], forecast_days: int = 1) -> dict[str, Any]:
        key = f"{api}_{model}_{day.isoformat()}_{kind}"
        if api == "single_runs":
            query = run_query(settings=settings, model=model, day=day, hourly=names, forecast_days=forecast_days)
        else:
            query = day_query(settings=settings, model=model, day=day, hourly=names)
        return client.probe(url=url, query=query, cache_key=key)

    def found(day: date) -> bool:
        if api == "previous_runs":
            answer = ask(day=day, kind="search", names=["precipitation_previous_day1"])
            return not answer.get("error") and has_full_day(
                hourly=answer.get("hourly", {}), name="precipitation_previous_day1", model=model
            )
        if api == "single_runs":
            return not ask(day=day, kind="search", names=["precipitation"]).get("error")
        answer = ask(day=day, kind="search", names=["precipitation"])
        return not answer.get("error") and has_full_day(hourly=answer.get("hourly", {}), name="precipitation", model=model)

    first_day = first_available_day(first=first, last=recent, is_available=found)
    row: dict[str, Any] = {
        "api": api,
        "model": model,
        "first_day": first_day.isoformat() if first_day else None,
        "max_days_ahead": None,
        "variables": "",
        "run_time_known": api == "single_runs",
        "note": SURVEY_NOTE,
    }
    if first_day is None:
        row["note"] = f"No data on {recent.isoformat()}. {SURVEY_NOTE}"
        return row
    if api == "previous_runs":
        names = [f"{name}_previous_day1" for name in hourly_names]
        names += [f"precipitation_previous_day{n}" for n in PREVIOUS_DAYS if n > 1]
        answer = ask(day=recent, kind="detail", names=names)
        hourly = answer.get("hourly", {})
        full = [name for name in names if has_full_day(hourly=hourly, name=name, model=model)]
        row["variables"] = " ".join(name for name in full if name.endswith("_previous_day1"))
        days = [n for n in PREVIOUS_DAYS if f"precipitation_previous_day{n}" in full]
        row["max_days_ahead"] = max(days) if days else None
        if answer.get("error"):
            row["note"] = f"{answer.get('reason')}. {SURVEY_NOTE}"
    elif api == "single_runs":
        answer = ask(day=recent, kind="detail", names=hourly_names, forecast_days=16)
        hourly = answer.get("hourly", {})
        rain = series_of(hourly=hourly, name="precipitation", model=model)
        filled = [index for index, value in enumerate(rain) if value is not None]
        row["max_days_ahead"] = round(max(filled) / 24, 1) if filled else None
        # The run starts at 00 UTC, so hours 24 to 47 are one full UTC day.
        row["variables"] = " ".join(
            name
            for name in hourly_names
            if len(series_of(hourly=hourly, name=name, model=model)) >= 48
            and all(value is not None for value in series_of(hourly=hourly, name=name, model=model)[24:48])
        )
        if answer.get("error"):
            row["note"] = f"{answer.get('reason')}. {SURVEY_NOTE}"
    else:
        answer = ask(day=recent, kind="detail", names=hourly_names)
        hourly = answer.get("hourly", {})
        row["max_days_ahead"] = 0
        row["variables"] = " ".join(
            name for name in hourly_names if has_full_day(hourly=hourly, name=name, model=model)
        )
        if answer.get("error"):
            row["note"] = f"{answer.get('reason')}. {SURVEY_NOTE}"
    return row


def survey_rows(*, client: openmeteo.OpenMeteo, settings: dict[str, Any], today: date) -> list[dict[str, Any]]:
    rows = []
    for api, key in (
        ("previous_runs", "previous_runs_models"),
        ("single_runs", "single_runs_models"),
        ("historical_forecast", "historical_forecast_models"),
    ):
        for model in settings[key]:
            rows.append(survey_api(client=client, settings=settings, api=api, model=model, today=today))
    return rows


def first_day_of(*, survey: list[dict[str, Any]], api: str, model: str) -> date | None:
    for row in survey:
        if row["api"] == api and row["model"] == model and row["first_day"]:
            return date.fromisoformat(row["first_day"])
    return None


def testable_rows(
    *, finds: list[dict[str, Any]], survey: list[dict[str, Any]], settings: dict[str, Any]
) -> list[dict[str, Any]]:
    """Count finds per area and year whose assessment 7 days ahead has a stored forecast."""
    single_first = first_day_of(survey=survey, api="single_runs", model=settings["forecast_model"])
    previous_first = first_day_of(survey=survey, api="previous_runs", model="best_match")
    counts: dict[tuple[str, str], list[int]] = {}
    for find in finds:
        day = find_day(find=find)
        run = latest_run_before(
            assessment_date=day - timedelta(days=7), publication_delay_hours=settings["publication_delay_hours"]
        )
        single = single_first is not None and run.date() >= single_first
        previous = previous_first is not None and day - timedelta(days=8) >= previous_first
        for area in (find["area"], "all"):
            for year in (str(day.year), "all"):
                entry = counts.setdefault((area, year), [0, 0, 0])
                entry[0] += 1
                entry[1] += int(single)
                entry[2] += int(previous)
    return [
        {
            "area": area,
            "year": year,
            "finds": entry[0],
            "testable_7_days_ahead_single_runs": entry[1],
            "testable_7_days_ahead_previous_runs_best_match": entry[2],
        }
        for (area, year), entry in sorted(counts.items(), key=lambda item: (item[0][0] == "all", *item[0]))
    ]


def eligible_finds(*, finds: list[dict[str, Any]], settings: dict[str, Any], today: date) -> list[dict[str, Any]]:
    """Return finds with a stored run for every days_ahead and ERA5 for the day before the find."""
    result = []
    for find in finds:
        day = find_day(find=find)
        if day > today - timedelta(days=8):
            continue
        if all(
            latest_run_before(
                assessment_date=day - timedelta(days=k), publication_delay_hours=settings["publication_delay_hours"]
            )
            >= FORECAST_FIRST_RUN
            for k in settings["days_ahead"]
        ):
            result.append(find)
    return result


def choose_sample(*, finds: list[dict[str, Any]], comparison_sample: int, seed: int) -> list[dict[str, Any]]:
    """Return all home finds and a seeded draw of comparison finds."""
    home = [find for find in finds if find["area"] == "home"]
    comparison = [find for find in finds if find["area"] == "comparison"]
    drawn = random.Random(seed).sample(comparison, min(comparison_sample, len(comparison)))
    return home + sorted(drawn, key=lambda find: find["record_id"])


def place_for(*, find: dict[str, Any], days_ahead: int) -> dict[str, Any]:
    """Return the place assessed days_ahead days before the find."""
    target = find_day(find=find)
    return {
        "record_id": find["record_id"],
        "area": find["area"],
        "latitude": find["latitude"],
        "longitude": find["longitude"],
        "assessment_date": target - timedelta(days=days_ahead),
        "target_date": target,
        "days_ahead": days_ahead,
    }


def rain_over(*, daily: dict[date, dict[str, float | None]], first: date, last: date) -> float | None:
    """Return the rain over the days first to last, or None when a day is missing."""
    values = []
    day = first
    while day <= last:
        value = daily.get(day, {}).get("rain_mm")
        if value is None:
            return None
        values.append(value)
        day += timedelta(days=1)
    return sum(values)


def rain_stats(*, area: str, days_ahead: int, period: str, pairs: list[tuple[float, float]]) -> dict[str, Any]:
    actual = np.array([a for a, _ in pairs])
    forecast = np.array([f for _, f in pairs])
    gap = forecast - actual
    correlation = None
    if len(pairs) >= 2 and actual.std() > 0 and forecast.std() > 0:
        correlation = round(float(np.corrcoef(actual, forecast)[0, 1]), 3)
    return {
        "area": area,
        "days_ahead": days_ahead,
        "period": period,
        "places": len(pairs),
        "median_actual_rain_mm": round(float(np.median(actual)), 2),
        "median_forecast_rain_mm": round(float(np.median(forecast)), 2),
        "mean_difference_mm": round(float(gap.mean()), 2),
        "median_abs_difference_mm": round(float(np.median(np.abs(gap))), 2),
        "p90_abs_difference_mm": round(float(np.percentile(np.abs(gap), 90)), 2),
        "correlation": correlation,
    }


def rain_rows(
    *,
    samples: dict[tuple[int, str], list[tuple[str, float, float]]],
) -> list[dict[str, Any]]:
    """Return one row per days_ahead, period and area from (area, actual, forecast) samples."""
    order = {"forecast days": 0, "single day": 1}
    rows = []
    for (days_ahead, period), items in sorted(samples.items(), key=lambda item: (order.get(item[0][1], 2), item[0][1], item[0][0])):
        for area in ("home", "comparison", "all"):
            pairs = [(a, f) for name, a, f in items if area in (name, "all")]
            if pairs:
                rows.append(rain_stats(area=area, days_ahead=days_ahead, period=period, pairs=pairs))
    return rows


def add_sources(*, context: RunContext, downloaded_at: str, settings: dict[str, Any]) -> None:
    """Record the four weather APIs with their licence and query template."""
    hourly = ",".join(openmeteo.HOURLY_VARIABLES)
    common = {"latitude": "<place>", "longitude": "<place>", "hourly": hourly, "timezone": "GMT"}
    entries = [
        (
            "Open-Meteo Historical Weather API",
            openmeteo.ARCHIVE_URL,
            {
                **common,
                "start_date": "<find date minus 31 days>",
                "end_date": "<day before the find>",
                "models": f"{ERA5} or {IFS}",
            },
        ),
        (
            "Open-Meteo Single Runs API",
            openmeteo.SINGLE_RUNS_URL,
            {
                **common,
                "models": settings["forecast_model"],
                "run": "<00 or 12 UTC run published before the assessment day>",
                "forecast_days": settings["forecast_days"],
            },
        ),
        (
            "Open-Meteo Previous Runs API",
            openmeteo.PREVIOUS_RUNS_URL,
            {**common, "start_date": "<survey day>", "end_date": "<survey day>", "models": "<model>"},
        ),
        (
            "Open-Meteo Historical Forecast API",
            openmeteo.HISTORICAL_FORECAST_URL,
            {**common, "start_date": "<survey day>", "end_date": "<survey day>", "models": "<model>"},
        ),
    ]
    for name, url, query in entries:
        context.add_source(
            name=name,
            url=url,
            licence=openmeteo.LICENCE,
            version="v1",
            downloaded_at=downloaded_at,
            query=query,
        )


def run(context: RunContext) -> None:
    """Survey the sources, fetch forecasts published in the past for the sample and compare the rain."""
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
    cache_dir = context.raw_dir / "cache"

    survey_client = openmeteo.OpenMeteo(cache_dir=cache_dir, pause_seconds=settings["pause_seconds"])
    survey = survey_rows(client=survey_client, settings=settings, today=today)
    survey_seconds = time.monotonic() - started
    survey_path = reports_dir / "p3b_forecast_sources.csv"
    write_csv(rows=survey, columns=SURVEY_COLUMNS, path=survey_path)

    finds = read_finds(path=finds_path)
    testable_path = reports_dir / "p3b_testable_finds.csv"
    write_csv(
        rows=testable_rows(finds=finds, survey=survey, settings=settings),
        columns=TESTABLE_COLUMNS,
        path=testable_path,
    )

    sample = choose_sample(
        finds=eligible_finds(finds=finds, settings=settings, today=today),
        comparison_sample=settings["comparison_sample"],
        seed=context.seed,
    )
    windows = tuple(settings["windows"])
    missing_days = settings["reconstructed_missing_days"]
    delay = timedelta(hours=settings["publication_delay_hours"])
    sample_client = openmeteo.OpenMeteo(cache_dir=cache_dir, pause_seconds=settings["pause_seconds"])

    # One archive answer per find covers the past part of every days_ahead.
    daily: dict[str, dict[str, Any]] = {ERA5: {}, IFS: {}}
    forecasts: dict[int, dict[str, ForecastRun]] = {k: {} for k in settings["days_ahead"]}
    skipped = {k: 0 for k in settings["days_ahead"]}
    for find in sample:
        day = find_day(find=find)
        location = {"latitude": find["latitude"], "longitude": find["longitude"]}
        daily[ERA5][find["record_id"]] = daily_values(
            hourly=sample_client.archive_hourly(
                model=ERA5, start=day - timedelta(days=max(windows) + 1), end=day - timedelta(days=1), **location
            )
        )
        daily[IFS][find["record_id"]] = daily_values(
            hourly=sample_client.archive_hourly(
                model=IFS, start=day - timedelta(days=missing_days + 8), end=day - timedelta(days=1), **location
            )
        )
        for k in settings["days_ahead"]:
            run_time = latest_run_before(
                assessment_date=day - timedelta(days=k), publication_delay_hours=settings["publication_delay_hours"]
            )
            hourly = sample_client.single_run_hourly(
                model=settings["forecast_model"],
                run_time=run_time,
                forecast_days=settings["forecast_days"],
                **location,
            )
            if hourly is None:
                skipped[k] += 1
                continue
            forecasts[k][find["record_id"]] = ForecastRun(
                model=settings["forecast_model"],
                run_time=run_time,
                published_at=run_time + delay,
                daily=daily_values(hourly=hourly),
            )

    rows = build_weather_features(
        places=[place_for(find=find, days_ahead=0) for find in sample],
        daily_by_dataset=daily,
        windows=windows,
        reconstructed_missing_days=missing_days,
        views=(LOOK_BACK,),
    )
    actual_rows = {(row["record_id"], row["window_days"]): row for row in rows}
    value_rows: list[dict[str, Any]] = []
    samples: dict[tuple[int, str], list[tuple[str, float, float]]] = {}

    def add_sample(*, key: tuple[int, str], area: str, actual: float | None, forecast: float | None) -> None:
        if actual is not None and forecast is not None:
            samples.setdefault(key, []).append((area, actual, forecast))

    for k in settings["days_ahead"]:
        places = [place_for(find=find, days_ahead=k) for find in sample if find["record_id"] in forecasts[k]]
        forecast_rows = build_weather_features(
            places=places,
            daily_by_dataset=daily,
            windows=windows,
            reconstructed_missing_days=missing_days,
            forecasts=forecasts[k],
        )
        rows += forecast_rows
        for row in forecast_rows:
            actual = actual_rows[(row["record_id"], row["window_days"])]
            add_sample(key=(k, f"window {row['window_days']}"), area=row["area"], actual=actual["rain_mm"], forecast=row["rain_mm"])
        for place in places:
            forecast = forecasts[k][place["record_id"]]
            era5 = daily[ERA5][place["record_id"]]
            first, last = place["assessment_date"], place["target_date"] - timedelta(days=1)
            add_sample(
                key=(k, "forecast days"),
                area=place["area"],
                actual=rain_over(daily=era5, first=first, last=last),
                forecast=rain_over(daily=forecast.daily, first=first, last=last),
            )
            stored = forecast_value_rows(place=place, forecast=forecast)
            value_rows += stored
            if k == 7:
                for value in stored:
                    add_sample(
                        key=(value["days_ahead"], "single day"),
                        area=place["area"],
                        actual=era5.get(date.fromisoformat(value["forecast_date"]), {}).get("rain_mm"),
                        forecast=value["rain_mm"],
                    )
    sample_seconds = time.monotonic() - started - survey_seconds

    weather_path = context.output_dir / "weather_windows.parquet"
    pq.write_table(pa.Table.from_pylist(rows), weather_path)
    values_path = context.output_dir / "forecast_values.parquet"
    pq.write_table(pa.Table.from_pylist(value_rows), values_path)
    rain_path = reports_dir / "p3b_forecast_rain.csv"
    write_csv(rows=rain_rows(samples=samples), columns=RAIN_COLUMNS, path=rain_path)

    metrics = [
        metric_row(scope="survey", places=len(survey), client=survey_client, wall_seconds=survey_seconds),
        metric_row(scope="sample", places=len(sample), client=sample_client, wall_seconds=sample_seconds),
    ]
    metrics_path = reports_dir / "p3b_metrics.csv"
    write_csv(rows=metrics, columns=METRIC_COLUMNS, path=metrics_path)
    print(json.dumps({"metrics": metrics, "skipped_runs_by_days_ahead": skipped}, indent=2))
    for path in (survey_path, testable_path, weather_path, values_path, rain_path, metrics_path):
        context.add_output(path)
