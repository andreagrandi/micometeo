"""Tests for the duplicate rules, the filters and the count tables."""

from typing import Any

import pytest

from micometeo.finds.cleaning import apply_filters, first_failed_filter, mark_duplicates
from micometeo.finds.counts import accuracy_class, count_table, dropped_table

FILTERS = {
    "not_find_kinds": ["MATERIAL_SAMPLE"],
    "earliest_date": "1990-01-01",
    "max_uncertainty_m": 1000,
    "bad_gbif_issues": ["ZERO_COORDINATE", "COUNTRY_COORDINATE_MISMATCH"],
    "area_boxes": {
        "home": {"west": 9.5, "south": 42.2, "east": 12.9, "north": 44.5},
        "comparison": {"west": 5.9, "south": 45.8, "east": 17.2, "north": 49.1},
    },
}
DOWNLOAD_DATE = "2026-10-10"


def find(**values: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "record_id": "inat:1",
        "source": "iNaturalist",
        "event_date": "2021-10-03",
        "date_precision": "day",
        "latitude": 44.0,
        "longitude": 10.9,
        "coordinate_uncertainty_m": 20.0,
        "coordinates_obscured": False,
        "identification_quality": "inat_research",
        "licence": "CC-BY",
        "cell_id": "500m_E1_N1",
        "area": "home",
        "in_pistoia": False,
        "year": 2021,
        "season": "autumn",
        "recorded_by": "walker",
        "basis_of_record": "HUMAN_OBSERVATION",
        "gbif_issues": "",
        "inat_id": "1",
        "duplicate_of": "",
    }
    record.update(values)
    return record


def test_same_record_from_two_place_queries_counts_once() -> None:
    records = [find(), find()]
    mark_duplicates(records=records, max_distance_m=100)
    assert [record["duplicate_rule"] for record in records] == ["", "repeated_download"]


def test_gbif_copy_of_inat_record_is_a_duplicate() -> None:
    inat = find()
    copy = find(record_id="gbif:9", source="GBIF", recorded_by="Walker W.")
    records = [copy, inat]
    mark_duplicates(records=records, max_distance_m=100)
    assert copy["duplicate_rule"] == "gbif_inat_overlap"
    assert copy["duplicate_of"] == "inat:1"
    assert inat["duplicate_rule"] == ""


def test_blurred_gbif_copy_blurs_the_kept_inat_record() -> None:
    inat = find()
    copy = find(
        record_id="gbif:9", source="GBIF", coordinates_obscured=True, latitude=None, longitude=None
    )
    mark_duplicates(records=[inat, copy], max_distance_m=100)
    assert inat["coordinates_obscured"] is True
    assert inat["latitude"] is None
    assert inat["cell_id"] == ""


@pytest.mark.parametrize(
    ("source", "rule"), [("GBIF", "same_find_gbif"), ("iNaturalist", "same_find_inat")]
)
def test_same_person_same_day_close_by_is_one_find(source: str, rule: str) -> None:
    first = find(record_id=f"{source}:1", source=source, inat_id="")
    near = find(record_id=f"{source}:2", source=source, inat_id="", latitude=44.0005)
    far = find(record_id=f"{source}:3", source=source, inat_id="", latitude=44.01)
    other_day = find(record_id=f"{source}:4", source=source, inat_id="", event_date="2021-10-04")
    records = [first, near, far, other_day]
    mark_duplicates(records=records, max_distance_m=100)
    assert [record["duplicate_rule"] for record in records] == ["", rule, "", ""]
    assert near["duplicate_of"] == first["record_id"]


def test_blurred_records_never_match_on_position() -> None:
    first = find(record_id="inat:1", inat_id="1")
    blurred = find(
        record_id="inat:2", inat_id="2", coordinates_obscured=True, latitude=None, longitude=None
    )
    mark_duplicates(records=[first, blurred], max_distance_m=100)
    assert blurred["duplicate_rule"] == ""


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({}, ""),
        ({"basis_of_record": "MATERIAL_SAMPLE", "event_date": ""}, "not_a_find"),
        ({"basis_of_record": "PRESERVED_SPECIMEN"}, ""),
        ({"date_precision": "month", "event_date": ""}, "no_full_date"),
        ({"event_date": "1985-09-01"}, "odd_date"),
        ({"event_date": "2027-01-01"}, "odd_date"),
        ({"coordinates_obscured": True, "latitude": None, "longitude": None}, "blurred"),
        ({"gbif_issues": "ZERO_COORDINATE;OTHER"}, "odd_place"),
        ({"latitude": 47.0}, "odd_place"),
        ({"coordinate_uncertainty_m": 1500.0}, "low_accuracy"),
        ({"coordinate_uncertainty_m": None}, ""),
        ({"identification_quality": "inat_needs_id"}, "weak_identification"),
        ({"identification_quality": "inat_casual"}, "weak_identification"),
        ({"identification_quality": "gbif_other_source"}, ""),
    ],
)
def test_each_filter(values: dict[str, Any], expected: str) -> None:
    record = find(**values)
    assert first_failed_filter(record=record, filters=FILTERS, download_date=DOWNLOAD_DATE) == expected


def test_filters_stop_at_the_first_failure() -> None:
    record = find(
        event_date="1985-09-01",
        coordinates_obscured=True,
        coordinate_uncertainty_m=5000.0,
        identification_quality="inat_casual",
    )
    assert first_failed_filter(record=record, filters=FILTERS, download_date=DOWNLOAD_DATE) == "odd_date"


def test_duplicates_are_not_filtered() -> None:
    records = [find(), find(identification_quality="inat_casual")]
    mark_duplicates(records=records, max_distance_m=100)
    apply_filters(records=records, filters=FILTERS, download_date=DOWNLOAD_DATE)
    assert [record["failed_filter"] for record in records] == ["", ""]


@pytest.mark.parametrize(
    ("uncertainty", "expected"),
    [(None, "unknown"), (100.0, "up_to_100m"), (101.0, "101_to_1000m"), (1001.0, "above_1000m")],
)
def test_accuracy_class(uncertainty: float | None, expected: str) -> None:
    assert accuracy_class(uncertainty_m=uncertainty) == expected


def cleaned_records() -> list[dict[str, Any]]:
    records = [
        find(record_id="inat:1", inat_id="1", in_pistoia=True),
        find(record_id="gbif:1", source="GBIF", inat_id="1"),
        find(
            record_id="inat:2",
            inat_id="2",
            recorded_by="another_walker",
            identification_quality="inat_casual",
        ),
        find(record_id="inat:3", inat_id="3", area="comparison", latitude=47.0, longitude=8.0),
    ]
    mark_duplicates(records=records, max_distance_m=100)
    apply_filters(records=records, filters=FILTERS, download_date=DOWNLOAD_DATE)
    return records


def test_count_table_totals_per_area_and_stage() -> None:
    rows = count_table(records=cleaned_records())
    totals = {
        (row["area"], row["stage"]): row["records"] for row in rows if row["dimension"] == "total"
    }
    assert totals == {
        ("home", "all"): 3,
        ("home", "after_duplicates"): 2,
        ("home", "eligible"): 1,
        ("pistoia", "all"): 1,
        ("pistoia", "after_duplicates"): 1,
        ("pistoia", "eligible"): 1,
        ("comparison", "all"): 1,
        ("comparison", "after_duplicates"): 1,
        ("comparison", "eligible"): 1,
    }
    dimensions = {row["dimension"] for row in rows}
    assert dimensions == {
        "total",
        "year",
        "season",
        "source",
        "location_accuracy",
        "blurred",
        "identification_quality",
        "licence",
    }


def test_dropped_table_counts_each_rule_and_filter() -> None:
    rows = dropped_table(records=cleaned_records())
    home = {row["step"]: row["records"] for row in rows if row["area"] == "home"}
    assert home["gbif_inat_overlap"] == 1
    assert home["weak_identification"] == 1
    assert home["blurred"] == 0
