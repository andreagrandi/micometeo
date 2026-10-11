"""Offline checks of the helpers of the Bielefeld rule check, on synthetic days."""

import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("p4b_bielefeld_run", ROOT / "experiments" / "p4b_bielefeld" / "run.py")
biel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(biel)


def weather_for(*, size: int, rain: list[float] | None = None) -> dict[str, np.ndarray]:
    values = {name: np.ones(size) for name in ["rain_7d_mm", "rain_14d_mm", "rain_30d_mm", "temp_7d_c", "temp_14d_c", "temp_30d_c"]}
    if rain is not None:
        values["rain_30d_mm"] = np.array(rain, dtype=float)
    return values


def test_season_mask_keeps_both_end_days_in_every_year() -> None:
    dates = np.array(["2015-08-04", "2015-08-05", "2016-11-21", "2016-11-22", "2016-10-01"], dtype="datetime64[D]")
    mask = biel.season_mask(dates=dates, start="08-05", end="11-21")
    assert list(mask) == [False, True, True, False, True]


def test_each_porcini_day_is_compared_only_with_empty_days_of_its_year() -> None:
    dates = np.array(["2015-08-10", "2015-08-11", "2015-08-12", "2016-08-10", "2016-08-11"], dtype="datetime64[D]")
    counts = np.array([3, 0, 0, 0, 5])
    table = biel.build_day_table(dates=dates, counts=counts, weather=weather_for(size=5))
    assert list(table["case_id"]) == ["2015-08-10"] * 3 + ["2016-08-11"] * 2
    assert list(table["point_kind"]) == ["find", "other_day", "other_day", "find", "other_day"]
    assert list(table["assessment_date"]) == ["2015-08-10", "2015-08-11", "2015-08-12", "2016-08-11", "2016-08-10"]
    assert list(table["year"]) == [2015] * 3 + [2016] * 2


def test_days_without_complete_weather_are_left_out() -> None:
    dates = np.array(["2015-08-10", "2015-08-11", "2015-08-12"], dtype="datetime64[D]")
    weather = weather_for(size=3, rain=[1.0, np.nan, 1.0])
    table = biel.build_day_table(dates=dates, counts=np.array([1, 0, 0]), weather=weather)
    assert list(table["assessment_date"]) == ["2015-08-10", "2015-08-12"]


def test_rule_shares_count_each_day_once() -> None:
    dates = np.array(["2015-08-10", "2015-08-11", "2015-08-12", "2015-08-13"], dtype="datetime64[D]")
    counts = np.array([1, 2, 0, 0])
    weather = weather_for(size=4, rain=[50.0, 10.0, 50.0, 10.0])
    table = biel.build_day_table(dates=dates, counts=counts, weather=weather)
    conditions = [{"column": "rain_30d_mm", "op": ">=", "value": 30.0, "reason": "wet"}]
    rows = biel.rule_share_rows(table=table, conditions=conditions)
    assert rows == [{"rule": "rain_30d_mm >= 30", "porcini_days_meeting": 0.5, "other_days_meeting": 0.5}]
