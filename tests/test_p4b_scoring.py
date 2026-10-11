"""Offline checks of the P4b scoring code and models on small synthetic tables."""

import time

import numpy as np
import pytest

from micometeo.benchmark import models, scoring

COLUMNS = scoring.FEATURE_COLUMNS


def build_table(*, cases: int = 60, seed: int = 0, signal: float = 3.0, sets: tuple[str, ...] = ("tuning", "test")) -> scoring.Table:
    """Build cases with one find, 20 forest points and 10 known spots, where finds have more rain."""
    rng = np.random.default_rng(seed)
    rows: dict[str, list] = {name: [] for name in ["case_id", "set", "area", "block_id", "year", "assessment_date", "point_kind", *COLUMNS]}
    for index in range(cases):
        for kind, count in (("find", 1), ("forest", 20), ("known_spot", 10)):
            for _ in range(count):
                rows["case_id"].append(f"c{index:04d}")
                rows["set"].append(sets[index % len(sets)])
                rows["area"].append("comparison")
                rows["block_id"].append(f"b{index % 6}")
                rows["year"].append(2018 + index % 3)
                rows["assessment_date"].append("2020-10-01")
                rows["point_kind"].append(kind)
                for column in COLUMNS:
                    shift = signal if kind == "find" and column == "rain_7d_mm" else 0.0
                    rows[column].append(rng.normal() + shift)
    return {name: np.array(values) for name, values in rows.items()}


def ranks_of(*, find: float, points: list[float]) -> float:
    values = np.array([find, *points], dtype=float)
    _, ranks = scoring.rank_positions(
        case_ids=np.array(["a"] * len(values)), is_find=np.array([True] + [False] * len(points)), values=values
    )
    return float(ranks[0])


def test_rank_position_find_first_is_zero() -> None:
    assert ranks_of(find=9.0, points=[1.0, 2.0, 3.0, 4.0]) == 0.0


def test_rank_position_find_last_is_one() -> None:
    assert ranks_of(find=0.0, points=[1.0, 2.0, 3.0, 4.0]) == 1.0


def test_rank_position_counts_ties_as_half() -> None:
    assert ranks_of(find=2.0, points=[2.0, 2.0, 1.0, 3.0]) == (1 + 0.5 * 2) / 4


def test_rank_positions_handle_many_cases_independently() -> None:
    case_ids = np.array(["b", "b", "b", "a", "a"])
    is_find = np.array([True, False, False, True, False])
    values = np.array([1.0, 2.0, 0.0, 5.0, 6.0])
    ids, ranks = scoring.rank_positions(case_ids=case_ids, is_find=is_find, values=values)
    assert list(ids) == ["a", "b"]
    assert list(ranks) == [1.0, 0.5]


def test_tied_find_counts_as_random_tie_break() -> None:
    # The find ties with 4 of 10 points and 1 point is above, so it lands anywhere from 0.1 to 0.5.
    values = np.array([1.0, 2.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    is_find = np.array([True] + [False] * 10)
    _, ranks, ties = scoring.rank_spans(case_ids=np.array(["a"] * 11), is_find=is_find, values=values)
    assert ranks[0] == 0.3
    assert ties[0] == 0.4
    shares = scoring.top_shares(ranks=ranks, ties=ties)
    assert abs(shares["top10"]) < 1e-12
    assert abs(shares["top20"] - 0.25) < 1e-12


def test_constant_model_scores_like_random() -> None:
    table = build_table()
    constant = np.zeros(len(table["case_id"]))
    result = scoring.score_models(table=table, predictions={"constant": constant})
    entry = result["scores"][("test", "forest")]["models"]["constant"]
    assert abs(entry["top20"] - 0.20) < 1e-12
    assert abs(entry["top10"] - 0.10) < 1e-12


def test_top_shares_use_strict_limits() -> None:
    shares = scoring.top_shares(ranks=np.array([0.0, 0.05, 0.10, 0.15, 0.25, 0.9]))
    assert shares == {"top10": 2 / 6, "top20": 4 / 6}


def test_common_rows_drop_cases_with_incomplete_find_and_incomplete_points() -> None:
    table = build_table(cases=4)
    find_rows = np.where((table["case_id"] == "c0000") & (table["point_kind"] == "find"))[0]
    table["rain_7d_mm"][find_rows[0]] = np.nan
    forest_rows = np.where((table["case_id"] == "c0001") & (table["point_kind"] == "forest"))[0]
    table["slope_deg"][forest_rows[:3]] = np.nan
    mask, dropped = scoring.common_rows(table=table)
    assert dropped["cases_dropped"] == 1
    assert dropped["cases_total"] == 4
    assert dropped["points_dropped"] == 30 + 3
    assert not mask[table["case_id"] == "c0000"].any()
    assert mask[table["case_id"] == "c0002"].all()


def test_perfect_model_gets_top20_of_one() -> None:
    table = build_table()
    perfect = (table["point_kind"] == "find").astype(float)
    result = scoring.score_models(table=table, predictions={"perfect": perfect, "other": models.random_values(table=table)})
    for entry in result["scores"].values():
        assert entry["models"]["perfect"]["top20"] == 1.0
        assert entry["models"]["perfect"]["top10"] == 1.0


def test_scores_cover_both_point_kinds_of_p4a() -> None:
    table = build_table()
    result = scoring.score_models(table=table, predictions={"random": models.random_values(table=table)})
    assert ("test", "forest") in result["scores"]
    assert ("test", "known_spot") in result["scores"]


def test_unknown_point_kind_stops_scoring() -> None:
    table = build_table()
    table["point_kind"] = np.where(table["point_kind"] == "known_spot", "known", table["point_kind"])
    with pytest.raises(ValueError, match="known"):
        scoring.score_models(table=table, predictions={"random": models.random_values(table=table)})


def test_rules_use_rain_of_days_8_to_30_and_cooling() -> None:
    table = {
        "case_id": np.array(["a", "a"]),
        "rain_7d_mm": np.array([40.0, 0.0]),
        "rain_30d_mm": np.array([50.0, 50.0]),
        "temp_7d_c": np.array([15.0, 11.0]),
        "temp_30d_c": np.array([14.0, 14.0]),
    }
    conditions = [
        {"column": "rain_8_30d_mm", "op": ">=", "value": 30.0},
        {"column": "temp_drop_c", "op": ">=", "value": 1.0},
    ]
    assert list(models.rule_values(table=table, conditions=conditions)) == [0.0, 2.0]


def test_rules_derive_day_of_year_from_the_date() -> None:
    table = {"case_id": np.array(["a", "b"]), "assessment_date": np.array(["2021-06-14", "2021-06-15"])}
    conditions = [{"column": "day_of_year", "op": ">=", "value": 166.0}]
    assert list(models.rule_values(table=table, conditions=conditions)) == [0.0, 1.0]


def test_identical_models_have_same_range_and_zero_difference() -> None:
    table = build_table()
    values = models.rain_guess(table=table)
    result = scoring.score_models(table=table, predictions={"a": values, "b": values.copy()})
    entry = result["scores"][("test", "forest")]
    assert entry["models"]["a"]["top20_range"] == entry["models"]["b"]["top20_range"]
    difference = scoring.difference_range(entry=entry, model_a="a", model_b="b")
    assert difference["difference"] == 0.0
    assert difference["range"] == (0.0, 0.0)


def test_redraws_reuse_the_same_groups_for_every_model() -> None:
    table = build_table()
    result = scoring.score_models(table=table, predictions={"a": models.rain_guess(table=table), "b": models.random_values(table=table)})
    entry = result["scores"][("tuning", "forest")]
    assert entry["n_groups"] <= 6 * 3
    again = scoring.score_models(table=table, predictions={"b": models.random_values(table=table)})
    assert np.array_equal(entry["redraws"]["b"]["top20"], again["scores"][("tuning", "forest")]["redraws"]["b"]["top20"])


def test_rule_checks_pass_for_strong_model_and_fail_for_random() -> None:
    table = build_table(cases=120, sets=("test",), signal=0.5)
    perfect = (table["point_kind"] == "find").astype(float)
    predictions = {
        "random": models.random_values(table=table),
        "rain": models.rain_guess(table=table),
        "habitat": models.habitat_guess(table=table),
        "both": perfect,
    }
    result = scoring.score_models(table=table, predictions=predictions)
    checks = scoring.check_rules(result=result, set_name="test", rain="rain", habitat="habitat", both="both")
    assert checks["S1"]["passed"] and checks["S2"]["passed"] and checks["S3"]["passed"]
    weak = scoring.check_rules(result=result, set_name="test", rain="rain", habitat="habitat", both="random")
    assert not weak["S1"]["passed"]
    assert not weak["S2"]["passed"]


def test_rule_values_count_met_conditions() -> None:
    table = {"case_id": np.array(["a", "b", "c"]), "rain_7d_mm": np.array([10.0, 2.0, np.nan]), "temp_7d_c": np.array([8.0, 8.0, 8.0])}
    conditions = [
        {"column": "rain_7d_mm", "op": ">=", "value": 5.0, "reason": "wet week"},
        {"column": "temp_7d_c", "op": "<=", "value": 12.0, "reason": "cool week"},
    ]
    assert list(models.rule_values(table=table, conditions=conditions)) == [2.0, 1.0, 1.0]


def test_logistic_regression_ranks_finds_with_more_rain_high() -> None:
    table = build_table(cases=80)
    log_odds, coefficients = models.fit_logistic(table=table, columns=models.FEATURE_SETS["weather"])
    assert coefficients["rain_7d_mm"] > 0.5
    result = scoring.score_models(table=table, predictions={"logistic": log_odds})
    assert result["scores"][("test", "forest")]["models"]["logistic"]["top20"] > 0.8


def test_standardisation_uses_tuning_rows_only() -> None:
    table = build_table(cases=40)
    log_odds, _ = models.fit_logistic(table=table, columns=models.FEATURE_SETS["habitat"])
    changed = {name: values.copy() for name, values in table.items()}
    test_rows = changed["set"] == "test"
    changed["altitude_m"][test_rows] += 1000.0
    changed_log_odds, _ = models.fit_logistic(table=changed, columns=models.FEATURE_SETS["habitat"])
    tuning_rows = ~test_rows
    assert np.allclose(log_odds[tuning_rows], changed_log_odds[tuning_rows])
    assert not np.allclose(log_odds[test_rows], changed_log_odds[test_rows])


def test_logistic_regression_gives_same_result_with_same_seed() -> None:
    table = build_table(cases=40)
    first, first_coefficients = models.fit_logistic(table=table, columns=models.FEATURE_SETS["both"], seed=42)
    second, second_coefficients = models.fit_logistic(table=table, columns=models.FEATURE_SETS["both"], seed=42)
    assert np.array_equal(first, second)
    assert first_coefficients == second_coefficients
    assert np.array_equal(models.random_values(table=table), models.random_values(table=table))


def test_leave_block_out_scores_all_tuning_cases() -> None:
    table = build_table(cases=60, sets=("tuning",))
    shares = models.leave_block_out(table=table, columns=models.FEATURE_SETS["weather"])
    assert shares["n_cases"] == 60
    assert shares["top20"] > 0.8


def test_scoring_speed_on_280000_rows() -> None:
    rng = np.random.default_rng(1)
    cases = 1900
    per_case = 150
    n = cases * per_case
    case_ids = np.repeat([f"c{i:05d}" for i in range(cases)], per_case)
    kinds = np.tile(np.array(["find"] + ["forest"] * 100 + ["known_spot"] * 49), cases)
    table: scoring.Table = {
        "case_id": case_ids,
        "set": np.where(np.repeat(np.arange(cases), per_case) % 2 == 0, "tuning", "test"),
        "block_id": np.repeat(np.arange(cases) % 40, per_case),
        "year": np.repeat(2018 + np.arange(cases) % 6, per_case),
        "point_kind": kinds,
    }
    for column in COLUMNS:
        table[column] = rng.normal(size=n)
    start = time.perf_counter()
    scoring.score_models(table=table, predictions={"a": rng.random(n), "b": rng.random(n)})
    assert time.perf_counter() - start < 10
