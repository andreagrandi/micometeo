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
    assert json.loads(inat_source["licence"]) == {"CC-BY-NC": 3}
    assert len(finished_run["state"]["outputs"]) == 6
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
    assert totals[("home", "all")] == 5
    assert totals[("home", "after_duplicates")] == 4
    assert totals[("home", "eligible")] == 1
    assert totals[("pistoia", "eligible")] == 1
    assert totals[("comparison", "eligible")] == 2
    with (reports / "p1_dropped.csv").open(encoding="utf-8") as handle:
        home = {row["step"]: int(row["records"]) for row in csv.DictReader(handle) if row["area"] == "home"}
    assert home["gbif_inat_overlap"] == 1
    assert home["blurred"] == 2
    assert home["weak_identification"] == 1
    assert (reports / "p1_map.png").stat().st_size > 0


def test_no_output_holds_a_blurred_position(finished_run: dict[str, Any]) -> None:
    tmp_path = finished_run["tmp_path"]
    for name in ("all_records.parquet", "finds.parquet"):
        table = pq.read_table(tmp_path / "processed" / name).to_pylist()
        for row in table:
            assert row["latitude"] != pytest.approx(BLURRED_LATITUDE)
            assert row["longitude"] != pytest.approx(BLURRED_LONGITUDE)
        blurred = [row for row in table if row["coordinates_obscured"]]
        assert all(row["latitude"] is None and row["cell_id"] == "" for row in blurred)
    for path in [*(tmp_path / "reports").iterdir(), tmp_path / "state.json"]:
        text = path.read_bytes().decode("utf-8", errors="ignore")
        assert "43.123" not in text
        assert "11.765" not in text
