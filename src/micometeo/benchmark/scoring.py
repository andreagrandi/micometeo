"""Rank positions, top shares, uncertainty ranges and the success rules of docs/test_rules.md.

The feature table is a dict of numpy arrays, one entry per column, one row per case square or comparison point.
"""

from typing import Any

import numpy as np

Table = dict[str, np.ndarray]

WEATHER_COLUMNS = ["rain_7d_mm", "rain_14d_mm", "rain_30d_mm", "temp_7d_c", "temp_14d_c", "temp_30d_c"]
HABITAT_COLUMNS = ["forest_share", "broadleaf_share", "altitude_m", "slope_deg"]
FEATURE_COLUMNS = HABITAT_COLUMNS + WEATHER_COLUMNS

# Comparison point kinds, as P4a names them in comparison_points.parquet.
POINT_KINDS = ("forest", "known_spot", "other_day")
TOP_SHARES = {"top10": 0.10, "top20": 0.20}
REDRAWS = 1000
SEED = 42


def complete_rows(*, table: Table, columns: list[str] | None = None) -> np.ndarray:
    """Return a mask of rows with no NaN in any of the given feature columns."""
    columns = FEATURE_COLUMNS if columns is None else columns
    mask = np.ones(len(table["case_id"]), dtype=bool)
    for column in columns:
        mask &= ~np.isnan(table[column].astype(float))
    return mask


def common_rows(*, table: Table, columns: list[str] | None = None) -> tuple[np.ndarray, dict[str, int]]:
    """Return the mask of rows every model is scored on, and how many cases and points were dropped.

    A case stays only if its find row is complete. Incomplete comparison points are dropped.
    """
    complete = complete_rows(table=table, columns=columns)
    is_find = table["point_kind"] == "find"
    kept_find = is_find & complete
    kept_cases = np.unique(table["case_id"][kept_find])
    mask = complete & np.isin(table["case_id"], kept_cases)
    all_cases = np.unique(table["case_id"][is_find])
    points = ~is_find
    return mask, {
        "cases_total": int(len(all_cases)),
        "cases_dropped": int(len(all_cases) - len(kept_cases)),
        "points_total": int(points.sum()),
        "points_dropped": int((points & ~mask).sum()),
    }


def rank_positions(*, case_ids: np.ndarray, is_find: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the sorted case ids and, for each, the share of comparison points above the find.

    Ties count as half. A rank of 0 means the find came first. A case without a find or without comparison points gets NaN.
    """
    unique_ids, ranks, _ = rank_spans(case_ids=case_ids, is_find=is_find, values=values)
    return unique_ids, ranks


def rank_spans(*, case_ids: np.ndarray, is_find: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the sorted case ids, the rank position with ties as half, and the share of points tied with the find.

    The tie share lets top shares count a tie as a random tie break, see hit_shares.
    """
    unique_ids, codes = np.unique(case_ids, return_inverse=True)
    size = len(unique_ids)
    find_values = np.full(size, np.nan)
    find_values[codes[is_find]] = values[is_find]
    points = ~is_find
    point_codes = codes[points]
    point_values = values[points]
    reference = find_values[point_codes]
    above = np.bincount(point_codes, weights=(point_values > reference).astype(float), minlength=size)
    ties = np.bincount(point_codes, weights=(point_values == reference).astype(float), minlength=size)
    counts = np.bincount(point_codes, minlength=size).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        ranks = (above + 0.5 * ties) / counts
        tie_shares = ties / counts
    ranks[counts == 0] = np.nan
    ranks[np.isnan(find_values)] = np.nan
    return unique_ids, ranks, tie_shares


def case_ranks(*, table: Table, values: np.ndarray, mask: np.ndarray, set_name: str, point_kind: str) -> dict[str, np.ndarray]:
    """Return rank, block and year group of each scorable case of one set against one kind of point."""
    kinds = table["point_kind"]
    selected = mask & (table["set"] == set_name) & ((kinds == "find") | (kinds == point_kind))
    case_ids = table["case_id"][selected]
    is_find = kinds[selected] == "find"
    unique_ids, ranks, tie_shares = rank_spans(case_ids=case_ids, is_find=is_find, values=values[selected])
    find_ids = case_ids[is_find]
    group_labels = np.char.add(
        np.char.add(table["block_id"][selected][is_find].astype(str), "|"),
        table["year"][selected][is_find].astype(str),
    )
    order = np.argsort(find_ids, kind="stable")
    labels_by_case = np.full(len(unique_ids), "", dtype=group_labels.dtype)
    labels_by_case[np.searchsorted(unique_ids, find_ids[order])] = group_labels[order]
    keep = ~np.isnan(ranks)
    return {"case_id": unique_ids[keep], "rank": ranks[keep], "tie": tie_shares[keep], "group": labels_by_case[keep]}


def hit_shares(*, ranks: np.ndarray, ties: np.ndarray | None, limit: float) -> np.ndarray:
    """Return for each case the chance that its rank position falls below the limit, breaking ties at random.

    Without ties this is 1 or 0. A find tied with many points lands anywhere in the tied span with equal chance.
    """
    if ties is None:
        return (ranks < limit).astype(float)
    low = ranks - ties / 2
    with np.errstate(invalid="ignore", divide="ignore"):
        spread = np.clip((limit - low) / ties, 0.0, 1.0)
    return np.where(ties > 0, spread, (ranks < limit).astype(float))


def top_shares(*, ranks: np.ndarray, ties: np.ndarray | None = None) -> dict[str, float]:
    """Return the share of cases with a rank position below 0.10 and below 0.20, ties broken at random."""
    if len(ranks) == 0:
        return {name: float("nan") for name in TOP_SHARES}
    return {name: float(hit_shares(ranks=ranks, ties=ties, limit=limit).mean()) for name, limit in TOP_SHARES.items()}


def group_redraws(*, groups: np.ndarray, redraws: int = REDRAWS, seed: int = SEED) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the group code of each case, the case count per group and the redraw index matrix.

    Each redraw picks as many groups as exist, with replacement.
    """
    _, codes = np.unique(groups, return_inverse=True)
    group_sizes = np.bincount(codes)
    draws = np.random.default_rng(seed).integers(0, len(group_sizes), size=(redraws, len(group_sizes)))
    return codes, group_sizes, draws


def redrawn_shares(
    *, ranks: np.ndarray, codes: np.ndarray, group_sizes: np.ndarray, draws: np.ndarray, ties: np.ndarray | None = None
) -> dict[str, np.ndarray]:
    """Return the top shares of every redraw."""
    sizes_per_draw = group_sizes[draws].sum(axis=1)
    result = {}
    for name, limit in TOP_SHARES.items():
        hits = np.bincount(codes, weights=hit_shares(ranks=ranks, ties=ties, limit=limit), minlength=len(group_sizes))
        result[name] = hits[draws].sum(axis=1) / sizes_per_draw
    return result


def interval(*, values: np.ndarray) -> tuple[float, float]:
    """Return the 2.5 and 97.5 percentiles."""
    low, high = np.percentile(values, [2.5, 97.5])
    return float(low), float(high)


def score_models(*, table: Table, predictions: dict[str, np.ndarray], redraws: int = REDRAWS, seed: int = SEED) -> dict[str, Any]:
    """Score every model on the same rows, per set and point kind, with uncertainty ranges.

    Each entry under "scores" keeps the redrawn shares so that any two models can be compared with difference_range.
    """
    mask, dropped = common_rows(table=table)
    unknown = set(table["point_kind"].astype(str)) - {"find", *POINT_KINDS}
    if unknown:
        raise ValueError(f"Unknown point kinds would be left out of every score: {sorted(unknown)}")
    kinds = [kind for kind in POINT_KINDS if np.any(table["point_kind"] == kind)]
    scores: dict[tuple[str, str], dict[str, Any]] = {}
    for set_name in sorted(set(table["set"].astype(str))):
        for kind in kinds:
            entry: dict[str, Any] = {"models": {}, "redraws": {}}
            codes = group_sizes = draws = None
            for name, values in predictions.items():
                cases = case_ranks(table=table, values=values, mask=mask, set_name=set_name, point_kind=kind)
                if codes is None:
                    entry["n_cases"] = int(len(cases["rank"]))
                    if entry["n_cases"] == 0:
                        break
                    codes, group_sizes, draws = group_redraws(groups=cases["group"], redraws=redraws, seed=seed)
                    entry["n_groups"] = int(len(group_sizes))
                shares = top_shares(ranks=cases["rank"], ties=cases["tie"])
                redrawn = redrawn_shares(
                    ranks=cases["rank"], codes=codes, group_sizes=group_sizes, draws=draws, ties=cases["tie"]
                )
                entry["redraws"][name] = redrawn
                entry["models"][name] = {
                    **shares,
                    **{f"{key}_range": interval(values=redrawn[key]) for key in TOP_SHARES},
                }
            scores[(set_name, kind)] = entry
    return {"dropped": dropped, "scores": scores}


def difference_range(*, entry: dict[str, Any], model_a: str, model_b: str, share: str = "top20") -> dict[str, Any]:
    """Return model A minus model B for one share, with the range from the same redrawn groups."""
    redrawn = entry["redraws"]
    difference = redrawn[model_a][share] - redrawn[model_b][share]
    low, high = interval(values=difference)
    return {
        "difference": entry["models"][model_a][share] - entry["models"][model_b][share],
        "range": (low, high),
    }


def check_rules(*, result: dict[str, Any], set_name: str, rain: str, habitat: str, both: str) -> dict[str, Any]:
    """Check S1, S2 and S3 on forest points for one set.

    S1 and S2 are checked for the model with weather and habitat. S3 compares it with habitat alone.
    """
    entry = result["scores"][(set_name, "forest")]
    top20 = entry["models"][both]["top20"]
    low = entry["models"][both]["top20_range"][0]
    s2 = difference_range(entry=entry, model_a=both, model_b=rain)
    s3 = difference_range(entry=entry, model_a=both, model_b=habitat)
    return {
        "S1": {"passed": bool(top20 >= 0.30 and low > 0.20), "top20": top20, "lower_end": low},
        "S2": {
            "passed": bool(s2["difference"] >= 0.05 and s2["range"][0] > 0),
            "difference": s2["difference"],
            "lower_end": s2["range"][0],
        },
        "S3": {
            "passed": bool(s3["difference"] >= 0.05 and s3["range"][0] > 0),
            "difference": s3["difference"],
            "lower_end": s3["range"][0],
        },
    }
