"""Tests for GBIF and iNaturalist parsing, blurred positions and grid IDs."""

import json
import zipfile
from pathlib import Path

import pytest

from micometeo.finds import gbif, inaturalist
from micometeo.finds.grid import cell_id
from micometeo.finds.records import licence_code

SETTINGS = {
    "gbif_taxon_keys": [5954958, 8733688, 5954691, 5954949],
    "inat_taxon_ids": [48701, 333772, 350216, 335942],
    "tuscany_gid": "ITA.16_1",
    "pistoia_gid": "ITA.16.8_1",
    "emilia_apennines": {
        "gid": "ITA.6_1",
        "west": 9.0,
        "south": 43.5,
        "east": 13.0,
        "north": 44.3,
    },
    "comparison_countries": ["CH", "AT"],
    "inat_pistoia_place_id": 33195,
}
RETRIEVED_AT = "2026-10-10T16:00:00Z"
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
    "dataGeneralizations",
    "license",
    "rightsHolder",
    "recordedBy",
    "basisOfRecord",
    "issue",
    "countryCode",
    "level2Gid",
]


def gbif_row(**values: str) -> dict[str, str]:
    row = dict.fromkeys(GBIF_COLUMNS, "")
    row.update(
        gbifID="1",
        datasetKey="other-dataset",
        scientificName="Boletus edulis Bull.",
        taxonKey="5954958",
        year="2021",
        month="10",
        day="3",
        decimalLatitude="44.05",
        decimalLongitude="10.85",
        coordinateUncertaintyInMeters="25",
        license="http://creativecommons.org/licenses/by-nc/4.0/legalcode",
        countryCode="IT",
        level2Gid="ITA.16.8_1",
        basisOfRecord="HUMAN_OBSERVATION",
    )
    row.update(values)
    return row


def inat_observation(**values: object) -> dict[str, object]:
    observation: dict[str, object] = {
        "id": 101,
        "observed_on": "2020-09-15",
        "location": "43.95,10.9",
        "public_positional_accuracy": 12,
        "obscured": False,
        "geoprivacy": None,
        "taxon_geoprivacy": "open",
        "quality_grade": "research",
        "license_code": "cc-by",
        "user": {"login": "walker"},
        "taxon": {"id": 48701, "name": "Boletus edulis"},
        "place_ids": [13073, 33195],
    }
    observation.update(values)
    return observation


def test_gbif_row_becomes_find_record() -> None:
    record = gbif.parse_row(row=gbif_row(), settings=SETTINGS, retrieved_at=RETRIEVED_AT)
    assert record["record_id"] == "gbif:1"
    assert record["event_date"] == "2021-10-03"
    assert record["season"] == "autumn"
    assert record["latitude"] == pytest.approx(44.05)
    assert record["coordinates_obscured"] is False
    assert record["licence"] == "CC-BY-NC"
    assert record["area"] == "home"
    assert record["in_pistoia"] is True
    assert record["identification_quality"] == "gbif_other_source"
    assert record["cell_id"].startswith("500m_E")


@pytest.mark.parametrize(
    "field", ["informationWithheld", "dataGeneralizations"]
)
def test_gbif_blurred_record_loses_its_position(field: str) -> None:
    row = gbif_row(**{field: "Coordinate uncertainty increased to 28000 m"})
    record = gbif.parse_row(row=row, settings=SETTINGS, retrieved_at=RETRIEVED_AT)
    assert record["coordinates_obscured"] is True
    assert record["latitude"] is None
    assert record["longitude"] is None
    assert record["cell_id"] == ""


def test_gbif_inat_copy_keeps_inat_id_and_research_grade() -> None:
    row = gbif_row(
        datasetKey=gbif.INAT_DATASET_KEY,
        occurrenceID="https://www.inaturalist.org/observations/101",
    )
    record = gbif.parse_row(row=row, settings=SETTINGS, retrieved_at=RETRIEVED_AT)
    assert record["inat_id"] == "101"
    assert record["identification_quality"] == "inat_research"


def test_gbif_partial_dates_have_no_event_date() -> None:
    month_only = gbif.parse_row(
        row=gbif_row(day=""), settings=SETTINGS, retrieved_at=RETRIEVED_AT
    )
    no_date = gbif.parse_row(
        row=gbif_row(year="", month="", day=""), settings=SETTINGS, retrieved_at=RETRIEVED_AT
    )
    assert (month_only["event_date"], month_only["date_precision"]) == ("", "month")
    assert (no_date["event_date"], no_date["date_precision"]) == ("", "none")


def test_gbif_comparison_country_sets_area() -> None:
    record = gbif.parse_row(
        row=gbif_row(countryCode="CH", level2Gid=""),
        settings=SETTINGS,
        retrieved_at=RETRIEVED_AT,
    )
    assert record["area"] == "comparison"
    assert record["in_pistoia"] is False


def test_gbif_archive_is_read_from_zip(tmp_path: Path) -> None:
    rows = [gbif_row(), gbif_row(gbifID="2", informationWithheld="blurred")]
    lines = ["\t".join(GBIF_COLUMNS)]
    lines += ["\t".join(row[column] for column in GBIF_COLUMNS) for row in rows]
    zip_path = tmp_path / "gbif.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("occurrence.txt", "\n".join(lines) + "\n")
    records = gbif.parse_archive(zip_path=zip_path, settings=SETTINGS, retrieved_at=RETRIEVED_AT)
    assert [record["record_id"] for record in records] == ["gbif:1", "gbif:2"]
    assert records[1]["latitude"] is None


def test_gbif_predicate_covers_species_and_both_areas() -> None:
    predicate = gbif.build_predicate(settings=SETTINGS)
    taxa, has_coordinate, areas = predicate["predicates"]
    assert taxa == {
        "type": "in",
        "key": "TAXON_KEY",
        "values": ["5954958", "8733688", "5954691", "5954949"],
    }
    assert has_coordinate["key"] == "HAS_COORDINATE"
    tuscany, emilia, countries = areas["predicates"]
    assert tuscany == {"type": "equals", "key": "GADM_GID", "value": "ITA.16_1"}
    assert emilia["predicates"][1]["geometry"] == (
        "POLYGON((9.0 43.5,13.0 43.5,13.0 44.3,9.0 44.3,9.0 43.5))"
    )
    assert countries["values"] == ["CH", "AT"]


def test_gbif_login_error_names_missing_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in gbif.LOGIN_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GBIF_USERNAME", "someone")
    with pytest.raises(RuntimeError, match="GBIF_PASSWORD, GBIF_EMAIL"):
        gbif.read_login()


def test_inat_observation_becomes_find_record() -> None:
    record = inaturalist.parse_observation(
        observation=inat_observation(),
        area="home",
        settings=SETTINGS,
        retrieved_at=RETRIEVED_AT,
    )
    assert record["record_id"] == "inat:101"
    assert record["latitude"] == pytest.approx(43.95)
    assert record["coordinate_uncertainty_m"] == 12
    assert record["identification_quality"] == "inat_research"
    assert record["licence"] == "CC-BY"
    assert record["in_pistoia"] is True
    assert record["recorded_by"] == "walker"


@pytest.mark.parametrize(
    "values",
    [
        {"obscured": True},
        {"geoprivacy": "obscured"},
        {"geoprivacy": "private", "location": None},
        {"taxon_geoprivacy": "obscured"},
    ],
)
def test_inat_blurred_observation_loses_its_position(values: dict[str, object]) -> None:
    record = inaturalist.parse_observation(
        observation=inat_observation(**values),
        area="home",
        settings=SETTINGS,
        retrieved_at=RETRIEVED_AT,
    )
    assert record["coordinates_obscured"] is True
    assert record["latitude"] is None
    assert record["longitude"] is None
    assert record["cell_id"] == ""


def test_inat_pages_keep_only_points_south_of_limit(tmp_path: Path) -> None:
    path = tmp_path / "page.json"
    page = {
        "results": [
            inat_observation(id=1, location="44.1,11.0"),
            inat_observation(id=2, location="44.6,11.0"),
            inat_observation(id=3, location=None),
        ]
    }
    path.write_text(json.dumps(page), encoding="utf-8")
    records = inaturalist.parse_pages(
        paths=[path],
        area="home",
        settings=SETTINGS,
        retrieved_at=RETRIEVED_AT,
        max_latitude=44.3,
    )
    assert [record["record_id"] for record in records] == ["inat:1"]


def test_inat_download_follows_pages_and_reuses_saved_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full_page = {"results": [{"id": number} for number in range(1, 201)]}
    (tmp_path / "inat_tuscany_001.json").write_text(json.dumps(full_page), encoding="utf-8")
    requested: list[str] = []

    class Reply:
        def __enter__(self) -> "Reply":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"results": [{"id": 201}]}).encode()

    def fake_urlopen(request: object, timeout: float) -> Reply:
        requested.append(request.full_url)
        return Reply()

    monkeypatch.setattr(inaturalist.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(inaturalist, "PAUSE_SECONDS", 0)
    paths = inaturalist.download_place(
        settings=SETTINGS, place_name="tuscany", place_id=13073, raw_dir=tmp_path
    )
    assert [path.name for path in paths] == ["inat_tuscany_001.json", "inat_tuscany_002.json"]
    assert len(requested) == 1
    assert "id_above=200" in requested[0]


def test_cell_id_matches_epsg_3035_grid() -> None:
    assert cell_id(latitude=52.0, longitude=10.0) == "500m_E4321000_N3210000"


def test_cell_id_builds_larger_squares_with_the_same_format() -> None:
    assert cell_id(latitude=52.0, longitude=10.0, size_m=10000) == "10000m_E4320000_N3210000"
    assert cell_id(latitude=52.0, longitude=10.0, size_m=30000) == "30000m_E4320000_N3210000"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("cc-by-nc", "CC-BY-NC"),
        ("cc0", "CC0"),
        ("http://creativecommons.org/licenses/by/4.0/legalcode", "CC-BY"),
        ("http://creativecommons.org/publicdomain/zero/1.0/legalcode", "CC0"),
        ("cc-by-nc-sa", "CC-BY-NC-SA"),
        (None, "other"),
        ("all rights reserved", "other"),
    ],
)
def test_licence_code(value: str | None, expected: str) -> None:
    assert licence_code(value=value) == expected
