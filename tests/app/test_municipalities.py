"""Checks for municipality borders and the municipality stored with each grid square."""

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path
from unittest.mock import patch

import psycopg
import pytest
import shapefile
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.management import CommandError, call_command
from shapely.geometry import MultiPolygon as ShapelyMultiPolygon
from shapely.geometry import box

from micometeo.finds.grid import format_cell_id
from national_grid.models import (
    GridBuild,
    GridBuildCell,
    GridCell,
    GridChunk,
    GridRegion,
    Municipality,
)
from national_grid.source import (
    BoundarySourceError,
    MunicipalityBoundary,
    read_municipalities,
)

COMMAND_MODULE = "national_grid.management.commands.load_municipalities"
WEST = 4_300_000
SOUTH = 2_300_000
UTM_PROJECTION = (
    'PROJCS["WGS_1984_UTM_Zone_32N",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
    'SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["Degree",'
    '0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",'
    '500000],PARAMETER["False_Northing",0],PARAMETER["Central_Meridian",9],PARAMETER['
    '"Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0],UNIT["Meter",1]]'
)


def _write_municipality_zip(path: Path, *, with_municipalities: bool = True) -> str:
    stem = path.with_suffix("")
    writer = shapefile.Writer(str(stem))
    writer.field("COD_REG", "N", decimal=0)
    writer.field("PRO_COM_T", "N", decimal=0)
    writer.field("COMUNE", "C")
    for code, region, name, west in ((47007, 9, "Marliana", 500_000), (1001, 1, "Agliè", 600_000)):
        writer.poly([[[west, 4_800_000], [west + 1_000, 4_800_000], [west + 1_000, 4_801_000],
                      [west, 4_801_000], [west, 4_800_000]]])
        writer.record(region, code, name)
    writer.close()
    stem.with_suffix(".prj").write_text(UTM_PROJECTION, encoding="utf-8")
    with zipfile.ZipFile(path, "w") as archive:
        if with_municipalities:
            for suffix in (".shp", ".shx", ".dbf", ".prj"):
                archive.write(stem.with_suffix(suffix), f"Com01012026/Com01012026_WGS84{suffix}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_read_municipalities_keeps_one_region_with_six_digit_codes(tmp_path: Path) -> None:
    archive_path = tmp_path / "boundaries.zip"
    expected_hash = _write_municipality_zip(archive_path)

    municipalities = read_municipalities(
        archive_path=archive_path, region_code="09", expected_sha256=expected_hash
    )

    assert [(item.istat_code, item.name, item.region_code) for item in municipalities] == [
        ("047007", "Marliana", "09")
    ]
    assert municipalities[0].geometry.geom_type == "MultiPolygon"
    assert municipalities[0].geometry.bounds[0] > 4_000_000


def test_read_municipalities_rejects_a_changed_hash_and_missing_members(tmp_path: Path) -> None:
    archive_path = tmp_path / "boundaries.zip"
    expected_hash = _write_municipality_zip(archive_path)
    with pytest.raises(BoundarySourceError, match="hash mismatch"):
        read_municipalities(archive_path=archive_path, region_code="09", expected_sha256="0" * 64)

    missing_path = tmp_path / "missing" / "boundaries.zip"
    missing_path.parent.mkdir()
    missing_hash = _write_municipality_zip(missing_path, with_municipalities=False)
    with pytest.raises(BoundarySourceError, match="missing members"):
        read_municipalities(archive_path=missing_path, region_code="09", expected_sha256=missing_hash)
    assert expected_hash != missing_hash


def _boundary(*, code: str, name: str, east_from: int, east_to: int) -> MunicipalityBoundary:
    return MunicipalityBoundary(
        istat_code=code,
        name=name,
        region_code="09",
        geometry=ShapelyMultiPolygon([box(WEST + east_from, SOUTH, WEST + east_to, SOUTH + 500)]),
    )


def _square(*, index: int, build: GridBuild, chunk: GridChunk, region: GridRegion) -> str:
    west = WEST + index * 500
    geometry = Polygon.from_bbox((west, SOUTH, west + 500, SOUTH + 500))
    geometry.srid = 3035
    cell = GridCell.objects.create(
        cell_id=format_cell_id(corner_e=west, corner_n=SOUTH),
        corner_e=west,
        corner_n=SOUTH,
        geometry=geometry,
    )
    GridBuildCell.objects.create(
        build=build,
        cell=cell,
        chunk=chunk,
        owner_region=region,
        land_geometry=MultiPolygon(geometry, srid=3035),
        land_share=1.0,
    )
    return cell.cell_id


@pytest.fixture
def squares() -> dict[str, str]:
    """Create five squares side by side: inside, split, tied, outside and in another region."""
    build = GridBuild.objects.create(version="municipality-grid", fingerprint="a" * 64)
    chunk = GridChunk.objects.create(
        build=build, west_e=WEST, south_n=SOUTH, east_e=WEST + 3000, north_n=SOUTH + 500
    )
    footprint = MultiPolygon(
        Polygon.from_bbox((WEST, SOUTH, WEST + 3000, SOUTH + 500)), srid=3035
    )
    tuscany = GridRegion.objects.create(
        build=build, istat_code="09", name="Toscana", geometry=footprint
    )
    other = GridRegion.objects.create(
        build=build, istat_code="10", name="Umbria", geometry=footprint
    )
    return {
        "inside": _square(index=0, build=build, chunk=chunk, region=tuscany),
        "split": _square(index=1, build=build, chunk=chunk, region=tuscany),
        "tied": _square(index=2, build=build, chunk=chunk, region=tuscany),
        "outside": _square(index=3, build=build, chunk=chunk, region=tuscany),
        "other_region": _square(index=4, build=build, chunk=chunk, region=other),
    }


def _run_command(*, boundaries: tuple[MunicipalityBoundary, ...]) -> dict[str, int]:
    out = io.StringIO()
    with patch(f"{COMMAND_MODULE}.read_municipalities", return_value=boundaries):
        call_command("load_municipalities", stdout=out)
    return json.loads(out.getvalue())


def _stored_names() -> dict[str, str | None]:
    return {
        cell.cell_id: cell.municipality_id for cell in GridCell.objects.order_by("cell_id")
    }


# Squares are 500 m wide. Zero is the west edge of the first square.
BOUNDARIES = (
    _boundary(code="100002", name="Alpha", east_from=0, east_to=800),
    _boundary(code="100003", name="Beta", east_from=800, east_to=1250),
    _boundary(code="100001", name="Gamma", east_from=1250, east_to=1500),
)


@pytest.mark.django_db
def test_load_municipalities_assigns_largest_overlap_then_lowest_code(
    squares: dict[str, str],
) -> None:
    result = _run_command(boundaries=BOUNDARIES)

    stored = _stored_names()
    assert stored[squares["inside"]] == "100002"
    assert stored[squares["split"]] == "100002"
    assert stored[squares["tied"]] == "100001"
    assert stored[squares["outside"]] is None
    assert stored[squares["other_region"]] is None
    assert result == {
        "municipalities_created": 3,
        "municipalities_updated": 0,
        "municipalities_unchanged": 0,
        "squares_assigned": 3,
        "squares_changed": 0,
        "squares_without_municipality": 1,
    }


@pytest.mark.django_db
def test_load_municipalities_second_run_changes_nothing(squares: dict[str, str]) -> None:
    _run_command(boundaries=BOUNDARIES)
    before = _stored_names()

    second = _run_command(boundaries=BOUNDARIES)

    assert second == {
        "municipalities_created": 0,
        "municipalities_updated": 0,
        "municipalities_unchanged": 3,
        "squares_assigned": 0,
        "squares_changed": 0,
        "squares_without_municipality": 1,
    }
    assert _stored_names() == before


@pytest.mark.django_db
def test_load_municipalities_updates_a_renamed_municipality_and_moves_squares(
    squares: dict[str, str],
) -> None:
    _run_command(boundaries=BOUNDARIES)
    renamed = _boundary(code="100001", name="Gamma renamed", east_from=1400, east_to=1500)

    result = _run_command(boundaries=(*BOUNDARIES[:2], renamed))

    assert Municipality.objects.get(istat_code="100001").name == "Gamma renamed"
    assert result["municipalities_updated"] == 1
    assert result["municipalities_unchanged"] == 2
    # Gamma now covers 100 m of the third square and Beta 250 m.
    assert result["squares_changed"] == 1
    assert _stored_names()[squares["tied"]] == "100003"


@pytest.mark.django_db
def test_load_municipalities_reports_a_source_error_as_a_command_error() -> None:
    with pytest.raises(CommandError, match="does not exist"):
        call_command("load_municipalities", archive_path="/nonexistent/boundaries.zip")


def _real_database_rows() -> tuple[int, int]:
    """Count region 09 squares and those without a municipality in the configured database."""
    try:
        with psycopg.connect(
            dbname=os.getenv("MICOMETEO_DB_NAME", "micometeo"),
            user=os.getenv("MICOMETEO_DB_USER", "micometeo"),
            password=os.getenv("MICOMETEO_DB_PASSWORD", "replace-with-a-local-password"),
            host=os.getenv("MICOMETEO_DB_HOST", "127.0.0.1"),
            port=os.getenv("MICOMETEO_DB_PORT", "5542"),
            connect_timeout=5,
        ) as connection:
            return connection.execute(
                """
                SELECT count(*), count(*) FILTER (WHERE cell.municipality_id IS NULL)
                FROM national_grid_gridcell AS cell
                WHERE cell.cell_id IN (
                    SELECT build_cell.cell_id
                    FROM national_grid_gridbuildcell AS build_cell
                    JOIN national_grid_gridregion AS region ON region.id = build_cell.owner_region_id
                    WHERE region.istat_code = '09'
                )
                """
            ).fetchone()
    except psycopg.Error as exc:
        pytest.skip(f"The configured database cannot be read: {exc}")


def test_every_tuscan_square_in_the_configured_database_has_a_municipality() -> None:
    """Read the real database directly, because the test database is always empty."""
    squares, without = _real_database_rows()
    if not squares:
        pytest.skip("The configured database holds no Tuscan squares")
    assert without == 0
