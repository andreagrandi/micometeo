"""Group hourly values into Italian days and total the days before an assessment date.

A day runs from midnight to midnight Europe/Rome and has 23 or 25 hours when summer time changes.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
DEFAULT_WINDOWS = (7, 14, 30)
ERA5 = "era5_seamless"
IFS = "ecmwf_ifs"
# Open-Meteo has no ecmwf_ifs values before this UTC day, so earlier requests would come back empty.
IFS_FIRST_DAY = date(2017, 1, 1)
FORECAST_MODEL = "ecmwf_ifs"
# The Single Runs API has no runs before this moment.
FORECAST_FIRST_RUN = datetime(2024, 3, 14, 0, tzinfo=UTC)
MAX_DAYS_AHEAD = 7
# The 06 and 18 UTC runs are often missing, so only these hours are used.
FORECAST_RUN_HOURS = (0, 12)
# Hourly name, daily column, and how the hours of a day combine.
DAILY_VARIABLES = (
    ("precipitation", "rain_mm", "sum"),
    ("temperature_2m", "mean_temperature_c", "mean"),
    ("et0_fao_evapotranspiration", "evaporation_mm", "sum"),
    ("soil_moisture_0_to_7cm", "mean_soil_moisture", "mean"),
    ("soil_temperature_0_to_7cm", "mean_soil_temperature_c", "mean"),
)
VALUE_COLUMNS = [column for _, column, _ in DAILY_VARIABLES]
OUTPUT_COLUMNS = [
    "record_id",
    "area",
    "latitude",
    "longitude",
    "assessment_date",
    "target_date",
    "days_ahead",
    "view",
    "window_days",
    "source",
    "dataset",
    "value_kind",
    *VALUE_COLUMNS,
    "complete_days",
    "reconstructed_days",
    "model_days",
    "forecast_days",
    "forecast_model",
    "forecast_run_time",
    "forecast_published_at",
]
FORECAST_VALUE_COLUMNS = [
    "record_id",
    "area",
    "assessment_date",
    "forecast_date",
    "days_ahead",
    "model",
    "run_time",
    "published_at",
    *VALUE_COLUMNS,
]

DailyValues = dict[date, dict[str, float | None]]


@dataclass(frozen=True)
class ViewSpec:
    """Which dataset supplies which days of a window."""

    name: str
    source: str
    dataset: str
    value_kind: str
    old_dataset: str
    recent_dataset: str
    recent_is_model: bool
    old_is_model: bool = False


LOOK_BACK = ViewSpec(
    name="look_back",
    source="Open-Meteo Historical Weather API",
    dataset=ERA5,
    value_kind="reconstructed past weather",
    old_dataset=ERA5,
    recent_dataset=ERA5,
    recent_is_model=False,
)
ON_THE_MORNING = ViewSpec(
    name="on_the_morning",
    source="Open-Meteo Historical Weather API",
    dataset=f"{ERA5}, {IFS}",
    value_kind="reconstructed past weather and model values for past hours",
    old_dataset=ERA5,
    recent_dataset=IFS,
    recent_is_model=True,
)
ON_THE_MORNING_FROM_FORECAST_API = ViewSpec(
    name="on_the_morning",
    source="Open-Meteo Forecast API",
    dataset="best_match past_days",
    value_kind="model values for past hours",
    old_dataset="best_match_past_days",
    recent_dataset="best_match_past_days",
    recent_is_model=True,
    old_is_model=True,
)
FORECAST = ViewSpec(
    name="forecast",
    source="Open-Meteo Historical Weather API and Single Runs API",
    dataset=f"{ERA5}, {IFS}, single runs {FORECAST_MODEL}",
    value_kind="reconstructed past weather, model values for past hours and a forecast published in the past",
    old_dataset=ERA5,
    recent_dataset=IFS,
    recent_is_model=True,
)
DEFAULT_VIEWS = (LOOK_BACK, ON_THE_MORNING)


@dataclass(frozen=True)
class ForecastRun:
    """One stored model run, with the Italian days it forecast."""

    model: str
    run_time: datetime
    published_at: datetime
    daily: DailyValues


def day_start(*, day: date) -> datetime:
    """Return midnight Europe/Rome at the start of the day, as a UTC time."""
    return datetime.combine(day, time(0), tzinfo=ROME).astimezone(UTC)


def latest_run_before(*, assessment_date: date, publication_delay_hours: int) -> datetime:
    """Return the latest run that was published before the assessment day started in Italy.

    A run counts as published its start time plus the delay.
    """
    cutoff = day_start(day=assessment_date)
    delay = timedelta(hours=publication_delay_hours)
    for back in range(0, 10):
        run_day = cutoff.date() - timedelta(days=back)
        for hour in sorted(FORECAST_RUN_HOURS, reverse=True):
            run_time = datetime.combine(run_day, time(hour), tzinfo=UTC)
            if run_time + delay <= cutoff:
                return run_time
    raise ValueError(f"No run found before {assessment_date.isoformat()}")


def hours_in_local_day(*, day: date) -> int:
    """Return 23, 24 or 25, the number of hours between two Italian midnights."""
    start = datetime.combine(day, time(0), tzinfo=ROME).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=ROME).astimezone(UTC)
    return round((end - start).total_seconds() / 3600)


def local_day(*, utc_time: str) -> date:
    """Return the Italian day of an hourly GMT timestamp such as 2026-07-01T22:00."""
    moment = datetime.fromisoformat(utc_time).replace(tzinfo=UTC)
    return moment.astimezone(ROME).date()


def daily_values(*, hourly: dict[str, Any]) -> DailyValues:
    """Return one value per Italian day and variable, or None when an hour of that day is missing."""
    hours = hourly["time"]
    days: dict[date, list[int]] = {}
    for index, stamp in enumerate(hours):
        days.setdefault(local_day(utc_time=stamp), []).append(index)
    result: DailyValues = {}
    for day, indexes in days.items():
        expected = hours_in_local_day(day=day)
        values: dict[str, float | None] = {}
        for hourly_name, column, how in DAILY_VARIABLES:
            series = hourly.get(hourly_name)
            picked = [series[index] for index in indexes] if series else []
            if len(picked) != expected or any(value is None for value in picked):
                values[column] = None
            elif how == "sum":
                values[column] = round(sum(picked), 4)
            else:
                values[column] = round(sum(picked) / len(picked), 4)
        result[day] = values
    return result


def window_dates(*, assessment_date: date, window_days: int) -> list[date]:
    """Return the full days ending the day before the assessment date, oldest first."""
    return [assessment_date - timedelta(days=offset) for offset in range(window_days, 0, -1)]


def check_before(*, days: list[date], assessment_date: date) -> None:
    """Raise if any day is on or after the assessment date."""
    late = [day for day in days if day >= assessment_date]
    if late:
        raise ValueError(
            f"Days {[day.isoformat() for day in late]} are not before {assessment_date.isoformat()}"
        )


def check_forecast(*, place: dict[str, Any], forecast: ForecastRun | None) -> ForecastRun:
    """Raise unless the forecast was published before the assessment day started in Italy."""
    if forecast is None:
        raise ValueError(f"No forecast for {place['record_id']}")
    start = day_start(day=place["assessment_date"])
    if forecast.published_at > start:
        raise ValueError(
            f"Forecast for {place['record_id']} was published at {forecast.published_at.isoformat()}, "
            f"after the assessment day started at {start.isoformat()}"
        )
    return forecast


def window_row(
    *,
    place: dict[str, Any],
    spec: ViewSpec,
    window_days: int,
    reconstructed_missing_days: int,
    daily_by_dataset: dict[str, dict[str, DailyValues]],
    forecast: ForecastRun | None = None,
) -> dict[str, Any]:
    """Return the totals of one place, view and window.

    With a forecast, the window ends the day before the target date. Days before the assessment date
    come from the archive and the later days come only from the forecast.
    """
    assessment_date: date = place["assessment_date"]
    target_date: date = place["target_date"]
    use_forecast = place["days_ahead"] > 0
    if use_forecast:
        forecast = check_forecast(place=place, forecast=forecast)
    days = window_dates(assessment_date=target_date, window_days=window_days)
    check_before(days=days, assessment_date=target_date)
    last_old_day = assessment_date - timedelta(days=1 + reconstructed_missing_days)
    chosen: list[dict[str, float | None]] = []
    model_days = 0
    forecast_days = 0
    for day in days:
        if day >= assessment_date:
            # These days come only from the stored forecast, never from the archive.
            if forecast is None or not use_forecast:
                raise ValueError(f"Day {day.isoformat()} is not before {assessment_date.isoformat()}")
            if day not in forecast.daily:
                raise ValueError(f"Forecast for {place['record_id']} has no values for {day.isoformat()}")
            forecast_days += 1
            chosen.append(forecast.daily[day])
            continue
        is_recent = day > last_old_day
        dataset = spec.recent_dataset if is_recent else spec.old_dataset
        model_days += int(spec.recent_is_model if is_recent else spec.old_is_model)
        # Archive days are looked up only before the assessment date.
        chosen.append(daily_by_dataset.get(dataset, {}).get(place["record_id"], {}).get(day, {}))
    row: dict[str, Any] = {
        "record_id": place["record_id"],
        "area": place["area"],
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "assessment_date": assessment_date.isoformat(),
        "target_date": target_date.isoformat(),
        "days_ahead": place["days_ahead"],
        "view": spec.name,
        "window_days": window_days,
        "source": spec.source,
        "dataset": spec.dataset,
        "value_kind": spec.value_kind,
    }
    for _, column, how in DAILY_VARIABLES:
        series = [values.get(column) for values in chosen]
        if any(value is None for value in series):
            row[column] = None
        elif how == "sum":
            row[column] = round(sum(series), 3)
        else:
            row[column] = round(sum(series) / len(series), 3)
    row["complete_days"] = sum(values.get("rain_mm") is not None for values in chosen)
    row["reconstructed_days"] = window_days - model_days - forecast_days
    row["model_days"] = model_days
    row["forecast_days"] = forecast_days
    row["forecast_model"] = forecast.model if use_forecast and forecast else None
    row["forecast_run_time"] = forecast.run_time.isoformat() if use_forecast and forecast else None
    row["forecast_published_at"] = forecast.published_at.isoformat() if use_forecast and forecast else None
    return row


def build_weather_features(
    *,
    places: list[dict[str, Any]],
    daily_by_dataset: dict[str, dict[str, DailyValues]],
    windows: tuple[int, ...] = DEFAULT_WINDOWS,
    reconstructed_missing_days: int,
    views: tuple[ViewSpec, ...] = DEFAULT_VIEWS,
    forecasts: dict[str, ForecastRun] | None = None,
) -> list[dict[str, Any]]:
    """Return one row per place, view and window, using only days before the assessment date.

    The daily values are already fetched, by dataset name and then place id. Places with days_ahead above 0
    get only the forecast view, and need a forecast published before the assessment day.
    """
    for place in places:
        days_ahead = place["days_ahead"]
        if not 0 <= days_ahead <= MAX_DAYS_AHEAD:
            raise ValueError(f"days_ahead {days_ahead} of {place['record_id']} is not between 0 and {MAX_DAYS_AHEAD}")
        if place["target_date"] != place["assessment_date"] + timedelta(days=days_ahead):
            raise ValueError(f"target_date of {place['record_id']} is not the assessment date plus days_ahead")
    cleaned: dict[str, dict[str, DailyValues]] = {}
    for dataset, by_place in daily_by_dataset.items():
        cleaned[dataset] = {}
        for place in places:
            days = by_place.get(place["record_id"], {})
            cleaned[dataset][place["record_id"]] = {
                day: values for day, values in days.items() if day < place["assessment_date"]
            }
    rows: list[dict[str, Any]] = []
    for place in places:
        forecast = (forecasts or {}).get(place["record_id"])
        specs = (FORECAST,) if place["days_ahead"] > 0 else views
        for spec in specs:
            for window_days in windows:
                rows.append(
                    window_row(
                        place=place,
                        spec=spec,
                        window_days=window_days,
                        reconstructed_missing_days=reconstructed_missing_days,
                        daily_by_dataset=cleaned,
                        forecast=forecast,
                    )
                )
    return rows


def forecast_value_rows(*, place: dict[str, Any], forecast: ForecastRun) -> list[dict[str, Any]]:
    """Return the stored forecast values for the 7 Italian days from the assessment date.

    Days without a full set of values are left out. Raises if the forecast was published too late.
    """
    check_forecast(place=place, forecast=forecast)
    published_day = forecast.published_at.astimezone(ROME).date()
    rows: list[dict[str, Any]] = []
    for offset in range(MAX_DAYS_AHEAD):
        day = place["assessment_date"] + timedelta(days=offset)
        values = forecast.daily.get(day)
        if not values or any(values.get(column) is None for column in VALUE_COLUMNS):
            continue
        rows.append(
            {
                "record_id": place["record_id"],
                "area": place["area"],
                "assessment_date": place["assessment_date"].isoformat(),
                "forecast_date": day.isoformat(),
                "days_ahead": (day - published_day).days,
                "model": forecast.model,
                "run_time": forecast.run_time.isoformat(),
                "published_at": forecast.published_at.isoformat(),
                **{column: values[column] for column in VALUE_COLUMNS},
            }
        )
    return rows


def fetch_daily_values(
    *, places: list[dict[str, Any]], client: Any, windows: tuple[int, ...], reconstructed_missing_days: int
) -> dict[str, dict[str, DailyValues]]:
    """Fetch the archive for every place. Never ask for a UTC date on or after the assessment date."""
    longest = max(windows)
    result: dict[str, dict[str, DailyValues]] = {ERA5: {}, IFS: {}}
    for place in places:
        end = place["assessment_date"] - timedelta(days=1)
        starts = {
            ERA5: place["assessment_date"] - timedelta(days=longest + 1),
            IFS: place["assessment_date"] - timedelta(days=reconstructed_missing_days + 1),
        }
        for model, start in starts.items():
            if model == IFS and end < IFS_FIRST_DAY:
                result[model][place["record_id"]] = {}
                continue
            hourly = client.archive_hourly(
                model=model,
                latitude=place["latitude"],
                longitude=place["longitude"],
                start=start,
                end=end,
            )
            result[model][place["record_id"]] = daily_values(hourly=hourly)
    return result
