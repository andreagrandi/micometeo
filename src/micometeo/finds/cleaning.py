"""Duplicate rules and filters that decide which finds are reliable enough to use."""

import math
from collections import defaultdict
from typing import Any

DUPLICATE_RULES = ["repeated_download", "gbif_inat_overlap", "same_find_gbif", "same_find_inat"]
FILTERS = [
    "not_a_find",
    "no_full_date",
    "odd_date",
    "blurred",
    "odd_place",
    "low_accuracy",
    "weak_identification",
]
WEAK_IDENTIFICATION = ("inat_needs_id", "inat_casual")
EARTH_RADIUS_M = 6_371_000


def distance_m(*, a: dict[str, Any], b: dict[str, Any]) -> float:
    """Return the distance in metres between two records along the earth surface."""
    lat_a, lat_b = math.radians(a["latitude"]), math.radians(b["latitude"])
    d_lat = lat_b - lat_a
    d_lon = math.radians(b["longitude"] - a["longitude"])
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def _mark(record: dict[str, Any], rule: str, original: dict[str, Any]) -> None:
    record["duplicate_rule"] = rule
    record["duplicate_of"] = original["record_id"]


def _same_find(
    records: list[dict[str, Any]], source: str, rule: str, max_distance_m: float
) -> None:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if (
            record["source"] == source
            and not record["duplicate_rule"]
            and not record["coordinates_obscured"]
            and record["latitude"] is not None
            and record["event_date"]
            and record["recorded_by"]
        ):
            groups[(record["event_date"], record["recorded_by"])].append(record)
    for group in groups.values():
        kept: list[dict[str, Any]] = []
        for record in sorted(group, key=lambda item: item["record_id"]):
            original = next(
                (other for other in kept if distance_m(a=record, b=other) <= max_distance_m),
                None,
            )
            if original is None:
                kept.append(record)
            else:
                _mark(record, rule, original)


def mark_duplicates(*, records: list[dict[str, Any]], max_distance_m: float) -> None:
    """Fill duplicate_rule and duplicate_of on every record that repeats another one.

    Rules run in the order of DUPLICATE_RULES. Blurred records only match on iNaturalist ID.
    """
    for record in records:
        record["duplicate_rule"] = ""
        record["duplicate_of"] = ""

    first_seen: dict[str, dict[str, Any]] = {}
    for record in records:
        if record["record_id"] in first_seen:
            _mark(record, "repeated_download", first_seen[record["record_id"]])
        else:
            first_seen[record["record_id"]] = record

    inat_records = {
        record["inat_id"]: record
        for record in records
        if record["source"] == "iNaturalist" and not record["duplicate_rule"]
    }
    for record in records:
        if record["source"] == "GBIF" and record["inat_id"] in inat_records:
            original = inat_records[record["inat_id"]]
            _mark(record, "gbif_inat_overlap", original)
            if record["coordinates_obscured"] and not original["coordinates_obscured"]:
                original["coordinates_obscured"] = True
                original["latitude"], original["longitude"], original["cell_id"] = None, None, ""

    _same_find(records, "GBIF", "same_find_gbif", max_distance_m)
    _same_find(records, "iNaturalist", "same_find_inat", max_distance_m)


def _inside(record: dict[str, Any], box: dict[str, float]) -> bool:
    return (
        box["south"] <= record["latitude"] <= box["north"]
        and box["west"] <= record["longitude"] <= box["east"]
    )


def first_failed_filter(
    *, record: dict[str, Any], filters: dict[str, Any], download_date: str
) -> str:
    """Return the name of the first filter the record fails, or an empty string."""
    # Soil and DNA samples show the fungus is in the ground, not that a mushroom grew.
    if record["basis_of_record"] in filters["not_find_kinds"]:
        return "not_a_find"
    if record["date_precision"] != "day" or not record["event_date"]:
        return "no_full_date"
    if not filters["earliest_date"] <= record["event_date"] <= download_date:
        return "odd_date"
    if record["coordinates_obscured"]:
        return "blurred"
    issues = set(filter(None, (record["gbif_issues"] or "").split(";")))
    if (
        record["latitude"] is None
        or issues & set(filters["bad_gbif_issues"])
        or not _inside(record, filters["area_boxes"][record["area"]])
    ):
        return "odd_place"
    uncertainty = record["coordinate_uncertainty_m"]
    if uncertainty is not None and uncertainty > filters["max_uncertainty_m"]:
        return "low_accuracy"
    if record["identification_quality"] in WEAK_IDENTIFICATION:
        return "weak_identification"
    return ""


def apply_filters(
    *, records: list[dict[str, Any]], filters: dict[str, Any], download_date: str
) -> None:
    """Fill failed_filter on records that are not duplicates."""
    for record in records:
        record["failed_filter"] = (
            ""
            if record["duplicate_rule"]
            else first_failed_filter(record=record, filters=filters, download_date=download_date)
        )
