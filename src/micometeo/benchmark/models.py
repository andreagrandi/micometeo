"""Models for the benchmark. Each returns one value per table row, higher meaning more likely a find."""

import operator
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression

from micometeo.benchmark.scoring import (
    HABITAT_COLUMNS,
    SEED,
    WEATHER_COLUMNS,
    Table,
    case_ranks,
    common_rows,
    top_shares,
)

FEATURE_SETS = {
    "weather": WEATHER_COLUMNS,
    "habitat": HABITAT_COLUMNS,
    "both": HABITAT_COLUMNS + WEATHER_COLUMNS,
}
OPERATORS = {">=": operator.ge, "<=": operator.le}
TUNING = "tuning"


def random_values(*, table: Table, seed: int = SEED) -> np.ndarray:
    """Return random values, a check of the scoring code."""
    return np.random.default_rng(seed).random(len(table["case_id"]))


def rain_guess(*, table: Table) -> np.ndarray:
    """Return the rain of the last 7 days, the simple weather guess."""
    return table["rain_7d_mm"].astype(float)


def habitat_guess(*, table: Table) -> np.ndarray:
    """Return the forest share, the simple habitat guess."""
    return table["forest_share"].astype(float)


def rule_column(*, table: Table, column: str) -> np.ndarray:
    """Return a table column, or one of the values that rules use but the table does not store.

    rain_8_30d_mm is rain from 30 to 8 days before, temp_drop_c is how much cooler the last 7 days were than the last 30,
    day_of_year comes from assessment_date when the table has no such column.
    """
    if column == "rain_8_30d_mm":
        return table["rain_30d_mm"].astype(float) - table["rain_7d_mm"].astype(float)
    if column == "temp_drop_c":
        return table["temp_30d_c"].astype(float) - table["temp_7d_c"].astype(float)
    if column == "day_of_year" and "day_of_year" not in table:
        dates = table["assessment_date"].astype("datetime64[D]")
        return (dates - dates.astype("datetime64[Y]").astype("datetime64[D]")).astype(float) + 1
    return table[column].astype(float)


def rule_values(*, table: Table, conditions: list[dict[str, Any]]) -> np.ndarray:
    """Return the number of conditions each row meets. A NaN value meets no condition."""
    total = np.zeros(len(table["case_id"]))
    for condition in conditions:
        compare = OPERATORS[condition["op"]]
        with np.errstate(invalid="ignore"):
            total += compare(rule_column(table=table, column=condition["column"]), condition["value"])
    return total


def fit_logistic(*, table: Table, columns: list[str], tuning_set: str = TUNING, seed: int = SEED, fit_mask: np.ndarray | None = None, comparison_kind: str = "forest") -> tuple[np.ndarray, dict[str, float]]:
    """Fit a logistic regression on tuning finds against tuning comparison points and return log-odds for every row.

    Means and spreads come from the fitting rows only. Rows with a NaN in the chosen columns get NaN.
    """
    common, _ = common_rows(table=table)
    kinds = table["point_kind"]
    fit = common & (table["set"] == tuning_set) & ((kinds == "find") | (kinds == comparison_kind))
    if fit_mask is not None:
        fit &= fit_mask
    features = np.column_stack([table[column].astype(float) for column in columns])
    train = features[fit]
    mean = train.mean(axis=0)
    spread = train.std(axis=0)
    spread[spread == 0] = 1.0
    model = LogisticRegression(random_state=seed)
    model.fit((train - mean) / spread, (kinds[fit] == "find").astype(int))
    log_odds = ((features - mean) / spread) @ model.coef_[0] + model.intercept_[0]
    coefficients = {column: float(value) for column, value in zip(columns, model.coef_[0])}
    coefficients["intercept"] = float(model.intercept_[0])
    return log_odds, coefficients


def leave_block_out(*, table: Table, columns: list[str], tuning_set: str = TUNING, seed: int = SEED) -> dict[str, float]:
    """Fit without one tuning block at a time, score that block, and return the top shares over all tuning cases.

    Scores use forest points.
    """
    in_tuning = table["set"] == tuning_set
    blocks = table["block_id"].astype(str)
    predictions = np.full(len(blocks), np.nan)
    for block in np.unique(blocks[in_tuning]):
        held_out = in_tuning & (blocks == block)
        log_odds, _ = fit_logistic(table=table, columns=columns, tuning_set=tuning_set, seed=seed, fit_mask=~held_out)
        predictions[held_out] = log_odds[held_out]
    mask, _ = common_rows(table=table)
    cases = case_ranks(table=table, values=predictions, mask=mask, set_name=tuning_set, point_kind="forest")
    return {**top_shares(ranks=cases["rank"], ties=cases["tie"]), "n_cases": int(len(cases["rank"]))}
