"""Record counts before and after the duplicate rules and filters."""

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from micometeo.finds.cleaning import DUPLICATE_RULES, FILTERS

AREAS = ["home", "pistoia", "comparison"]
STAGES = ["all", "after_duplicates", "eligible", "timing"]
DIMENSIONS = [
    "year",
    "season",
    "source",
    "location_accuracy",
    "blurred",
    "identification_quality",
    "licence",
]
COUNT_COLUMNS = ["area", "stage", "dimension", "value", "records"]
DROPPED_COLUMNS = ["area", "kind", "step", "records"]


def accuracy_class(*, uncertainty_m: float | None) -> str:
    """Group a position error in metres into a class for the count table."""
    if uncertainty_m is None:
        return "unknown"
    if uncertainty_m <= 100:
        return "up_to_100m"
    if uncertainty_m <= 1000:
        return "101_to_1000m"
    return "above_1000m"


def _value(record: dict[str, Any], dimension: str) -> str:
    if dimension == "location_accuracy":
        return accuracy_class(uncertainty_m=record["coordinate_uncertainty_m"])
    if dimension == "blurred":
        return "yes" if record["coordinates_obscured"] else "no"
    value = record[dimension]
    return "" if value is None else str(value)


def in_area(*, record: dict[str, Any], area: str) -> bool:
    """Return True if the record belongs to a report area, Pistoia being part of home."""
    if area == "pistoia":
        return record["area"] == "home" and bool(record["in_pistoia"])
    return record["area"] == area


def in_stage(*, record: dict[str, Any], stage: str) -> bool:
    """Return True if the record is still present at that stage of the cleaning."""
    if stage == "all":
        return True
    if stage == "after_duplicates":
        return not record["duplicate_rule"]
    if stage == "timing":
        return not record["duplicate_rule"] and bool(record.get("square_id"))
    return not record["duplicate_rule"] and not record["failed_filter"]


def count_table(*, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Count records by area, stage and each dimension, in long format."""
    rows = []
    for area in AREAS:
        for stage in STAGES:
            selected = [
                record
                for record in records
                if in_area(record=record, area=area) and in_stage(record=record, stage=stage)
            ]
            rows.append(
                {
                    "area": area,
                    "stage": stage,
                    "dimension": "total",
                    "value": "",
                    "records": len(selected),
                }
            )
            for dimension in DIMENSIONS:
                counts = Counter(_value(record, dimension) for record in selected)
                for value in sorted(counts):
                    rows.append(
                        {
                            "area": area,
                            "stage": stage,
                            "dimension": dimension,
                            "value": value,
                            "records": counts[value],
                        }
                    )
    return rows


def dropped_table(*, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Count how many records each duplicate rule and each filter removed, per area."""
    rows = []
    for area in AREAS:
        selected = [record for record in records if in_area(record=record, area=area)]
        rules = Counter(record["duplicate_rule"] for record in selected)
        failed = Counter(record["failed_filter"] for record in selected)
        rows += [
            {"area": area, "kind": "duplicate", "step": rule, "records": rules[rule]}
            for rule in DUPLICATE_RULES
        ]
        rows += [
            {"area": area, "kind": "filter", "step": step, "records": failed[step]}
            for step in FILTERS
        ]
    return rows


def write_csv(*, rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    """Write rows to a CSV file with the given columns."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
