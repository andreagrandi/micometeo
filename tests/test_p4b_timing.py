"""Offline checks of the timing test on small synthetic data."""

from pathlib import Path

import numpy as np
import pytest

from micometeo.benchmark import models, scoring, timing


def find_table(*, days: list[str], sets: list[str]) -> scoring.Table:
    count = len(days)
    table: scoring.Table = {
        "case_id": np.array([f"c{i}" for i in range(count)]),
        "set": np.array(sets),
        "area": np.array(["comparison"] * count),
        "block_id": np.array([f"b{i % 2}" for i in range(count)]),
        "year": np.array([2020] * count),
        "assessment_date": np.array(days),
        "point_kind": np.array(["find"] * count),
        "cell_id": np.array([f"cell{i}" for i in range(count)]),
        "latitude": np.full(count, 43.0),
        "longitude": np.full(count, 11.0),
    }
    for column in timing.HABITAT_AND_PLACE:
        table[column] = np.full(count, 0.5)
    return table


def patch_weather(monkeypatch) -> None:
    def fake(*, latitudes, longitudes, dates, weather_dir):
        size = len(dates)
        return {name: np.ones(size) for name in scoring.WEATHER_COLUMNS}, [], []

    monkeypatch.setattr(timing.features, "weather_features", fake)


def test_window_has_91_days_with_find_in_the_middle(monkeypatch) -> None:
    patch_weather(monkeypatch)
    arrays = find_table(days=["2020-10-01"], sets=["tuning"])
    table = timing.build_timing_table(arrays=arrays, other_cases=(np.array([]), np.array([])), weather_dir=Path("."))
    assert len(table["case_id"]) == 91
    assert list(table["point_kind"]).count("find") == 1
    assert table["assessment_date"][0] == "2020-08-17"
    assert table["assessment_date"][-1] == "2020-11-15"
    find_index = list(table["point_kind"]).index("find")
    assert table["assessment_date"][find_index] == "2020-10-01"
    assert table["day_of_year"][find_index] == 275
    assert (table["forest_share"] == 0.5).all()


def test_days_with_a_case_in_the_same_square_are_left_out(monkeypatch) -> None:
    patch_weather(monkeypatch)
    arrays = find_table(days=["2020-10-01"], sets=["tuning"])
    other = (np.array(["cell0", "cell0", "elsewhere"]), np.array(["2020-10-04", "2020-09-30", "2020-10-02"]))
    table = timing.build_timing_table(arrays=arrays, other_cases=other, weather_dir=Path("."))
    dates = set(table["assessment_date"])
    assert "2020-10-04" not in dates
    assert "2020-09-30" not in dates
    assert "2020-10-02" in dates
    assert len(table["case_id"]) == 89


def test_calendar_guess_uses_tuning_find_median_only() -> None:
    table = {
        "set": np.array(["tuning", "tuning", "test", "tuning"]),
        "point_kind": np.array(["find", "find", "find", "other_day"]),
        "day_of_year": np.array([100, 300, 10, 50]),
    }
    guess = timing.calendar_guess(table=table)
    assert list(guess) == [-100.0, -100.0, -190.0, -150.0]


def test_logistic_fits_find_against_other_days() -> None:
    rng = np.random.default_rng(0)
    rows = 300
    kinds = np.where(np.arange(rows) % 10 == 0, "find", "other_day")
    table: scoring.Table = {
        "case_id": np.array([f"c{i // 10}" for i in range(rows)]),
        "set": np.array(["tuning"] * rows),
        "point_kind": kinds,
    }
    for column in scoring.FEATURE_COLUMNS:
        table[column] = rng.normal(size=rows) + (3.0 * (kinds == "find") if column == "rain_14d_mm" else 0.0)
    _, coefficients = models.fit_logistic(table=table, columns=models.FEATURE_SETS["weather"], comparison_kind="other_day")
    assert coefficients["rain_14d_mm"] > 0.5
    # Without finds against forest rows nothing is left to fit.
    with pytest.raises(ValueError):
        models.fit_logistic(table=table, columns=models.FEATURE_SETS["weather"])


def fake_result(*, tuning: dict[str, float], test: dict[str, float]) -> dict:
    def entry(shares: dict[str, float]) -> dict:
        redraws = {name: {"top20": np.full(1000, share), "top10": np.full(1000, share)} for name, share in shares.items()}
        models_ = {name: {"top20": share, "top20_range": (share, share)} for name, share in shares.items()}
        return {"models": models_, "redraws": redraws}

    return {"scores": {("tuning", "other_day"): entry(tuning), ("test", "other_day"): entry(test)}}


def test_best_model_is_chosen_on_tuning_only() -> None:
    result = fake_result(
        tuning={"rain_7d": 0.4, "rain_14d": 0.3, "rain_30d": 0.2, "rules_weather": 0.1, "logistic_weather": 0.35},
        test={"rain_7d": 0.1, "rain_14d": 0.9, "rain_30d": 0.2, "rules_weather": 0.1, "logistic_weather": 0.35},
    )
    assert timing.choose_best(result=result) == "rain_7d"


def test_t1_and_t2_need_the_thresholds() -> None:
    passing = fake_result(tuning={}, test={"rain_7d": 0.40, "calendar_guess": 0.30})
    t1, t2 = timing.check_timing(result=passing, set_name="test", best="rain_7d")
    assert t1["passed"] and t2["passed"]
    close = fake_result(tuning={}, test={"rain_7d": 0.40, "calendar_guess": 0.37})
    t1, t2 = timing.check_timing(result=close, set_name="test", best="rain_7d")
    assert t1["passed"] and not t2["passed"]
    low = fake_result(tuning={}, test={"rain_7d": 0.25, "calendar_guess": 0.10})
    t1, t2 = timing.check_timing(result=low, set_name="test", best="rain_7d")
    assert not t1["passed"] and t2["passed"]
