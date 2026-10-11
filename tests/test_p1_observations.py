"""Offline run of the P1 experiment with the two downloads replaced by saved samples."""

import csv
import importlib.util
import json
import tomllib
import zipfile
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from micometeo.context import RunContext
from shapely.geometry import box

from micometeo.finds import gbif, inaturalist, roads

ROOT = Path(__file__).resolve().parent.parent
BLURRED_LATITUDE = 43.1234567
BLURRED_LONGITUDE = 11.7654321
# Published positions of three blurred records. They must never count as exact points.
HIDDEN_VALUES = [
    BLURRED_LATITUDE,
    BLURRED_LONGITUDE,
    43.5678,
    10.2345,
    47.3456789,
    8.654321,
]
GBIF_COLUMNS = [
    "gbifID",
    "datasetKey",
    "occurrenceID",
    "scientificName",
    "taxonKey",
    "year",
    "month",
    "day",
    "decimalLatitude",
    "decimalLongitude",
    "coordinateUncertaintyInMeters",
    "informationWithheld",
    "license",
    "recordedBy",
    "countryCode",
    "level2Gid",
    "issue",
]


def load_p1():
    spec = importlib.util.spec_from_file_location(
        "p1_run", ROOT / "experiments" / "p1_observations" / "run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observation(number: int, **values: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": number,
        "observed_on": "2020-09-15",
        "location": f"44.0{number},10.9",
        "public_positional_accuracy": 15,
        "obscured": False,
        "geoprivacy": None,
        "taxon_geoprivacy": None,
        "quality_grade": "research",
        "license_code": "cc-by-nc",
        "user": {"login": f"user{number}"},
        "taxon": {"id": 48701, "name": "Boletus edulis"},
        "place_ids": [13073],
    }
    item.update(values)
    return item


def fake_inat_download(
    *, settings: dict[str, Any], place_name: str, place_id: int, raw_dir: Path
) -> list[Path]:
    results = []
    if place_name == "tuscany":
        results = [
            observation(1, place_ids=[13073, 33195]),
            observation(
                2,
                obscured=True,
                geoprivacy="obscured",
                location=f"{BLURRED_LATITUDE},{BLURRED_LONGITUDE}",
            ),
            observation(3, quality_grade="needs_id"),
            observation(
                5,
                observed_on="2021-06-10",
                location="44.05,10.9",
                public_positional_accuracy=2500,
                place_ids=[13073, 33195],
            ),
            observation(
                6,
                obscured=True,
                geoprivacy="obscured",
                quality_grade="needs_id",
                location="43.5678,10.2345",
            ),
            observation(7, location="44.06,10.9", public_positional_accuracy=40000),
        ]
    if place_name == "switzerland":
        results = [observation(4, location="46.8,8.2")]
    path = raw_dir / f"inat_{place_name}_001.json"
    path.write_text(json.dumps({"results": results}), encoding="utf-8")
    return [path]


def fake_gbif_fetch(*, key: str, raw_dir: Path) -> tuple[Path, dict[str, Any]]:
    rows = [
        {
            "gbifID": "11",
            "datasetKey": gbif.INAT_DATASET_KEY,
            "occurrenceID": "https://www.inaturalist.org/observations/1",
            "year": "2020",
            "month": "9",
            "day": "15",
            "decimalLatitude": "44.01",
            "decimalLongitude": "10.9",
            "countryCode": "IT",
        },
        {
            "gbifID": "12",
            "datasetKey": "museum",
            "year": "2019",
            "month": "10",
            "day": "2",
            "decimalLatitude": str(BLURRED_LATITUDE),
            "decimalLongitude": str(BLURRED_LONGITUDE),
            "informationWithheld": "Coordinates generalised",
            "countryCode": "IT",
        },
        {
            "gbifID": "13",
            "datasetKey": "swiss-fungi",
            "year": "2018",
            "month": "8",
            "day": "20",
            "decimalLatitude": "47.1",
            "decimalLongitude": "9.0",
            "coordinateUncertaintyInMeters": "50",
            "license": "http://creativecommons.org/licenses/by/4.0/legalcode",
            "countryCode": "CH",
        },
    ]
    rows.append(
        {
            "gbifID": "14",
            "datasetKey": "swiss-fungi",
            "year": "2017",
            "month": "5",
            "day": "4",
            "decimalLatitude": "47.3456789",
            "decimalLongitude": "8.6543210",
            "coordinateUncertaintyInMeters": "3535",
            "informationWithheld": "Coordinates rounded to the 5 km grid",
            "countryCode": "CH",
        }
    )
    lines = ["\t".join(GBIF_COLUMNS)]
    lines += ["\t".join(row.get(column, "") for column in GBIF_COLUMNS) for row in rows]
    zip_path = raw_dir / f"gbif_{key}.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("occurrence.txt", "\n".join(lines) + "\n")
    status = {"doi": "10.15468/dl.test", "created": "2026-10-10T16:00:00.000+00:00"}
    return zip_path, status


@pytest.fixture
def finished_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr(inaturalist, "download_place", fake_inat_download)
    monkeypatch.setattr(gbif, "fetch_download", fake_gbif_fetch)
    monkeypatch.setattr(
        roads,
        "area_shapes",
        lambda *, settings, raw_dir: {
            "home": box(10.0, 43.0, 11.5, 44.3),
            "comparison": box(6.0, 46.0, 16.0, 48.5),
        },
    )
    extract_path = tmp_path / "extract.osm.pbf"
    extract_path.write_bytes(b"sample")
    monkeypatch.setattr(roads, "download_extract", lambda *, name, raw_dir: extract_path)
    monkeypatch.setattr(roads, "extract_date", lambda *, path: "2026-10-08T20:21:06Z")
    monkeypatch.setattr(roads, "ways_near_points", lambda *, paths, points: [])
    monkeypatch.setattr(
        roads,
        "nearest_distances",
        lambda *, points, ways, radius_m: [{"road": 500.0, "road_or_path": 50.0} for _ in points],
    )
    config = tomllib.loads(
        (ROOT / "experiments" / "p1_observations" / "config.toml").read_text(encoding="utf-8")
    )
    settings = config["settings"]
    settings["gbif_download_key"] = "test-key"
    settings["reports_dir"] = str(tmp_path / "reports")
    context = RunContext(
        config=settings,
        seed=42,
        run_id="test",
        raw_dir=tmp_path / "raw",
        output_dir=tmp_path / "processed",
        state_path=tmp_path / "state.json",
    )
    load_p1().run(context)
    return {
        "tmp_path": tmp_path,
        "state": json.loads((tmp_path / "state.json").read_text(encoding="utf-8")),
    }


def test_run_records_gbif_key_doi_and_inat_query(finished_run: dict[str, Any]) -> None:
    sources = finished_run["state"]["sources"]
    gbif_source = next(source for source in sources if source["name"].startswith("GBIF"))
    assert gbif_source["query"]["download_key"] == "test-key"
    assert gbif_source["version"] == "10.15468/dl.test"
    assert gbif_source["query"]["predicate"]["type"] == "and"
    inat_source = next(source for source in sources if source["name"].endswith("tuscany"))
    assert inat_source["query"]["place_id"] == 13073
    assert json.loads(inat_source["licence"]) == {"CC-BY-NC": 6}
    assert len(finished_run["state"]["outputs"]) == 7
    names = [source["name"] for source in sources]
    assert "OpenStreetMap extract italy/centro from Geofabrik" in names
    osm_source = next(source for source in sources if source["name"].endswith("austria from Geofabrik"))
    assert osm_source["version"] == "2026-10-08T20:21:06Z"
    assert osm_source["licence"] == "ODbL 1.0"


def test_run_writes_road_distance_table(finished_run: dict[str, Any]) -> None:
    path = finished_run["tmp_path"] / "reports" / "p1_road_distance.csv"
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 8
    home_finds = next(
        row
        for row in rows
        if (row["area"], row["group"], row["nearest"]) == ("home", "finds", "road_or_path")
    )
    assert home_finds["points"] == "1"
    assert home_finds["median_m"] == "50"
    assert home_finds["share_near"] == "1.0"


def test_run_counts_and_filters(finished_run: dict[str, Any]) -> None:
    reports = finished_run["tmp_path"] / "reports"
    with (reports / "p1_counts.csv").open(encoding="utf-8") as handle:
        totals = {
            (row["area"], row["stage"]): int(row["records"])
            for row in csv.DictReader(handle)
            if row["dimension"] == "total"
        }
    assert totals[("home", "all")] == 8
    assert totals[("home", "after_duplicates")] == 7
    assert totals[("home", "eligible")] == 1
    assert totals[("pistoia", "eligible")] == 1
    assert totals[("comparison", "eligible")] == 2
    assert totals[("home", "timing")] == 2
    assert totals[("pistoia", "timing")] == 1
    assert totals[("comparison", "timing")] == 1
    with (reports / "p1_dropped.csv").open(encoding="utf-8") as handle:
        home = {row["step"]: int(row["records"]) for row in csv.DictReader(handle) if row["area"] == "home"}
    assert home["gbif_inat_overlap"] == 1
    assert home["blurred"] == 3
    assert home["low_accuracy"] == 2
    assert home["weak_identification"] == 1
    assert (reports / "p1_map.png").stat().st_size > 0


def test_timing_table_has_squares_and_rough_points(finished_run: dict[str, Any]) -> None:
    table = pq.read_table(finished_run["tmp_path"] / "processed" / "timing_finds.parquet")
    assert table.column_names == [
        "record_id",
        "source",
        "area",
        "in_pistoia",
        "event_date",
        "year",
        "season",
        "species_group",
        "taxon_name",
        "square_id",
        "square_size_m",
        "rough_latitude",
        "rough_longitude",
        "failed_filter",
        "identification_quality",
        "licence",
    ]
    rows = {row["record_id"]: row for row in table.to_pylist()}
    assert sorted(rows) == ["gbif:14", "inat:2", "inat:5"]
    assert rows["inat:2"]["square_size_m"] == 30000
    assert rows["inat:2"]["square_id"].startswith("30000m_E")
    assert rows["inat:2"]["failed_filter"] == "blurred"
    assert rows["inat:2"]["rough_latitude"] == pytest.approx(BLURRED_LATITUDE)
    assert rows["inat:2"]["rough_longitude"] == pytest.approx(BLURRED_LONGITUDE)
    assert rows["inat:5"]["rough_latitude"] == pytest.approx(44.05)
    assert rows["gbif:14"]["rough_latitude"] == pytest.approx(47.3456789)
    assert rows["inat:5"]["square_size_m"] == 10000
    assert rows["inat:5"]["square_id"].startswith("10000m_E")
    assert rows["inat:5"]["failed_filter"] == "low_accuracy"
    assert rows["inat:5"]["in_pistoia"] is True
    assert rows["gbif:14"]["square_size_m"] == 10000
    assert rows["gbif:14"]["area"] == "comparison"
    assert {row["species_group"] for row in rows.values()} == {"porcini"}


def test_counts_hold_timing_finds_by_year_and_season(finished_run: dict[str, Any]) -> None:
    with (finished_run["tmp_path"] / "reports" / "p1_counts.csv").open(encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["stage"] == "timing"]
    counts = {
        (row["area"], row["dimension"], row["value"]): int(row["records"]) for row in rows
    }
    assert counts[("home", "year", "2020")] == 1
    assert counts[("home", "year", "2021")] == 1
    assert counts[("home", "season", "autumn")] == 1
    assert counts[("home", "season", "summer")] == 1
    assert counts[("pistoia", "year", "2021")] == 1
    assert counts[("comparison", "year", "2017")] == 1
    assert counts[("comparison", "season", "spring")] == 1


def test_all_records_hold_square_columns(finished_run: dict[str, Any]) -> None:
    table = pq.read_table(finished_run["tmp_path"] / "processed" / "all_records.parquet")
    rows = {row["record_id"]: row for row in table.to_pylist()}
    assert rows["inat:2"]["square_size_m"] == 30000
    assert rows["inat:6"]["square_id"] == ""
    assert rows["inat:7"]["square_size_m"] is None
    assert rows["inat:2"]["latitude"] is None
    assert rows["inat:2"]["published_latitude"] == pytest.approx(BLURRED_LATITUDE)
    assert rows["inat:2"]["published_longitude"] == pytest.approx(BLURRED_LONGITUDE)


def test_blurred_point_never_counts_as_an_exact_position(finished_run: dict[str, Any]) -> None:
    tmp_path = finished_run["tmp_path"]
    for name in ("all_records.parquet", "finds.parquet"):
        table = pq.read_table(tmp_path / "processed" / name).to_pylist()
        blurred = [row for row in table if row["coordinates_obscured"]]
        assert all(row["latitude"] is None and row["cell_id"] == "" for row in blurred)
        for row in table:
            assert all(row["latitude"] != pytest.approx(hidden) for hidden in HIDDEN_VALUES)
            assert all(row["longitude"] != pytest.approx(hidden) for hidden in HIDDEN_VALUES)
