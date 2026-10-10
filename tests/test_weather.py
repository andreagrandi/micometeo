"""Offline tests for the P3a weather totals: day grouping, no later days, labels, cache and the run."""

import csv
import importlib.util
import json
import tomllib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from micometeo.context import RunContext
from micometeo.weather import openmeteo
from micometeo.weather.features import (
    DEFAULT_VIEWS,
    ERA5,
    IFS,
    build_weather_features,
    check_before,
    daily_values,
    fetch_daily_values,
    hours_in_local_day,
    local_day,
    window_dates,
)

ROOT = Path(__file__).resolve().parent.parent
ASSESSMENT = date(2026, 7, 10)
MISSING_DAYS = 6


def load_p3():
    spec = importlib.util.spec_from_file_location("p3_run", ROOT / "experiments" / "p3_weather" / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def hourly_series(*, start: date, end: date, rule) -> dict[str, Any]:
    """Return GMT hourly data from 00:00 of start to 23:00 of end, with values from rule(stamp)."""
    stamps = []
    moment = datetime(start.year, start.month, start.day, tzinfo=UTC)
    last = datetime(end.year, end.month, end.day, 23, tzinfo=UTC)
    while moment <= last:
        stamps.append(moment)
        moment += timedelta(hours=1)
    values = [rule(stamp) for stamp in stamps]
    return {
        "time": [stamp.strftime("%Y-%m-%dT%H:%M") for stamp in stamps],
        "precipitation": [value["rain"] for value in values],
        "temperature_2m": [value["temperature"] for value in values],
        "et0_fao_evapotranspiration": [0.1] * len(stamps),
        "soil_moisture_0_to_7cm": [0.3] * len(stamps),
        "soil_temperature_0_to_7cm": [12.0] * len(stamps),
    }


def place(*, assessment_date: date = ASSESSMENT) -> dict[str, Any]:
    return {
        "record_id": "find1",
        "area": "home",
        "latitude": 44.05,
        "longitude": 10.8,
        "assessment_date": assessment_date,
        "target_date": assessment_date,
        "days_ahead": 0,
    }


def trap_data() -> dict[str, dict[str, Any]]:
    """Hours on or after the assessment date are huge. In era5 the last 6 days are also huge."""
    day_a_starts = datetime(2026, 7, 9, 22, tzinfo=UTC)
    six_days_ago = datetime(2026, 7, 3, 22, tzinfo=UTC)

    def era5_rule(stamp: datetime) -> dict[str, float]:
        if stamp >= day_a_starts:
            return {"rain": 1000.0, "temperature": 99.0}
        if stamp >= six_days_ago:
            return {"rain": 500.0 / 24, "temperature": 50.0}
        return {"rain": 0.5, "temperature": 20.0}

    def ifs_rule(stamp: datetime) -> dict[str, float]:
        if stamp >= day_a_starts:
            return {"rain": 1000.0, "temperature": 99.0}
        return {"rain": 0.1, "temperature": 18.0}

    return {
        ERA5: hourly_series(start=date(2026, 6, 9), end=date(2026, 7, 10), rule=era5_rule),
        IFS: hourly_series(start=date(2026, 7, 3), end=date(2026, 7, 10), rule=ifs_rule),
    }


def trap_rows() -> list[dict[str, Any]]:
    daily = {model: {"find1": daily_values(hourly=hourly)} for model, hourly in trap_data().items()}
    return build_weather_features(
        places=[place()], daily_by_dataset=daily, reconstructed_missing_days=MISSING_DAYS
    )


def pick(rows: list[dict[str, Any]], *, view: str, window: int) -> dict[str, Any]:
    return next(row for row in rows if row["view"] == view and row["window_days"] == window)


def test_look_back_totals_match_hand_sums_and_ignore_later_days() -> None:
    rows = trap_rows()
    # The last 6 days before the assessment date hold 500 mm each. Older days hold 12 mm each.
    seven = pick(rows, view="look_back", window=7)
    assert seven["rain_mm"] == pytest.approx(12.0 + 6 * 500.0, abs=0.01)
    assert seven["mean_temperature_c"] == pytest.approx((20.0 + 6 * 50.0) / 7, abs=0.01)
    thirty = pick(rows, view="look_back", window=30)
    assert thirty["rain_mm"] == pytest.approx(24 * 12.0 + 6 * 500.0, abs=0.01)
    assert thirty["complete_days"] == 30
    # A day on or after the assessment date would add 24000 mm and raise the temperature above 50.
    assert all(row["mean_temperature_c"] <= 50.0 for row in rows)


def test_on_the_morning_never_uses_the_500_mm_days() -> None:
    rows = trap_rows()
    morning = pick(rows, view="on_the_morning", window=7)
    # One reconstructed day at 12 mm and 6 model days at 2.4 mm each.
    assert morning["rain_mm"] == pytest.approx(12.0 + 6 * 2.4, abs=0.01)
    assert morning["model_days"] == 6
    assert morning["reconstructed_days"] == 1
    thirty = pick(rows, view="on_the_morning", window=30)
    assert thirty["rain_mm"] == pytest.approx(24 * 12.0 + 6 * 2.4, abs=0.01)
    assert all(row["rain_mm"] < 500 for row in rows if row["view"] == "on_the_morning")


def test_guard_raises_when_a_window_would_include_the_assessment_day() -> None:
    days = window_dates(assessment_date=ASSESSMENT, window_days=7)
    assert days[-1] == date(2026, 7, 9)
    check_before(days=days, assessment_date=ASSESSMENT)
    with pytest.raises(ValueError):
        check_before(days=[*days, ASSESSMENT], assessment_date=ASSESSMENT)


def test_data_dated_on_or_after_the_assessment_day_is_dropped() -> None:
    daily = {model: {"find1": daily_values(hourly=hourly)} for model, hourly in trap_data().items()}
    assert max(daily[ERA5]["find1"]) >= ASSESSMENT
    with_late_day = build_weather_features(
        places=[place()], daily_by_dataset=daily, reconstructed_missing_days=MISSING_DAYS
    )
    assert pick(with_late_day, view="look_back", window=7)["rain_mm"] == pytest.approx(12.0 + 6 * 500.0, abs=0.01)
    assert all(row["rain_mm"] < 1000 for row in with_late_day if row["view"] == "on_the_morning")


def test_summer_time_end_day_has_25_hours_and_needs_all_of_them() -> None:
    assert hours_in_local_day(day=date(2026, 10, 25)) == 25
    assert hours_in_local_day(day=date(2026, 3, 29)) == 23
    assert hours_in_local_day(day=date(2026, 10, 24)) == 24
    # Local 25 October runs from 22:00 UTC on 24 October to 23:00 UTC on 25 October.
    hourly = hourly_series(start=date(2026, 10, 24), end=date(2026, 10, 26), rule=lambda s: {"rain": 1.0, "temperature": 10.0})
    assert daily_values(hourly=hourly)[date(2026, 10, 25)]["rain_mm"] == 25.0
    hourly["precipitation"][hourly["time"].index("2026-10-25T05:00")] = None
    assert daily_values(hourly=hourly)[date(2026, 10, 25)]["rain_mm"] is None
    cut = hourly["time"].index("2026-10-25T05:00")
    gap = {key: [*value[:cut], *value[cut + 1 :]] for key, value in hourly.items()}
    assert daily_values(hourly=gap)[date(2026, 10, 25)]["mean_temperature_c"] is None


def test_a_day_with_one_missing_hour_makes_the_window_value_missing() -> None:
    hourly = trap_data()
    hourly[ERA5]["precipitation"][hourly[ERA5]["time"].index("2026-07-05T10:00")] = None
    daily = {model: {"find1": daily_values(hourly=data)} for model, data in hourly.items()}
    rows = build_weather_features(places=[place()], daily_by_dataset=daily, reconstructed_missing_days=MISSING_DAYS)
    assert pick(rows, view="look_back", window=7)["rain_mm"] is None
    assert pick(rows, view="look_back", window=7)["complete_days"] == 6
    assert pick(rows, view="look_back", window=7)["mean_temperature_c"] is not None
    assert pick(rows, view="look_back", window=14)["rain_mm"] is None
    # The model days do not use era5, so the morning view is not hurt.
    assert pick(rows, view="on_the_morning", window=7)["rain_mm"] is not None


def test_a_day_missing_from_the_recent_dataset_is_not_filled_from_era5() -> None:
    hourly = trap_data()
    hourly[IFS]["precipitation"][hourly[IFS]["time"].index("2026-07-08T10:00")] = None
    daily = {model: {"find1": daily_values(hourly=data)} for model, data in hourly.items()}
    rows = build_weather_features(places=[place()], daily_by_dataset=daily, reconstructed_missing_days=MISSING_DAYS)
    assert pick(rows, view="on_the_morning", window=7)["rain_mm"] is None
    assert pick(rows, view="look_back", window=7)["rain_mm"] is not None


def test_hour_at_22_utc_on_the_day_before_falls_on_the_assessment_day_in_summer() -> None:
    assert local_day(utc_time="2026-07-09T22:00") == ASSESSMENT
    assert local_day(utc_time="2026-07-09T21:00") == date(2026, 7, 9)
    assert local_day(utc_time="2026-01-09T22:00") == date(2026, 1, 9)
    daily = daily_values(hourly=trap_data()[ERA5])
    assert ASSESSMENT in daily
    rows = trap_rows()
    assert pick(rows, view="look_back", window=7)["rain_mm"] == pytest.approx(12.0 + 6 * 500.0, abs=0.01)


def test_labels_never_say_forecast_and_look_back_says_reconstructed_past_weather() -> None:
    rows = trap_rows()
    assert {row["view"] for row in rows} == {"look_back", "on_the_morning"}
    for row in rows:
        assert "forecast" not in row["value_kind"].lower()
        assert row["days_ahead"] == 0
        assert row["assessment_date"] == row["target_date"] == "2026-07-10"
    for row in rows:
        if row["view"] == "look_back":
            assert row["value_kind"] == "reconstructed past weather"
            assert row["source"] == "Open-Meteo Historical Weather API"
            assert row["dataset"] == "era5_seamless"
    assert len(rows) == len(DEFAULT_VIEWS) * 3


def test_quota_weight_counts_many_variables_and_many_days() -> None:
    assert openmeteo.quota_weight(variables=5, days=14) == 1.0
    assert openmeteo.quota_weight(variables=5, days=32) == pytest.approx(32 / 14)
    assert openmeteo.quota_weight(variables=20, days=14) == 2.0
    assert openmeteo.quota_weight(variables=20, days=28) == 4.0


def fake_answer(url_text: str) -> dict[str, Any]:
    return {"hourly": hourly_series(start=date(2026, 1, 1), end=date(2026, 1, 3), rule=lambda s: {"rain": 0.0, "temperature": 5.0})}


def test_second_call_reads_the_cache_and_makes_no_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_get_json(*, url: str) -> dict[str, Any]:
        calls.append(url)
        return fake_answer(url)

    monkeypatch.setattr(openmeteo, "get_json", fake_get_json)
    arguments = {"model": ERA5, "latitude": 44.05001, "longitude": 10.80004, "start": date(2026, 1, 1), "end": date(2026, 1, 3)}
    first = openmeteo.OpenMeteo(cache_dir=tmp_path, pause_seconds=0)
    first.archive_hourly(**arguments)
    assert first.metrics.requests == 1
    assert first.metrics.quota_calls == 1.0
    cached = tmp_path / ERA5 / "44.0500_10.8000_2026-01-01_2026-01-03.json"
    assert cached.exists()
    second = openmeteo.OpenMeteo(cache_dir=tmp_path, pause_seconds=0)
    second.archive_hourly(**arguments)
    assert len(calls) == 1
    assert second.metrics.requests == 0
    assert second.metrics.cache_hits == 1


def test_requests_retry_after_a_server_error_and_stop_on_an_error_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    monkeypatch.setattr(openmeteo.time, "sleep", lambda seconds: None)
    outcomes = [urllib.error.HTTPError("u", 429, "slow down", {}, None), OSError("down"), {"hourly": {"time": []}}]

    def flaky(*, url: str) -> dict[str, Any]:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(openmeteo, "get_json", flaky)
    client = openmeteo.OpenMeteo(cache_dir=None, pause_seconds=0)
    hourly = client.archive_hourly(model=ERA5, latitude=1, longitude=2, start=date(2026, 1, 1), end=date(2026, 1, 2))
    assert hourly == {"time": []}
    monkeypatch.setattr(openmeteo, "get_json", lambda *, url: {"error": True, "reason": "end_date is too late"})
    with pytest.raises(RuntimeError):
        client.archive_hourly(model=ERA5, latitude=1, longitude=2, start=date(2026, 1, 1), end=date(2026, 1, 2))


def test_fetch_asks_only_for_utc_dates_before_the_assessment_date() -> None:
    asked: list[tuple[str, date, date]] = []

    class Client:
        def archive_hourly(self, *, model: str, latitude: float, longitude: float, start: date, end: date) -> dict[str, Any]:
            asked.append((model, start, end))
            return hourly_series(start=start, end=end, rule=lambda s: {"rain": 0.0, "temperature": 1.0})

    fetch_daily_values(places=[place()], client=Client(), windows=(7, 14, 30), reconstructed_missing_days=6)
    assert asked == [
        (ERA5, date(2026, 6, 9), date(2026, 7, 9)),
        (IFS, date(2026, 7, 3), date(2026, 7, 9)),
    ]


def test_fetch_skips_ecmwf_ifs_before_2017_and_keeps_it_when_the_window_reaches_2017() -> None:
    asked: list[tuple[str, date, date]] = []

    class Client:
        def archive_hourly(self, *, model: str, latitude: float, longitude: float, start: date, end: date) -> dict[str, Any]:
            asked.append((model, start, end))
            return hourly_series(start=start, end=end, rule=lambda s: {"rain": 0.0, "temperature": 1.0})

    daily = fetch_daily_values(
        places=[place(assessment_date=date(2016, 9, 30))], client=Client(), windows=(7,), reconstructed_missing_days=6
    )
    assert [model for model, _, _ in asked] == [ERA5]
    assert daily[IFS]["find1"] == {}
    rows = build_weather_features(
        places=[place(assessment_date=date(2016, 9, 30))], daily_by_dataset=daily, windows=(7,), reconstructed_missing_days=6
    )
    morning = [row for row in rows if row["view"] == "on_the_morning"][0]
    assert morning["rain_mm"] is None

    asked.clear()
    fetch_daily_values(
        places=[place(assessment_date=date(2017, 1, 2))], client=Client(), windows=(7,), reconstructed_missing_days=6
    )
    assert (IFS, date(2016, 12, 26), date(2017, 1, 1)) in asked


def write_finds(*, path: Path) -> None:
    rows = []
    for number in range(3):
        rows.append({"record_id": f"h{number}", "area": "home", "event_date": f"2026-0{number + 5}-15", "latitude": 44.0 + number * 0.1, "longitude": 10.8})
    for number in range(6):
        rows.append({"record_id": f"c{number}", "area": "comparison", "event_date": "2026-06-20", "latitude": 46.5 + number * 0.1, "longitude": 8.0})
    pq.write_table(pa.Table.from_pylist(rows), path)


@pytest.fixture
def finished_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    config = tomllib.loads((ROOT / "experiments" / "p3_weather" / "config.toml").read_text(encoding="utf-8"))
    settings = config["settings"]
    settings["finds_path"] = str(tmp_path / "finds.parquet")
    settings["comparison_sample"] = 2
    settings["pause_seconds"] = 0
    settings["reports_dir"] = str(tmp_path / "reports")
    write_finds(path=tmp_path / "finds.parquet")
    calls: list[str] = []

    def fake_get_json(*, url: str) -> dict[str, Any]:
        calls.append(url)
        query = dict(part.split("=") for part in url.split("?")[1].split("&"))
        if "past_days" in query:
            end = datetime.now(UTC).date()
            start = end - timedelta(days=int(query["past_days"]))
        else:
            start, end = date.fromisoformat(query["start_date"]), date.fromisoformat(query["end_date"])
        return {"hourly": hourly_series(start=start, end=end, rule=lambda s: {"rain": 0.25, "temperature": 15.0})}

    monkeypatch.setattr(openmeteo, "get_json", fake_get_json)
    state_path = tmp_path / "state.json"

    def do_run(name: str) -> RunContext:
        context = RunContext(
            config=settings,
            seed=42,
            run_id=name,
            raw_dir=tmp_path / "raw",
            output_dir=tmp_path / name,
            state_path=state_path,
        )
        load_p3().run(context)
        return context

    do_run("first")
    first_calls = len(calls)
    do_run("second")
    return {"tmp_path": tmp_path, "calls": calls, "first_calls": first_calls, "state": json.loads(state_path.read_text(encoding="utf-8"))}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_run_writes_windows_for_every_place_view_and_window(finished_run: dict[str, Any]) -> None:
    rows = pq.read_table(finished_run["tmp_path"] / "second" / "weather_windows.parquet").to_pylist()
    assert len(rows) == 5 * 2 * 3
    assert {row["area"] for row in rows} == {"home", "comparison"}
    seven = [row for row in rows if row["view"] == "look_back" and row["window_days"] == 7]
    assert all(row["rain_mm"] == pytest.approx(7 * 24 * 0.25) for row in seven)
    assert all(row["assessment_date"] == row["target_date"] for row in rows)
    assert sum(1 for output in finished_run["state"]["outputs"] if output.endswith("weather_windows.parquet")) == 1


def test_run_makes_no_sample_request_the_second_time(finished_run: dict[str, Any]) -> None:
    metrics = {row["scope"]: row for row in read_csv(finished_run["tmp_path"] / "reports" / "p3_metrics.csv")}
    assert metrics["sample"]["requests"] == "0"
    assert int(metrics["sample"]["cache_hits"]) == 10
    assert metrics["sample"]["places"] == "5"
    assert int(metrics["checks"]["requests"]) > 0


def test_run_writes_delay_summary_and_today_files(finished_run: dict[str, Any]) -> None:
    reports = finished_run["tmp_path"] / "reports"
    delays = read_csv(reports / "p3_delays.csv")
    assert [row["dataset"] for row in delays] == ["era5_seamless", "era5", "ecmwf_ifs", "best_match past_days"]
    assert all(row["days_missing_before_today"] == "0" for row in delays)
    summary = read_csv(reports / "p3_summary.csv")
    assert {row["area"] for row in summary} == {"home", "comparison", "all"}
    assert all(row["places_with_complete_rain"] == row["places"] for row in summary)
    differences = read_csv(reports / "p3_view_differences.csv")
    assert all(float(row["p90_abs_rain_difference_mm"]) == 0.0 for row in differences)
    today = read_csv(reports / "p3_today_check.csv")
    assert len(today) == 4 * 3 * 2
    assert {row["source"] for row in today} == {"Open-Meteo Forecast API", "Open-Meteo Historical Weather API"}
    assert all("forecast" not in row["value_kind"].lower() for row in today)
    assert {source["name"] for source in finished_run["state"]["sources"]} >= {
        "Open-Meteo Historical Weather API",
        "Open-Meteo Forecast API",
    }


def test_forecast_api_view_counts_every_day_as_model_values() -> None:
    from micometeo.weather.features import ON_THE_MORNING_FROM_FORECAST_API

    hourly = hourly_series(start=date(2026, 6, 9), end=date(2026, 7, 10), rule=lambda s: {"rain": 1.0, "temperature": 10.0})
    rows = build_weather_features(
        places=[place()],
        daily_by_dataset={"best_match_past_days": {"find1": daily_values(hourly=hourly)}},
        windows=(7,),
        reconstructed_missing_days=MISSING_DAYS,
        views=(ON_THE_MORNING_FROM_FORECAST_API,),
    )
    assert rows[0]["model_days"] == 7
    assert rows[0]["reconstructed_days"] == 0
    assert rows[0]["rain_mm"] == 7 * 24
    assert rows[0]["value_kind"] == "model values for past hours"
