"""P4b: score simple guesses, hand-written rules and logistic regression against random places."""

import csv
import glob
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from micometeo.benchmark import features, models, scoring, timing
from micometeo.context import RunContext
from micometeo.habitat.grid import read_download_note

ROOT = Path(__file__).resolve().parent.parent.parent
FINAL_SETS = ("final", "home_final")
SCORE_COLUMNS = [
    "model", "inputs", "set", "point_kind", "cases", "groups",
    "top10", "top10_low", "top10_high", "top20", "top20_low", "top20_high",
]  # fmt: skip
CHECK_COLUMNS = ["set", "family", "check", "value", "lower_end", "passed"]
TIMING_CHECK_COLUMNS = ["set", "chosen_model", "check", "value", "lower_end", "passed"]
COEFFICIENT_COLUMNS = ["feature_set", "feature", "coefficient"]
SUMMARY_COLUMNS = ["name", "value"]
INPUTS = {
    "random": "none",
    "rain_7d_guess": "weather",
    "forest_share_guess": "habitat",
    "rules_weather": "weather",
    "rules_habitat": "habitat",
    "rules_both": "both",
    "logistic_weather": "weather",
    "logistic_habitat": "habitat",
    "logistic_both": "both",
    "calendar_guess": "none",
    "rain_7d": "weather",
    "rain_14d": "weather",
    "rain_30d": "weather",
}
FAMILIES = ("rules", "logistic")


def write_csv(*, rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def resolve(*, path: str) -> Path:
    return Path(path) if Path(path).is_absolute() else ROOT / path


def table_to_arrays(*, table: pa.Table) -> scoring.Table:
    """Turn a feature table into numpy arrays, with text columns as plain strings."""
    arrays = {}
    for name in table.column_names:
        column = table[name].to_numpy(zero_copy_only=False)
        arrays[name] = column.astype(str) if table.schema.field(name).type == pa.string() else column
    return arrays


def drop_final_rows(*, table: pa.Table, score_final: bool) -> pa.Table:
    """Remove the final sets unless they are to be scored, so they cannot be scored by accident."""
    if score_final:
        return table
    keep = ~np.isin(table["set"].to_numpy(zero_copy_only=False).astype(str), FINAL_SETS)
    return table.filter(pa.array(keep))


def collapse_weather_sources(*, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace the one-per-cell ERA5 records with a single record, so the run record stays small."""
    cells = [record for record in records if record["name"].startswith("ERA5 hourly time series ")]
    others = [record for record in records if record not in cells]
    if not cells:
        return others
    one = {
        "name": f"ERA5 hourly time series, {len(cells)} cells of 0.25 degrees",
        "url": cells[0]["url"],
        "licence": cells[0]["licence"],
        "version": cells[0]["version"],
        "downloaded_at": max(record["downloaded_at"] for record in cells),
        "query": {"example_request": cells[0]["query"], "cells": len(cells)},
    }
    return [*others, one]


def build_predictions(*, arrays: scoring.Table, settings: dict[str, Any], seed: int) -> tuple[dict[str, np.ndarray], dict[str, dict[str, float]]]:
    """Return the values of every model for every row, and the logistic coefficients per feature set."""
    rules_weather = settings["rules_weather"]
    rules_habitat = settings["rules_habitat"]
    predictions = {
        "random": models.random_values(table=arrays, seed=seed),
        "rain_7d_guess": models.rain_guess(table=arrays),
        "forest_share_guess": models.habitat_guess(table=arrays),
        "rules_weather": models.rule_values(table=arrays, conditions=rules_weather),
        "rules_habitat": models.rule_values(table=arrays, conditions=rules_habitat),
        "rules_both": models.rule_values(table=arrays, conditions=rules_weather + rules_habitat),
    }
    coefficients = {}
    for name, columns in models.FEATURE_SETS.items():
        predictions[f"logistic_{name}"], coefficients[name] = models.fit_logistic(table=arrays, columns=columns, seed=seed)
    return predictions, coefficients


def score_rows(*, result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for (set_name, kind), entry in result["scores"].items():
        for model, values in entry["models"].items():
            rows.append(
                {
                    "model": model,
                    "inputs": INPUTS[model],
                    "set": set_name,
                    "point_kind": kind,
                    "cases": entry["n_cases"],
                    "groups": entry["n_groups"],
                    "top10": round(values["top10"], 3),
                    "top10_low": round(values["top10_range"][0], 3),
                    "top10_high": round(values["top10_range"][1], 3),
                    "top20": round(values["top20"], 3),
                    "top20_low": round(values["top20_range"][0], 3),
                    "top20_high": round(values["top20_range"][1], 3),
                }
            )
    return rows


def check_rows(*, result: dict[str, Any]) -> list[dict[str, Any]]:
    """Return S1, S2 and S3 per scored set and per family, plus S1 for weather alone on known spots."""
    rows = []
    for set_name in sorted({key[0] for key in result["scores"]}):
        forest = result["scores"].get((set_name, "forest"))
        if not forest or not forest["models"]:
            continue
        for family in FAMILIES:
            checks = scoring.check_rules(
                result=result,
                set_name=set_name,
                rain="rain_7d_guess",
                habitat=f"{family}_habitat",
                both=f"{family}_both",
            )
            for name, check in checks.items():
                rows.append(
                    {
                        "set": set_name,
                        "family": family,
                        "check": name,
                        "value": round(check["top20"] if name == "S1" else check["difference"], 3),
                        "lower_end": round(check["lower_end"], 3),
                        "passed": check["passed"],
                    }
                )
            known = result["scores"].get((set_name, "known_spot"))
            if known and known["models"]:
                weather = known["models"][f"{family}_weather"]
                rows.append(
                    {
                        "set": set_name,
                        "family": family,
                        "check": "S1 known spots weather",
                        "value": round(weather["top20"], 3),
                        "lower_end": round(weather["top20_range"][0], 3),
                        "passed": bool(weather["top20"] >= 0.30 and weather["top20_range"][0] > 0.20),
                    }
                )
    return rows


def run(context: RunContext) -> None:
    """Build the feature table, score every model on the same rows and write the report files."""
    settings = context.config
    timings: dict[str, float] = {}
    clock = time.monotonic()

    def lap(name: str) -> None:
        nonlocal clock
        timings[name] = round(time.monotonic() - clock, 1)
        clock = time.monotonic()

    run_dir = resolve(path=settings["p4a_run_dir"])
    weather_dir = resolve(path=settings["weather_dir"])
    dem_dir = resolve(path=settings["dem_dir"])
    tiles = list(Path(path) for path in sorted(glob.glob(str(resolve(path=settings["forest_tiles"])))))
    for name in ("cases.parquet", "comparison_points.parquet"):
        context.add_input(run_dir / name)

    def build() -> tuple[pa.Table, list, list]:
        return features.build_feature_table(run_dir=run_dir, weather_dir=weather_dir, forest_tiles=tiles, dem_dir=dem_dir)

    table, missing, records = build()
    if missing and settings.get("allow_missing_weather", False):
        print(f"WARNING: {len(missing)} weather cells are missing. Rows in those cells are dropped.")
    elif missing:
        features.fetch_missing(
            cells=missing, weather_dir=weather_dir, end_date=settings["weather_end_date"], workers=settings["download_workers"]
        )
        table, missing, records = build()
        if missing:
            raise RuntimeError(f"{len(missing)} weather cells are still missing after the download")
    lap("features")

    for record in collapse_weather_sources(records=records):
        context.add_source(**record)
    features_path = context.output_dir / "features.parquet"
    pq.write_table(table, features_path)
    context.add_output(features_path)

    orography_path = resolve(path=settings["orography_path"])
    heights, height_grid = features.cell_heights(path=orography_path)
    context.add_input(orography_path)
    context.add_source(
        **features.source_record(
            name="ERA5 ground height of each 0.25 degree cell",
            url=features.OROGRAPHY_URL,
            licence=features.ERA5_LICENCE,
            version="ERA5 geopotential at the surface, 1 January 2020 00:00, constant in time",
            note=read_download_note(path=orography_path),
        )
    )

    score_final = bool(settings["score_final"])
    arrays = table_to_arrays(table=drop_final_rows(table=table, score_final=score_final))
    arrays = features.correct_temperatures(table=arrays, heights=heights, transform=height_grid)
    predictions, coefficients = build_predictions(arrays=arrays, settings=settings, seed=context.seed)
    lap("models")

    result = scoring.score_models(table=arrays, predictions=predictions, redraws=settings["redraws"], seed=context.seed)
    lap("scores")

    other_cases = pq.read_table(run_dir / "cases.parquet", columns=["cell_id", "assessment_date"])
    timing_table = timing.build_timing_table(
        arrays=arrays,
        other_cases=(
            other_cases["cell_id"].to_numpy(zero_copy_only=False).astype(str),
            other_cases["assessment_date"].to_numpy(zero_copy_only=False).astype(str),
        ),
        weather_dir=weather_dir,
    )
    timing_table = features.correct_temperatures(table=timing_table, heights=heights, transform=height_grid)
    timing_values, timing_coefficients = timing.timing_predictions(
        table=timing_table, conditions=settings["rules_weather"], seed=context.seed
    )
    timing_result = scoring.score_models(
        table=timing_table, predictions=timing_values, redraws=settings["redraws"], seed=context.seed
    )
    best = timing.choose_best(result=timing_result)
    timing_checks = []
    for set_name in sorted({key[0] for key in timing_result["scores"]} - {models.TUNING}):
        if timing_result["scores"][(set_name, timing.OTHER_DAY)]["models"]:
            for row in timing.check_timing(result=timing_result, set_name=set_name, best=best):
                timing_checks.append(
                    {
                        "set": row["set"],
                        "chosen_model": row["model"],
                        "check": row["check"],
                        "value": round(row["value"], 3),
                        "lower_end": round(row["lower_end"], 3),
                        "passed": row["passed"],
                    }
                )
    lap("timing")

    leave_out = {name: models.leave_block_out(table=arrays, columns=columns, seed=context.seed) for name, columns in models.FEATURE_SETS.items()}
    lap("leave_one_block_out")

    reports_dir = resolve(path=settings["reports_dir"])
    coefficient_rows = [
        {"feature_set": name, "feature": feature, "coefficient": round(value, 4)}
        for name, values in coefficients.items()
        for feature, value in values.items()
    ]
    coefficient_rows += [
        {"feature_set": "timing_weather", "feature": feature, "coefficient": round(value, 4)}
        for feature, value in timing_coefficients.items()
    ]
    summary = [{"name": f"dropped_{key}", "value": value} for key, value in result["dropped"].items()]
    for name, values in leave_out.items():
        for key in ("top10", "top20", "n_cases"):
            summary.append({"name": f"leave_one_block_out_logistic_{name}_{key}", "value": round(values[key], 3)})
    summary += [{"name": f"seconds_{name}", "value": value} for name, value in timings.items()]
    outputs = {
        "p4b_scores.csv": (score_rows(result=result), SCORE_COLUMNS),
        "p4b_checks.csv": (check_rows(result=result), CHECK_COLUMNS),
        "p4b_timing_scores.csv": (score_rows(result=timing_result), SCORE_COLUMNS),
        "p4b_timing_checks.csv": (timing_checks, TIMING_CHECK_COLUMNS),
        "p4b_coefficients.csv": (coefficient_rows, COEFFICIENT_COLUMNS),
        "p4b_summary.csv": (summary, SUMMARY_COLUMNS),
    }
    for filename, (rows, columns) in outputs.items():
        path = reports_dir / filename
        write_csv(rows=rows, columns=columns, path=path)
        context.add_output(path)

    if score_final:
        print("FINAL SET SCORED: this is the one final use of the final and home final cases.")
    print(f"dropped: {result['dropped']}")
    for row in outputs["p4b_scores.csv"][0]:
        if row["point_kind"] == "forest" and row["set"] != "tuning":
            print(f"{row['set']:<10} {row['model']:<20} top20 {row['top20']} ({row['top20_low']} to {row['top20_high']})")
    for row in outputs["p4b_checks.csv"][0]:
        print(f"{row['set']:<10} {row['family']:<9} {row['check']:<24} {row['value']} lower {row['lower_end']} passed {row['passed']}")
    print(f"timing test, best weather prediction chosen on tuning: {best}")
    for row in outputs["p4b_timing_scores.csv"][0]:
        print(f"{row['set']:<10} {row['model']:<20} top20 {row['top20']} ({row['top20_low']} to {row['top20_high']})")
    for row in timing_checks:
        print(f"{row['set']:<10} {row['check']} {row['value']} lower {row['lower_end']} passed {row['passed']}")
    print("People also search more after rain, so a timing signal partly shows when people go out.")
    print(f"seconds: {timings}")
