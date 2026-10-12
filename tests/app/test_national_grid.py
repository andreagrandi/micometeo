"""Focused offline and PostGIS checks for the national grid application."""

import hashlib
import json
import zipfile
from datetime import date
from pathlib import Path

import pytest
import shapefile
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Point, Polygon

from micometeo.finds.grid import CELL_SIZE_M, cell_id, parse_cell_id
from national_grid.geometry import GridChunkBounds, cells_for_chunk
from national_grid.lookups import lookup_national_grid
from national_grid.models import GridBuild, GridBuildCell
from national_grid.services import BuildInputMismatchError, build_national_grid
from national_grid.source import (
    GRID_CRS,
    LICENSE_URL,
    OFFICIAL_URL,
    SOURCE_CRS,
    BoundarySource,
    RegionBoundary,
    read_boundary_source,
)


def _synthetic_source(*, archive_sha256: str = "0" * 64) -> BoundarySource:
    regions = tuple(
        RegionBoundary(
            istat_code=f"{index:02d}",
            name=f"Region {index:02d}",
            geometry=MultiPolygon(
                [
                    Polygon(
                        [
                            (4_000_000 + column * 1_000, 2_000_000 + row * 1_000),
                            (4_000_000 + (column + 1) * 1_000, 2_000_000 + row * 1_000),
                            (4_000_000 + (column + 1) * 1_000, 2_000_000 + (row + 1) * 1_000),
                            (4_000_000 + column * 1_000, 2_000_000 + (row + 1) * 1_000),
                            (4_000_000 + column * 1_000, 2_000_000 + row * 1_000),
                        ]
                    )
                ]
            ),
        )
        for index, (row, column) in enumerate((
            (row, column) for row in range(4) for column in range(5)
        ), start=1)
    )
    return BoundarySource(
        regions=regions,
        metadata={
            "dataset": "synthetic ISTAT fixture",
            "version": "test",
            "archive_sha256": archive_sha256,
            "members": ["Reg01012026/Reg01012026_WGS84.shp"],
            "source_crs": SOURCE_CRS,
            "grid_crs": GRID_CRS,
        },
    )


def _write_synthetic_zip(path: Path) -> str:
    stem = path.with_suffix("")
    writer = shapefile.Writer(str(stem))
    writer.field("COD_REG", "N", decimal=0)
    writer.field("DEN_REG", "C")
    for index in range(1, 21):
        row, column = divmod(index - 1, 5)
        west = 500_000 + column * 1_000
        south = 4_500_000 + row * 1_000
        writer.poly(
            [[
                [west, south],
                [west + 1_000, south],
                [west + 1_000, south + 1_000],
                [west, south + 1_000],
                [west, south],
            ]]
        )
        writer.record(index, f"Region {index}")
    writer.close()
    stem.with_suffix(".prj").write_text(
        'PROJCS["WGS_1984_UTM_Zone_32N",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
        'SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["Degree",'
        '0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",'
        '500000],PARAMETER["False_Northing",0],PARAMETER["Central_Meridian",9],PARAMETER['
        '"Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0],UNIT["Meter",1]]',
        encoding="utf-8",
    )
    with zipfile.ZipFile(path, "w") as archive:
        for suffix in (".shp", ".shx", ".dbf", ".prj"):
            archive.write(stem.with_suffix(suffix), f"Reg01012026/Reg01012026_WGS84{suffix}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_boundary_source_validates_hash_crs_fields_and_twenty_regions(tmp_path: Path) -> None:
    archive_path = tmp_path / "boundaries.zip"
    expected_hash = _write_synthetic_zip(archive_path)
    source = read_boundary_source(
        archive_path=archive_path,
        expected_sha256=expected_hash,
        downloaded_on=date(2026, 10, 12),
    )
    assert len(source.regions) == 20
    assert {region.istat_code for region in source.regions} == {f"{index:02d}" for index in range(1, 21)}
    assert source.metadata["source_crs"] == SOURCE_CRS
    assert source.metadata["grid_crs"] == GRID_CRS
    assert source.metadata["downloaded_on"] == "2026-10-12"
    assert source.metadata["version"] == "2026-01-01"
    assert source.metadata["source_url"] == OFFICIAL_URL
    assert source.metadata["license_url"] == LICENSE_URL
    assert source.metadata["license"] == "CC BY 4.0 unless otherwise indicated"
    assert source.metadata["credit"].startswith("ISTAT")
    assert "transformed once" in source.metadata["transformation"]
    assert "gadm" not in json.dumps(source.metadata).lower()


def test_cell_id_and_stored_square_use_aligned_lower_left_corner() -> None:
    value = cell_id(latitude=42.0, longitude=12.0)
    address = parse_cell_id(value, expected_size_m=CELL_SIZE_M)
    assert address.corner_e % CELL_SIZE_M == 0
    assert address.corner_n % CELL_SIZE_M == 0
    assert value == f"500m_E{address.corner_e}_N{address.corner_n}"
    with pytest.raises(ValueError, match="aligned"):
        parse_cell_id("500m_E123_N456")


def test_positive_land_cells_keep_coastal_slivers_and_drop_sea_only_cells() -> None:
    region = RegionBoundary(
        istat_code="01",
        name="Test",
        geometry=MultiPolygon([Polygon([(0, 0), (250, 0), (250, 500), (0, 500), (0, 0)])]),
    )
    cells = cells_for_chunk(
        regions=[region],
        bounds=GridChunkBounds(west_e=-500, south_n=-500, east_e=500, north_n=500),
    )
    assert len(cells) == 1
    assert 0 < cells[0].land_share < 1


def test_boundary_fixture_covers_mainland_edge_coastal_sliver_island_and_two_islands() -> None:
    def region(*, code: str, name: str, west: int, width: int) -> RegionBoundary:
        return RegionBoundary(
            istat_code=code,
            name=name,
            geometry=MultiPolygon(
                [
                    Polygon(
                        [
                            (west, 0),
                            (west + width, 0),
                            (west + width, 500),
                            (west, 500),
                            (west, 0),
                        ]
                    )
                ]
            ),
        )

    cells = cells_for_chunk(
        regions=[
            region(code="01", name="Mainland", west=0, width=500),
            region(code="02", name="Coastal sliver", west=1_000, width=200),
            region(code="03", name="Small island", west=2_000, width=100),
            region(code="19", name="Sicilia", west=3_000, width=500),
            region(code="20", name="Sardegna", west=4_000, width=500),
        ],
        bounds=GridChunkBounds(west_e=0, south_n=0, east_e=4_500, north_n=500),
    )
    by_id = {cell.cell_id: cell for cell in cells}
    assert by_id["500m_E0_N0"].land_share == pytest.approx(1.0)
    assert by_id["500m_E1000_N0"].land_share == pytest.approx(0.4)
    assert not by_id["500m_E1000_N0"].land_geometry.contains(Point(1_250, 250))
    assert by_id["500m_E2000_N0"].land_share == pytest.approx(0.2)
    assert by_id["500m_E3000_N0"].owner_name == "Sicilia"
    assert by_id["500m_E4000_N0"].owner_name == "Sardegna"
    assert "500m_E500_N0" not in by_id


def test_region_border_owner_uses_largest_area_then_lowest_code_on_exact_tie() -> None:
    def rectangle(*, code: str, west: int, east: int) -> RegionBoundary:
        return RegionBoundary(
            istat_code=code,
            name=f"Region {code}",
            geometry=MultiPolygon(
                [Polygon([(west, 0), (east, 0), (east, 500), (west, 500), (west, 0)])]
            ),
        )

    cells = cells_for_chunk(
        regions=[
            rectangle(code="02", west=0, east=300),
            rectangle(code="01", west=300, east=500),
            rectangle(code="04", west=500, east=750),
            rectangle(code="03", west=750, east=1_000),
        ],
        bounds=GridChunkBounds(west_e=0, south_n=0, east_e=1_000, north_n=500),
    )
    by_id = {cell.cell_id: cell for cell in cells}
    assert by_id["500m_E0_N0"].owner_code == "02"
    assert by_id["500m_E500_N0"].owner_code == "03"


@pytest.mark.django_db(transaction=True)
def test_interrupted_build_resumes_without_duplicate_memberships() -> None:
    source = _synthetic_source()
    first = build_national_grid(
        archive_path=None,
        source=source,
        build_version="test-interrupted-v1",
        expected_sha256="0" * 64,
        downloaded_on="2026-10-12",
        chunk_size_m=2_500,
        max_chunks=1,
    )
    assert first.status == GridBuild.Status.RUNNING
    assert first.build.completed_chunk_count == 1
    second = build_national_grid(
        archive_path=None,
        source=source,
        build_version="test-interrupted-v1",
        expected_sha256="0" * 64,
        downloaded_on="2026-10-12",
        chunk_size_m=2_500,
    )
    assert second.status == GridBuild.Status.COMPLETED
    assert GridBuildCell.objects.filter(build=second.build).count() == second.build.cell_count
    assert GridBuildCell.objects.filter(build=second.build).values("cell_id").distinct().count() == second.build.cell_count
    assert len(second.regional_counts) == 20
    assert sum(item["cell_count"] for item in second.regional_counts) == second.build.cell_count


@pytest.mark.django_db(transaction=True)
def test_repeating_completed_build_reuses_ids_and_rejects_changed_fingerprint() -> None:
    source = _synthetic_source()
    first = build_national_grid(
        archive_path=None,
        source=source,
        build_version="test-rebuild-v1",
        expected_sha256="0" * 64,
        downloaded_on="2026-10-12",
        chunk_size_m=2_500,
    )
    first_ids = set(GridBuildCell.objects.filter(build=first.build).values_list("cell_id", flat=True))
    first_updated_at = first.build.updated_at
    repeated = build_national_grid(
        archive_path=None,
        source=source,
        build_version="test-rebuild-v1",
        expected_sha256="0" * 64,
        downloaded_on="2026-10-12",
        chunk_size_m=2_500,
    )
    repeated_ids = set(
        GridBuildCell.objects.filter(build=repeated.build).values_list("cell_id", flat=True)
    )
    assert repeated.status == GridBuild.Status.COMPLETED
    assert repeated.processed_chunks == 0
    assert repeated.reused_chunks == first.build.planned_chunk_count
    assert repeated_ids == first_ids
    assert repeated.build.updated_at == first_updated_at
    with pytest.raises(BuildInputMismatchError, match="different inputs"):
        build_national_grid(
            archive_path=None,
            source=_synthetic_source(archive_sha256="1" * 64),
            build_version="test-rebuild-v1",
            expected_sha256="0" * 64,
            downloaded_on="2026-10-12",
            chunk_size_m=2_500,
        )


@pytest.mark.django_db
def test_lookup_rejects_unfinished_build_and_invalid_coordinates() -> None:
    build = GridBuild.objects.create(
        version="test-pending-v1",
        fingerprint="1" * 64,
        source_metadata={},
    )
    pending = lookup_national_grid(
        cell_id="500m_E4000000_N2000000",
        build_version=build.version,
    )
    assert pending.status == "unfinished_build"
    assert lookup_national_grid(latitude=float("nan"), longitude=12.0).status == "invalid"
    assert lookup_national_grid(latitude=float("inf"), longitude=12.0).status == "invalid"
    assert lookup_national_grid(latitude=-float("inf"), longitude=12.0).status == "invalid"
    assert lookup_national_grid(latitude=91.0, longitude=12.0).status == "invalid"
    assert lookup_national_grid(latitude=45.0, longitude=181.0).status == "invalid"
    assert lookup_national_grid(cell_id="500m_E1_N2").status == "invalid"
    assert lookup_national_grid(
        cell_id="500m_E4000000_N2000000", build_version="does-not-exist"
    ).status == "unknown_build"


@pytest.mark.django_db(transaction=True)
def test_completed_build_lookup_returns_both_wgs84_geometries() -> None:
    source = _synthetic_source()
    result = build_national_grid(
        archive_path=None,
        source=source,
        build_version="test-completed-lookup-v1",
        expected_sha256="0" * 64,
        downloaded_on="2026-10-12",
        chunk_size_m=2_500,
    )
    membership = GridBuildCell.objects.filter(build=result.build).first()
    assert membership is not None
    lookup = lookup_national_grid(
        cell_id=membership.cell_id,
        build_version=result.build.version,
    )
    assert lookup.status == "found"
    assert lookup.owner_region is not None
    assert lookup.full_geometry is not None
    assert lookup.full_geometry["type"] == "Polygon"
    assert lookup.land_geometry is not None
    assert lookup.land_geometry["type"] == "MultiPolygon"
    centroid = membership.cell.geometry.centroid
    to_wgs84 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)
    longitude, latitude = to_wgs84.transform(centroid.x, centroid.y)
    by_coordinate = lookup_national_grid(
        latitude=latitude,
        longitude=longitude,
        build_version=result.build.version,
    )
    assert by_coordinate.status == "found"
    assert by_coordinate.cell_id == membership.cell_id
    outside = lookup_national_grid(
        latitude=0.0,
        longitude=0.0,
        build_version=result.build.version,
    )
    assert outside.status == "outside"
