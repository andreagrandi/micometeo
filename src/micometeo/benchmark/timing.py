"""Timing test: rank the find day among the other days of the same square, 45 days either side."""

from pathlib import Path
from typing import Any

import numpy as np

from micometeo.benchmark import features, models
from micometeo.benchmark.scoring import Table, difference_range

WINDOW_DAYS = 45
OTHER_DAY = "other_day"
HABITAT_AND_PLACE = ["forest_share", "broadleaf_share", "altitude_m", "slope_deg"]
CASE_COLUMNS = ["case_id", "set", "area", "block_id", "year", "cell_id", "latitude", "longitude", *HABITAT_AND_PLACE]
WEATHER_GUESSES = ["rain_7d", "rain_14d", "rain_30d", "rules_weather", "logistic_weather"]


def build_timing_table(*, arrays: Table, other_cases: tuple[np.ndarray, np.ndarray], weather_dir: Path) -> Table:
    """Return one row per case and day from 45 days before to 45 days after, with weather and day of year.

    other_cases holds the cell ids and dates of every case of the P4a run. A day with a case in the same square is skipped.
    Habitat values are copied from the find row.
    """
    is_find = arrays["point_kind"] == "find"
    finds = {name: arrays[name][is_find] for name in CASE_COLUMNS}
    find_days = arrays["assessment_date"][is_find].astype("datetime64[D]").astype("int64")
    offsets = np.arange(-WINDOW_DAYS, WINDOW_DAYS + 1)
    count = len(offsets)
    rows = {name: np.repeat(values, count) for name, values in finds.items()}
    row_offsets = np.tile(offsets, len(find_days))
    row_days = np.repeat(find_days, count) + row_offsets

    other_cells, other_dates = other_cases
    cell_codes, inverse = np.unique(np.concatenate([other_cells, rows["cell_id"]]), return_inverse=True)
    taken = inverse[: len(other_cells)].astype("int64") * 1_000_000 + other_dates.astype("datetime64[D]").astype("int64")
    row_keys = inverse[len(other_cells) :].astype("int64") * 1_000_000 + row_days
    keep = (row_offsets == 0) | ~np.isin(row_keys, taken)

    rows = {name: values[keep] for name, values in rows.items()}
    row_days = row_days[keep]
    row_offsets = row_offsets[keep]
    dates = row_days.astype("datetime64[D]")
    rows["assessment_date"] = dates.astype(str)
    rows["point_kind"] = np.where(row_offsets == 0, "find", OTHER_DAY)
    rows["day_of_year"] = (dates - dates.astype("datetime64[Y]").astype("datetime64[D]")).astype("int64") + 1
    weather, _, _ = features.weather_features(
        latitudes=rows["latitude"].astype(float),
        longitudes=rows["longitude"].astype(float),
        dates=list(rows["assessment_date"]),
        weather_dir=weather_dir,
    )
    rows.update(weather)
    return rows


def calendar_guess(*, table: Table, tuning_set: str = models.TUNING) -> np.ndarray:
    """Rank days higher the closer they are to the median day of year of tuning finds."""
    tuning_finds = (table["set"] == tuning_set) & (table["point_kind"] == "find")
    middle = np.median(table["day_of_year"][tuning_finds])
    return -np.abs(table["day_of_year"].astype(float) - middle)


def timing_predictions(*, table: Table, conditions: list[dict[str, Any]], seed: int) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    """Return the values of the timing models for every row, and the logistic coefficients."""
    predictions = {
        "random": models.random_values(table=table, seed=seed),
        "calendar_guess": calendar_guess(table=table),
        "rain_7d": table["rain_7d_mm"].astype(float),
        "rain_14d": table["rain_14d_mm"].astype(float),
        "rain_30d": table["rain_30d_mm"].astype(float),
        "rules_weather": models.rule_values(table=table, conditions=conditions),
    }
    predictions["logistic_weather"], coefficients = models.fit_logistic(
        table=table, columns=models.FEATURE_SETS["weather"], seed=seed, comparison_kind=OTHER_DAY
    )
    return predictions, coefficients


def choose_best(*, result: dict[str, Any], candidates: list[str] = WEATHER_GUESSES, set_name: str = models.TUNING) -> str:
    """Return the candidate with the highest top 20 percent score on the tuning set."""
    models_scored = result["scores"][(set_name, OTHER_DAY)]["models"]
    return max(candidates, key=lambda name: models_scored[name]["top20"])


def check_timing(*, result: dict[str, Any], set_name: str, best: str, calendar: str = "calendar_guess") -> list[dict[str, Any]]:
    """Check T1 and T2 for the chosen model on one set."""
    entry = result["scores"][(set_name, OTHER_DAY)]
    top20 = entry["models"][best]["top20"]
    low = entry["models"][best]["top20_range"][0]
    gap = difference_range(entry=entry, model_a=best, model_b=calendar)
    return [
        {"set": set_name, "model": best, "check": "T1", "value": top20, "lower_end": low, "passed": bool(top20 >= 0.30 and low > 0.20)},
        {
            "set": set_name,
            "model": best,
            "check": "T2",
            "value": gap["difference"],
            "lower_end": gap["range"][0],
            "passed": bool(gap["difference"] >= 0.05 and gap["range"][0] > 0),
        },
    ]
