"""Offline tests for forecasts published in the past: no later archive days, run choice and the run cache."""

import csv
import importlib.util
import io
import json
import tomllib
import urllib.error
import urllib.parse
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from micometeo.context import RunContext
from micometeo.weather import openmeteo
from micometeo.weather.features import (
    ERA5,
    FORECAST_MODEL,
    FORECAST_VALUE_COLUMNS,
    IFS,
    OUTPUT_COLUMNS,
    ForecastRun,
    build_weather_features,
    daily_values,
    day_start,
    forecast_value_rows,
    latest_run_before,
)
from tests.test_weather import ASSESSMENT, MISSING_DAYS, hourly_series, place, pick

ROOT = Path(__file__).resolve().parent.parent
TRAP_MM = 9999.0
RUN_TIME = datetime(2026, 7, 9, 12, tzinfo=UTC)
PUBLISHED = RUN_TIME + timedelta(hours=6)


def forecast_place(*, days_ahead: int) -> dict[str, Any]:
    found = place()
    found["days_ahead"] = days_ahead
    found["target_date"] = ASSESSMENT + timedelta(days=days_ahead)
    return found


def archive_daily() -> dict[str, dict[str, Any]]:
    """Return 1 mm an hour in era5 and 2 mm an hour in ecmwf_ifs before the assessment day, traps from then on."""
    start_of_a = datetime(2026, 7, 9, 22, tzinfo=UTC)

    def rule(normal: float):
        def inner(stamp: datetime) -> dict[str, float]:
            if stamp >= start_of_a:
                return {"rain": TRAP_MM, "temperature": 99.0}
            return {"rain": normal, "temperature": 10.0}

        return inner

    return {
        ERA5: {"find1": daily_values(hourly=hourly_series(start=date(2026, 6, 1), end=date(2026, 7, 16), rule=rule(1.0)))},
        IFS: {"find1": daily_values(hourly=hourly_series(start=date(2026, 6, 1), end=date(2026, 7, 16), rule=rule(2.0)))},
    }


def make_forecast(*, published_at: datetime = PUBLISHED, skip: date | None = None) -> ForecastRun:
    """Return a run with 3 mm an hour and 20 degrees for the Italian days 10 to 15 July."""
    hourly = hourly_series(start=date(2026, 7, 9), end=date(2026, 7, 16), rule=lambda s: {"rain": 3.0, "temperature": 20.0})
    daily = daily_values(hourly=hourly)
    daily = {day: values for day, values in daily.items() if day != skip}
    return ForecastRun(model=FORECAST_MODEL, run_time=RUN_TIME, published_at=published_at, daily=daily)


def build(*, days_ahead: int, forecast: ForecastRun | None, windows: tuple[int, ...] = (7, 14)) -> list[dict[str, Any]]:
    return build_weather_features(
        places=[forecast_place(days_ahead=days_ahead)],
        daily_by_dataset=archive_daily(),
        windows=windows,
        reconstructed_missing_days=MISSING_DAYS,
        forecasts={"find1": forecast} if forecast else None,
    )


def test_missing_forecast_raises_and_never_falls_back_to_the_archive() -> None:
    with pytest.raises(ValueError, match="No forecast"):
        build(days_ahead=3, forecast=None)


def test_forecast_published_after_the_assessment_day_started_raises() -> None:
    cutoff = day_start(day=ASSESSMENT)
    assert cutoff == datetime(2026, 7, 9, 22, tzinfo=UTC)
    build(days_ahead=3, forecast=make_forecast(published_at=cutoff))
    with pytest.raises(ValueError, match="published"):
        build(days_ahead=3, forecast=make_forecast(published_at=cutoff + timedelta(minutes=1)))


def test_forecast_missing_a_day_before_the_target_raises() -> None:
    with pytest.raises(ValueError, match="2026-07-11"):
        build(days_ahead=3, forecast=make_forecast(skip=date(2026, 7, 11)))
    # A missing day after the window is not needed.
    build(days_ahead=3, forecast=make_forecast(skip=date(2026, 7, 14)))


def test_window_is_past_archive_days_plus_forecast_days_and_never_a_trap_value() -> None:
    rows = build(days_ahead=3, forecast=make_forecast())
    assert {row["view"] for row in rows} == {"forecast"}
    seven = pick(rows, view="forecast", window=7)
    # Window is 6 to 12 July. Days 6 to 9 are ecmwf_ifs at 48 mm, days 10 to 12 are the forecast at 72 mm.
    assert seven["rain_mm"] == pytest.approx(4 * 48.0 + 3 * 72.0)
    assert seven["mean_temperature_c"] == pytest.approx((4 * 10.0 + 3 * 20.0) / 7, abs=0.01)
    assert (seven["reconstructed_days"], seven["model_days"], seven["forecast_days"]) == (0, 4, 3)
    fourteen = pick(rows, view="forecast", window=14)
    # Window is 29 June to 12 July. 29 June to 3 July are era5 at 24 mm, 4 to 9 July are ecmwf_ifs.
    assert fourteen["rain_mm"] == pytest.approx(5 * 24.0 + 6 * 48.0 + 3 * 72.0)
    assert (fourteen["reconstructed_days"], fourteen["model_days"], fourteen["forecast_days"]) == (5, 6, 3)
    for row in rows:
        assert row["reconstructed_days"] + row["model_days"] + row["forecast_days"] == row["window_days"]
        assert row["rain_mm"] < TRAP_MM and row["mean_temperature_c"] < 99.0
        assert row["complete_days"] == row["window_days"]
        assert row["assessment_date"] == "2026-07-10"
        assert row["target_date"] == "2026-07-13"
        assert row["days_ahead"] == 3
        assert row["forecast_model"] == FORECAST_MODEL
        assert row["forecast_run_time"] == RUN_TIME.isoformat()
        assert row["forecast_published_at"] == PUBLISHED.isoformat()
        assert set(row) == set(OUTPUT_COLUMNS)


def test_forecast_values_are_used_even_when_the_archive_holds_values_for_those_days() -> None:
    # The archive has trap values on 10 to 12 July. Only the forecast may supply them.
    daily = archive_daily()
    assert daily[ERA5]["find1"][date(2026, 7, 11)]["rain_mm"] == 24 * TRAP_MM
    rows = build(days_ahead=7, forecast=make_forecast(), windows=(7,))
    assert rows[0]["rain_mm"] == pytest.approx(7 * 72.0)
    assert (rows[0]["reconstructed_days"], rows[0]["model_days"], rows[0]["forecast_days"]) == (0, 0, 7)


def test_days_ahead_one_uses_only_the_day_of_the_assessment_from_the_forecast() -> None:
    rows = build(days_ahead=1, forecast=make_forecast(), windows=(7,))
    assert rows[0]["rain_mm"] == pytest.approx(6 * 48.0 + 72.0)
    assert rows[0]["forecast_days"] == 1


def test_days_ahead_zero_rows_carry_empty_forecast_columns() -> None:
    rows = build(days_ahead=0, forecast=None, windows=(7,))
    assert {row["view"] for row in rows} == {"look_back", "on_the_morning"}
    for row in rows:
        assert row["forecast_days"] == 0
        assert row["forecast_model"] is None
        assert row["forecast_run_time"] is None
        assert row["forecast_published_at"] is None
        assert row["rain_mm"] < TRAP_MM


def test_days_ahead_outside_zero_to_seven_and_wrong_target_date_raise() -> None:
    for days_ahead in (8, -1):
        with pytest.raises(ValueError, match="days_ahead"):
            build(days_ahead=days_ahead, forecast=make_forecast())
    wrong = forecast_place(days_ahead=3)
    wrong["target_date"] = ASSESSMENT + timedelta(days=2)
    with pytest.raises(ValueError, match="target_date"):
        build_weather_features(
            places=[wrong],
            daily_by_dataset=archive_daily(),
            reconstructed_missing_days=MISSING_DAYS,
            forecasts={"find1": make_forecast()},
        )


@pytest.mark.parametrize("assessment", [date(2026, 1, 15), date(2026, 7, 15)])
def test_latest_run_is_the_12_utc_run_of_the_day_before(assessment: date) -> None:
    run = latest_run_before(assessment_date=assessment, publication_delay_hours=6)
    assert run == datetime.combine(assessment - timedelta(days=1), datetime.min.time(), tzinfo=UTC).replace(hour=12)


@pytest.mark.parametrize("assessment", [date(2026, 1, 15), date(2026, 7, 15)])
def test_a_longer_delay_picks_the_00_utc_run_of_the_day_before(assessment: date) -> None:
    run = latest_run_before(assessment_date=assessment, publication_delay_hours=13)
    assert run == datetime.combine(assessment - timedelta(days=1), datetime.min.time(), tzinfo=UTC)


def test_forecast_value_rows_set_days_ahead_from_the_published_day() -> None:
    forecast = make_forecast()
    rows = forecast_value_rows(place=forecast_place(days_ahead=3), forecast=forecast)
    assert [row["forecast_date"] for row in rows] == [f"2026-07-{day}" for day in range(10, 17)]
    assert [row["days_ahead"] for row in rows] == [1, 2, 3, 4, 5, 6, 7]
    for row in rows:
        assert set(row) == set(FORECAST_VALUE_COLUMNS)
        assert row["model"] == FORECAST_MODEL
        assert row["published_at"] == PUBLISHED.isoformat()
        assert row["run_time"] == RUN_TIME.isoformat()
        assert row["rain_mm"] == 72.0
    # A run published after the assessment day started is never stored.
    late = make_forecast(published_at=datetime(2026, 7, 10, 3, tzinfo=UTC))
    with pytest.raises(ValueError, match="after the assessment day started"):
        forecast_value_rows(place=forecast_place(days_ahead=3), forecast=late)


def test_forecast_value_rows_skip_days_without_complete_values() -> None:
    forecast = make_forecast(skip=date(2026, 7, 12))
    rows = forecast_value_rows(place=forecast_place(days_ahead=3), forecast=forecast)
    assert "2026-07-12" not in [row["forecast_date"] for row in rows]


def refusal(*, reason: str, code: int = 400) -> urllib.error.HTTPError:
    body = io.BytesIO(json.dumps({"error": True, "reason": reason}).encode())
    return urllib.error.HTTPError("u", code, "Bad Request", {}, body)


def test_single_run_hourly_keeps_00_and_12_utc_apart_returns_none_on_400_and_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    urls: list[str] = []

    def fake_get_json(*, url: str) -> dict[str, Any]:
        urls.append(url)
        if "run=2026-07-09T00%3A00" in url:
            raise refusal(reason="The requested model run is not available for this model")
        return {"hourly": {"time": ["2026-07-09T12:00"], "precipitation": [1.0]}}

    monkeypatch.setattr(openmeteo, "get_json", fake_get_json)
    client = openmeteo.OpenMeteo(cache_dir=tmp_path, pause_seconds=0)
    arguments = {"model": FORECAST_MODEL, "latitude": 44.05, "longitude": 10.8, "forecast_days": 10}
    night = client.single_run_hourly(run_time=datetime(2026, 7, 9, 0, tzinfo=UTC), **arguments)
    noon = client.single_run_hourly(run_time=datetime(2026, 7, 9, 12, tzinfo=UTC), **arguments)
    assert night is None
    assert noon == {"time": ["2026-07-09T12:00"], "precipitation": [1.0]}
    assert len(urls) == 2
    assert "run=2026-07-09T12%3A00" in urls[1]
    assert "forecast_days=10" in urls[1]
    assert "single-runs-api" in urls[1]
    files = sorted(path.name for path in (tmp_path / f"single_runs_{FORECAST_MODEL}").iterdir())
    assert files == ["44.0500_10.8000_2026-07-09T1200_10d.json"]
    assert client.metrics.quota_calls == pytest.approx(2 * openmeteo.quota_weight(variables=5, days=10))
    again = client.single_run_hourly(run_time=datetime(2026, 7, 9, 12, tzinfo=UTC), **arguments)
    assert again == noon
    assert len(urls) == 2
    assert client.metrics.cache_hits == 1


def test_single_run_hourly_raises_on_other_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    client = openmeteo.OpenMeteo(cache_dir=None, pause_seconds=0, attempts=1)
    arguments = {"model": FORECAST_MODEL, "latitude": 1.0, "longitude": 2.0, "run_time": RUN_TIME, "forecast_days": 10}
    monkeypatch.setattr(openmeteo, "get_json", lambda *, url: (_ for _ in ()).throw(refusal(reason="x", code=500)))
    with pytest.raises(urllib.error.HTTPError):
        client.single_run_hourly(**arguments)
    monkeypatch.setattr(openmeteo, "get_json", lambda *, url: (_ for _ in ()).throw(refusal(reason="Cannot parse")))
    with pytest.raises(RuntimeError):
        client.single_run_hourly(**arguments)


def test_probe_returns_the_error_answer_for_400_and_caches_both_answers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    urls: list[str] = []

    def fake_get_json(*, url: str) -> dict[str, Any]:
        urls.append(url)
        if "start_date=2010-01-01" in url:
            raise refusal(reason="out of range")
        return {"hourly": {"time": []}}

    monkeypatch.setattr(openmeteo, "get_json", fake_get_json)
    client = openmeteo.OpenMeteo(cache_dir=tmp_path, pause_seconds=0)
    old_day, new_day = "2010-01-01", "2020-01-01"
    query = {"hourly": "precipitation", "start_date": old_day, "end_date": old_day}
    bad = client.probe(url=openmeteo.PREVIOUS_RUNS_URL, query=query, cache_key=f"previous_{old_day}")
    assert bad == {"error": True, "reason": "out of range"}
    good = client.probe(url=openmeteo.PREVIOUS_RUNS_URL, query={**query, "start_date": new_day}, cache_key=f"previous_{new_day}")
    assert good == {"hourly": {"time": []}}
    client.probe(url=openmeteo.PREVIOUS_RUNS_URL, query=query, cache_key=f"previous_{old_day}")
    assert len(urls) == 2
    assert client.metrics.cache_hits == 1
    assert client.metrics.quota_calls == 2.0


def load_p3b():
    spec = importlib.util.spec_from_file_location("p3b_run", ROOT / "experiments" / "p3b_forecasts" / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_open_meteo(*, url: str) -> dict[str, Any]:
    """Answer all four hosts. Single runs start on 14 March 2024, the other sources in 2024 or 2022."""
    parsed = urllib.parse.urlparse(url)
    query = {key: values[0] for key, values in urllib.parse.parse_qs(parsed.query).items()}
    names = query["hourly"].split(",")
    host = parsed.netloc

    def answer(*, start: datetime, hours: int, first_day: datetime | None, null_first_hour: bool = False) -> dict[str, Any]:
        stamps = [start + timedelta(hours=hour) for hour in range(hours)]
        hourly: dict[str, Any] = {"time": [stamp.strftime("%Y-%m-%dT%H:%M") for stamp in stamps]}
        for name in names:
            missing = first_day is not None and start < first_day
            hourly[name] = [None if missing else 0.25 for _ in stamps]
            if null_first_hour and name == "precipitation":
                hourly[name][0] = None
        return {"hourly": hourly}

    if host.startswith("single-runs"):
        run = datetime.strptime(query["run"], "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
        if run < datetime(2024, 3, 14, tzinfo=UTC):
            raise refusal(reason="The requested model run is not available for this model")
        return answer(start=run, hours=int(query["forecast_days"]) * 24, first_day=None, null_first_hour=True)
    start = datetime.fromisoformat(query["start_date"]).replace(tzinfo=UTC)
    hours = ((date.fromisoformat(query["end_date"]) - date.fromisoformat(query["start_date"])).days + 1) * 24
    if host.startswith("previous-runs"):
        # Only forecasts up to 5 days ahead exist, from 2024.
        reply = answer(start=start, hours=hours, first_day=datetime(2024, 1, 1, tzinfo=UTC))
        for name in names:
            if int(name.split("_previous_day")[1]) > 5:
                reply["hourly"][name] = [None] * hours
        return reply
    if host.startswith("historical-forecast"):
        return answer(start=start, hours=hours, first_day=datetime(2022, 1, 1, tzinfo=UTC))
    return answer(start=start, hours=hours, first_day=None)


@pytest.fixture
def finished_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    config = tomllib.loads((ROOT / "experiments" / "p3b_forecasts" / "config.toml").read_text(encoding="utf-8"))
    settings = config["settings"]
    settings["finds_path"] = str(tmp_path / "finds.parquet")
    settings["comparison_sample"] = 2
    settings["pause_seconds"] = 0
    settings["survey_start"] = "2023-01-01"
    settings["reports_dir"] = str(tmp_path / "reports")
    finds = []
    for number, day in enumerate(["2025-05-15", "2025-06-15", "2024-09-10", "2023-09-10"]):
        finds.append({"record_id": f"h{number}", "area": "home", "event_date": day, "latitude": 44.0 + number * 0.1, "longitude": 10.8})
    for number, day in enumerate(["2025-06-20", "2025-07-20", "2024-10-01", "2024-02-01", "2025-08-01"]):
        finds.append({"record_id": f"c{number}", "area": "comparison", "event_date": day, "latitude": 46.5 + number * 0.1, "longitude": 8.0})
    pq.write_table(pa.Table.from_pylist(finds), tmp_path / "finds.parquet")
    monkeypatch.setattr(openmeteo, "get_json", fake_open_meteo)
    context = RunContext(
        config=settings,
        seed=42,
        run_id="first",
        raw_dir=tmp_path / "raw",
        output_dir=tmp_path / "first",
        state_path=tmp_path / "state.json",
    )
    load_p3b().run(context)
    return {"tmp_path": tmp_path, "state": json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_run_writes_forecast_rows_published_before_the_assessment_day(finished_run: dict[str, Any]) -> None:
    rows = pq.read_table(finished_run["tmp_path"] / "first" / "weather_windows.parquet").to_pylist()
    forecast_rows = [row for row in rows if row["view"] == "forecast"]
    assert {row["days_ahead"] for row in rows} == {0, 1, 3, 7}
    assert {row["view"] for row in rows if row["days_ahead"] == 0} == {"look_back"}
    # The 2023 find and the February 2024 find have no stored run, so they are not in the sample.
    assert {row["record_id"] for row in rows}.isdisjoint({"h3", "c3"})
    assert forecast_rows
    for row in forecast_rows:
        published = datetime.fromisoformat(row["forecast_published_at"])
        assert published <= day_start(day=date.fromisoformat(row["assessment_date"]))
        assert row["forecast_days"] == row["days_ahead"]
        assert row["reconstructed_days"] + row["model_days"] + row["forecast_days"] == row["window_days"]
        assert row["rain_mm"] == pytest.approx(row["window_days"] * 24 * 0.25)
    values = pq.read_table(finished_run["tmp_path"] / "first" / "forecast_values.parquet").to_pylist()
    assert values
    assert all(datetime.fromisoformat(v["published_at"]).date() < date.fromisoformat(v["assessment_date"]) for v in values)
    assert {output.rsplit("/", 1)[-1] for output in finished_run["state"]["outputs"]} >= {
        "weather_windows.parquet",
        "forecast_values.parquet",
        "p3b_forecast_sources.csv",
        "p3b_testable_finds.csv",
        "p3b_forecast_rain.csv",
        "p3b_metrics.csv",
    }


def test_run_writes_survey_testable_rain_and_metric_files(finished_run: dict[str, Any]) -> None:
    reports = finished_run["tmp_path"] / "reports"
    survey = read_csv(reports / "p3b_forecast_sources.csv")
    assert {row["api"] for row in survey} == {"previous_runs", "single_runs", "historical_forecast"}
    single = next(row for row in survey if row["api"] == "single_runs" and row["model"] == "ecmwf_ifs")
    assert single["first_day"] == "2024-03-14"
    assert single["run_time_known"] == "True"
    assert float(single["max_days_ahead"]) == 16.0
    previous = next(row for row in survey if row["api"] == "previous_runs" and row["model"] == "best_match")
    assert previous["first_day"] == "2024-01-01"
    assert previous["max_days_ahead"] == "5"
    assert "precipitation_previous_day1" in previous["variables"].split()
    historical = next(row for row in survey if row["api"] == "historical_forecast" and row["model"] == "ecmwf_ifs")
    assert historical["first_day"] == "2023-01-01"
    assert historical["max_days_ahead"] == "0"
    testable = {(row["area"], row["year"]): row for row in read_csv(reports / "p3b_testable_finds.csv")}
    assert testable[("home", "all")]["finds"] == "4"
    assert testable[("comparison", "all")]["finds"] == "5"
    assert testable[("all", "all")]["finds"] == "9"
    assert testable[("home", "2023")]["testable_7_days_ahead_single_runs"] == "0"
    assert testable[("home", "2025")]["testable_7_days_ahead_single_runs"] == "2"
    assert testable[("all", "all")]["testable_7_days_ahead_single_runs"] == "7"
    rain = read_csv(reports / "p3b_forecast_rain.csv")
    assert {row["period"] for row in rain} == {"forecast days", "single day", "window 7", "window 14", "window 30"}
    assert {row["area"] for row in rain} == {"home", "comparison", "all"}
    assert all(float(row["mean_difference_mm"]) == 0.0 for row in rain)
    assert {row["days_ahead"] for row in rain if row["period"] == "single day"} == {"1", "2", "3", "4", "5", "6", "7"}
    metrics = {row["scope"]: row for row in read_csv(reports / "p3b_metrics.csv")}
    assert set(metrics) == {"survey", "sample"}
    assert int(metrics["survey"]["requests"]) > 0
    assert int(metrics["sample"]["requests"]) > 0
