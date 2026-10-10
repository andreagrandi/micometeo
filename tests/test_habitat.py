"""Offline tests for the P2a sample grid: grid, terrain, soil, rock type and real detail."""

import csv
import importlib.util
import json
import math
import tomllib
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
import pytest
import rasterio
from rasterio.transform import from_origin

from micometeo.context import RunContext
from micometeo.finds.grid import cell_id
from micometeo.habitat import detail, rock, soil, terrain
from micometeo.habitat.grid import (
    PIXEL_SIZE_M,
    SampleGrid,
    build_grid,
    square_rows,
    write_download_note,
)

ROOT = Path(__file__).resolve().parent.parent
TERRAIN_SETTINGS = {"flat_slope_deg": 5.0, "min_resultant_length": 0.3}


def load_p2():
    spec = importlib.util.spec_from_file_location(
        "p2_run", ROOT / "experiments" / "p2_habitat" / "run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def small_grid() -> SampleGrid:
    return SampleGrid(west_e=4_300_000, south_n=2_300_000, east_e=4_301_000, north_n=2_301_000)


def test_build_grid_snaps_outward_to_500_m_corners() -> None:
    grid = build_grid(west=10.66, south=44.05, east=10.80, north=44.14)
    for edge in (grid.west_e, grid.south_n, grid.east_e, grid.north_n):
        assert edge % 500 == 0
    rows = square_rows(grid=grid)
    assert len(rows) == grid.rows * grid.columns
    assert 300 < len(rows) < 700


def test_square_ids_match_cell_id_of_the_square_centre() -> None:
    grid = build_grid(west=10.66, south=44.05, east=10.80, north=44.14)
    for row in square_rows(grid=grid)[::37]:
        expected = cell_id(latitude=row["centre_latitude"], longitude=row["centre_longitude"])
        assert row["cell_id"] == expected
        assert row["cell_id"] == f"500m_E{row['corner_e']}_N{row['corner_n']}"


def test_squares_run_row_by_row_from_the_north_west() -> None:
    corners = small_grid().corners()
    assert corners == [
        (4_300_000, 2_300_500),
        (4_300_500, 2_300_500),
        (4_300_000, 2_300_000),
        (4_300_500, 2_300_000),
    ]


def test_slope_rising_to_the_east_faces_west() -> None:
    columns = np.arange(40, dtype="float32") * PIXEL_SIZE_M
    altitude = np.tile(columns * 0.1, (40, 1))
    slope, aspect = terrain.slope_and_aspect(altitude=altitude, pixel_size=PIXEL_SIZE_M)
    assert slope[20, 20] == pytest.approx(5.71, abs=0.01)
    assert aspect[20, 20] == pytest.approx(270.0, abs=0.01)


def test_slope_rising_to_the_north_faces_south() -> None:
    rows = np.arange(40, dtype="float32")[::-1] * PIXEL_SIZE_M
    altitude = np.tile((rows * 0.2)[:, None], (1, 40))
    _, aspect = terrain.slope_and_aspect(altitude=altitude, pixel_size=PIXEL_SIZE_M)
    assert aspect[20, 20] == pytest.approx(180.0, abs=0.01)


def test_flat_ground_has_no_direction() -> None:
    _, aspect = terrain.slope_and_aspect(
        altitude=np.full((5, 5), 800.0, dtype="float32"), pixel_size=PIXEL_SIZE_M
    )
    assert np.all(np.isnan(aspect))


def test_circular_mean_across_north() -> None:
    direction, resultant = terrain.circular_mean(degrees=np.array([350.0, 10.0]))
    assert min(direction, 360 - direction) == pytest.approx(0.0, abs=1e-6)
    assert resultant == pytest.approx(math.cos(math.radians(10)))


def test_circular_mean_of_opposite_directions_has_no_strength() -> None:
    _, resultant = terrain.circular_mean(degrees=np.array([90.0, 270.0]))
    assert resultant == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize(
    ("valid_share", "expected"), [(1.0, "high"), (0.95, "high"), (0.9, "low"), (0.5, "low"), (0.4, None)]
)
def test_coverage_reliability_thresholds(valid_share: float, expected: str | None) -> None:
    assert terrain.coverage_reliability(valid_share=valid_share) == expected


def tilted_altitude(*, grid: SampleGrid, rise_per_m: float) -> np.ndarray:
    rows, columns = grid.pixel_shape
    eastings = np.arange(columns, dtype="float32") * PIXEL_SIZE_M
    return np.tile(1000 + eastings * rise_per_m, (rows, 1))


def test_summarise_terrain_gives_values_and_reliability_per_square() -> None:
    grid = small_grid()
    altitude = tilted_altitude(grid=grid, rise_per_m=0.2)
    altitude[:20, :20] = np.nan
    rows = terrain.summarise_terrain(altitude=altitude, grid=grid, settings=TERRAIN_SETTINGS)
    assert rows[0]["altitude_m"] is None
    assert rows[0]["altitude_m_source"] is None
    assert rows[0]["altitude_m_reliability"] is None
    steep = rows[3]
    assert steep["slope_deg"] == pytest.approx(11.3, abs=0.1)
    assert steep["aspect_deg"] == pytest.approx(270.0, abs=0.1)
    assert steep["aspect_deg_reliability"] == "high"
    assert steep["altitude_m_source"] == terrain.LAYER_ID


def test_gentle_slope_direction_is_low_reliability() -> None:
    grid = small_grid()
    rows = terrain.summarise_terrain(
        altitude=tilted_altitude(grid=grid, rise_per_m=0.02), grid=grid, settings=TERRAIN_SETTINGS
    )
    assert rows[3]["slope_deg_reliability"] == "high"
    assert rows[3]["aspect_deg_reliability"] == "low"


def soil_pixels(*, grid: SampleGrid, mean: float, low: float, high: float) -> dict[str, np.ndarray]:
    shape = grid.pixel_shape
    return {
        "mean": np.full(shape, mean, dtype="float32"),
        "Q0.05": np.full(shape, low, dtype="float32"),
        "Q0.95": np.full(shape, high, dtype="float32"),
    }


def test_soil_ph_is_divided_by_ten_and_narrow_range_is_medium() -> None:
    grid = small_grid()
    pixels = soil_pixels(grid=grid, mean=55, low=50, high=60)
    pixels["mean"][:20, :20] = np.nan
    rows = soil.summarise_soil(prop="phh2o", depth="5-15cm", pixels=pixels, grid=grid, max_range=1.5)
    assert rows[0] == {"soil_ph": None, "soil_ph_source": None, "soil_ph_reliability": None}
    assert rows[1]["soil_ph"] == pytest.approx(5.5)
    assert rows[1]["soil_ph_source"] == "soilgrids_phh2o_5-15cm"
    assert rows[1]["soil_ph_reliability"] == "medium"


def test_wide_soil_range_is_low_reliability() -> None:
    grid = small_grid()
    pixels = soil_pixels(grid=grid, mean=250, low=50, high=500)
    rows = soil.summarise_soil(prop="clay", depth="5-15cm", pixels=pixels, grid=grid, max_range=20.0)
    assert rows[0]["clay_pct"] == pytest.approx(25.0)
    assert rows[0]["clay_pct_reliability"] == "low"


def unit(code: str) -> dict[str, str]:
    return {"code": code, "name": f"name {code}", "description": f"description {code}"}


@pytest.mark.parametrize(
    ("codes", "expected_code", "expected_reliability"),
    [
        (["A", "A", "A", "A"], "A", "high"),
        (["A", "B", "A", "A"], "A", "medium"),
        (["B", "A", "A", "B"], "B", "low"),
        (["C", "A", "B", "D"], "C", "low"),
    ],
)
def test_rock_takes_most_common_unit_with_ties_to_south_west(
    codes: list[str], expected_code: str, expected_reliability: str
) -> None:
    result = rock.summarise_square(answers=[unit(code) for code in codes])
    assert result["rock_unit_code"] == expected_code
    assert result["rock_unit_name"] == f"name {expected_code}"
    assert result["rock_unit_code_reliability"] == expected_reliability
    assert result["rock_unit_code_source"] == rock.LAYER_ID


def test_rock_counts_missing_points_against_agreement() -> None:
    result = rock.summarise_square(answers=[unit("A"), None, unit("A"), unit("A")])
    assert result["rock_unit_code_reliability"] == "medium"


def test_rock_without_any_answer_is_empty() -> None:
    result = rock.summarise_square(answers=[None, None, None, None])
    assert result["rock_unit_code"] is None
    assert result["rock_unit_code_reliability"] is None


def test_rock_query_asks_the_point_in_latitude_longitude_order() -> None:
    query = rock.build_query(latitude=44.1, longitude=10.7, layer="layer")
    assert query["BBOX"] == "44.0999,10.6999,44.1001,10.7001"
    assert query["QUERY_LAYERS"] == "layer"


def test_rock_cache_skips_points_already_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = []

    def fake_query(*, latitude: float, longitude: float, layer: str) -> dict[str, str]:
        asked.append((latitude, longitude))
        return unit("A")

    monkeypatch.setattr(rock, "query_point", fake_query)
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps({"44.000000,10.000000": None}), encoding="utf-8")
    answers = rock.fetch_points(
        points=[(44.0, 10.0), (44.1, 10.1)], layer="layer", cache_path=cache_path, pause_seconds=0
    )
    assert asked == [(44.1, 10.1)]
    assert answers["44.000000,10.000000"] is None
    assert json.loads(cache_path.read_text(encoding="utf-8"))["44.100000,10.100000"]["code"] == "A"


def test_run_lengths_compare_with_the_first_value_of_the_stretch() -> None:
    assert detail.run_lengths(line=[1.0, 1.4, 1.8, 2.2], tolerance=0.5) == [2, 2]
    assert detail.run_lengths(line=[5, 5, math.nan, 5, 6], tolerance=0.0) == [2, 1, 1]
    assert detail.run_lengths(line=["A", "A", None, "B"], tolerance=0.0) == [2, 1]


def test_real_detail_averages_rows_and_columns() -> None:
    values = [[1, 1, 1, 1], [2, 2, 3, 3]]
    result = detail.real_detail_m(values=values, tolerance=0.0, spacing_east_m=250, spacing_north_m=100)
    along_rows = (4 + 2 + 2) / 3 * 250
    along_columns = 1.0 * 100
    assert result == pytest.approx((along_rows + along_columns) / 2, abs=0.1)


def test_mixed_square_share_ignores_empty_squares() -> None:
    blocks = [["A", "A", "A", "A"], ["A", "B", None, "A"], [None, None, None, None], [5.0, math.nan]]
    assert detail.mixed_square_share(blocks=blocks) == pytest.approx(1 / 3, abs=0.001)


def write_raster(
    *, path: Path, values: np.ndarray, crs: str, transform: Any, nodata: float
) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype=values.dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as target:
        target.write(values, 1)


@pytest.fixture
def finished_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    config = tomllib.loads(
        (ROOT / "experiments" / "p2_habitat" / "config.toml").read_text(encoding="utf-8")
    )
    settings = config["settings"]
    settings["sample_box"] = {"west": 10.70, "south": 44.08, "east": 10.71, "north": 44.09}
    settings["rock"]["pause_seconds"] = 0
    settings["reports_dir"] = str(tmp_path / "reports")
    settings["layers_path"] = str(tmp_path / "p2_layers.csv")

    def fake_dem(*, bounds: tuple, raw_dir: Path) -> Path:
        west, south, east, north = bounds
        columns = int((east - west) * 3600) + 1
        rows = int((north - south) * 3600) + 1
        values = np.tile(np.linspace(900, 1100, columns, dtype="float32"), (rows, 1))
        values[0, 0] = terrain.NODATA
        path = raw_dir / terrain.RAW_NAME
        transform = from_origin(west, north, 1 / 3600, 1 / 3600)
        write_raster(path=path, values=values, crs="EPSG:4326", transform=transform, nodata=terrain.NODATA)
        write_download_note(
            path=path,
            details={"tiles": ["https://example/tile.tif"], "last_modified": ["today"], "bounds": list(bounds)},
        )
        return path

    def fake_soil(*, prop: str, depth: str, stat: str, bounds: tuple, raw_dir: Path) -> Path:
        west, south, east, north = bounds
        value = {"mean": 55, "Q0.05": 50, "Q0.95": 60}[stat]
        values = np.full((12, 12), value, dtype="int16")
        values[:, :6] = -32768
        path = raw_dir / soil.raw_name(prop=prop, depth=depth, stat=stat)
        transform = from_origin(west, north, (east - west) / 12, (north - south) / 12)
        write_raster(path=path, values=values, crs="EPSG:4326", transform=transform, nodata=-32768)
        write_download_note(path=path, details={"url": "https://example/soil.vrt", "bounds": list(bounds)})
        return path

    def fake_query(*, latitude: float, longitude: float, layer: str) -> dict[str, str] | None:
        return unit("MAC2") if longitude > 10.705 else None

    monkeypatch.setattr(terrain, "download_dem", fake_dem)
    monkeypatch.setattr(soil, "download_soil", fake_soil)
    monkeypatch.setattr(rock, "query_point", fake_query)
    context = RunContext(
        config=settings,
        seed=42,
        run_id="test",
        raw_dir=tmp_path / "raw",
        output_dir=tmp_path / "processed",
        state_path=tmp_path / "state.json",
    )
    load_p2().run(context)
    return {
        "tmp_path": tmp_path,
        "state": json.loads((tmp_path / "state.json").read_text(encoding="utf-8")),
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_run_writes_grid_with_source_and_reliability_columns(finished_run: dict[str, Any]) -> None:
    table = pq.read_table(finished_run["tmp_path"] / "processed" / "grid.parquet").to_pylist()
    assert len(table) > 4
    first = table[0]
    for column in load_p2().VALUE_COLUMNS:
        assert column in first
        assert f"{column}_source" in first
        assert f"{column}_reliability" in first
    assert all(row["altitude_m"] is not None for row in table)
    assert all(row["altitude_m_source"] == terrain.LAYER_ID for row in table)
    assert any(row["soil_ph"] is None for row in table)
    assert any(row["soil_ph"] == pytest.approx(5.5) for row in table)


def test_run_writes_layer_list_with_every_field_filled(finished_run: dict[str, Any]) -> None:
    layers = read_csv(finished_run["tmp_path"] / "p2_layers.csv")
    assert [layer["layer_id"] for layer in layers] == [
        "copernicus_dem_glo30",
        "soilgrids_phh2o_5-15cm",
        "soilgrids_clay_5-15cm",
        "soilgrids_sand_5-15cm",
        "soilgrids_silt_5-15cm",
        "toscana_geologia_10k",
    ]
    for layer in layers:
        assert all(value for value in layer.values()), layer


def test_run_writes_coverage_gaps_and_detail(finished_run: dict[str, Any]) -> None:
    reports = finished_run["tmp_path"] / "reports"
    coverage = {row["value"]: row for row in read_csv(reports / "p2_coverage.csv")}
    assert coverage["altitude_m"]["share"] == "1.0"
    assert 0 < float(coverage["soil_ph"]["share"]) < 1
    assert 0 < float(coverage["rock_unit_code"]["share"]) < 1
    gaps = read_csv(reports / "p2_gaps.csv")
    assert gaps
    assert all("soil_ph" in gap["missing_values"] or "rock_unit_code" in gap["missing_values"] for gap in gaps)
    details = {row["layer_id"]: row for row in read_csv(reports / "p2_detail.csv")}
    assert set(details) == {
        "copernicus_dem_glo30",
        "soilgrids_phh2o_5-15cm",
        "soilgrids_clay_5-15cm",
        "soilgrids_sand_5-15cm",
        "soilgrids_silt_5-15cm",
        "toscana_geologia_10k",
    }
    assert details["soilgrids_phh2o_5-15cm"]["coarser_than_square"] == "True"


def test_run_records_every_source_and_output(finished_run: dict[str, Any]) -> None:
    state = finished_run["state"]
    names = [source["name"] for source in state["sources"]]
    assert names[0] == "Copernicus DEM GLO-30 elevation map"
    assert len([name for name in names if name.startswith("ISRIC")]) == 12
    assert names[-1].startswith("Regione Toscana")
    assert len(state["outputs"]) == 5
