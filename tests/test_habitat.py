"""Offline tests for the P2 sample grid: grid, terrain, soil, rock type, forest and real detail."""

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
import shapefile
from pyproj import Transformer
from rasterio.transform import from_origin

from micometeo.context import RunContext
from micometeo.finds.grid import cell_id
from micometeo.habitat import detail, forest, inventory, rock, soil, terrain
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


FOREST_SETTINGS = {"no_forest_below": 0.1, "low_reliability_below": 0.3, "broadleaf_from": 0.75}


def forest_block_grid() -> SampleGrid:
    return SampleGrid(west_e=4_300_000, south_n=2_300_000, east_e=4_300_500, north_n=2_300_500)


def forest_pixels(*, broadleaf: int, conifer: int, missing: int = 0) -> np.ndarray:
    """Return one square of 400 pixels with the given counts, the rest not forest."""
    flat = np.zeros(400, dtype="float32")
    flat[:broadleaf] = 1
    flat[broadleaf : broadleaf + conifer] = 2
    if missing:
        flat[400 - missing :] = np.nan
    return flat.reshape(20, 20)


def summarise_one_square(pixels: np.ndarray) -> dict[str, Any]:
    return forest.summarise_forest(pixels=pixels, grid=forest_block_grid(), settings=FOREST_SETTINGS)[0]


def test_forest_shares_count_forest_pixels_among_valid_pixels() -> None:
    result = summarise_one_square(forest_pixels(broadleaf=100, conifer=100, missing=40))
    assert result["forest_share"] == pytest.approx(200 / 360, abs=0.001)
    assert result["broadleaf_share"] == 0.5
    assert result["leaf_type"] == "mixed"
    assert result["forest_share_reliability"] == "low"
    assert result["forest_share_source"] == forest.LAYER_ID


def test_unclassifiable_and_outside_pixels_count_as_missing() -> None:
    raw = np.array([0, 1, 2, 254, 255], dtype="float32")
    assert np.isnan(forest.mask_unusable(pixels=raw)).tolist() == [False, False, False, True, True]


def test_square_with_too_few_valid_pixels_has_no_forest_values() -> None:
    result = summarise_one_square(forest_pixels(broadleaf=100, conifer=0, missing=250))
    assert result["forest_share"] is None
    assert result["leaf_type"] is None
    assert result["leaf_type_source"] is None


@pytest.mark.parametrize(
    ("broadleaf", "conifer", "expected", "reliability"),
    [
        (0, 0, "no forest", "high"),
        (39, 0, "no forest", "high"),
        (40, 0, "broadleaf", "low"),
        (119, 0, "broadleaf", "low"),
        (120, 0, "broadleaf", "high"),
        (90, 30, "broadleaf", "high"),
        (89, 31, "mixed", "high"),
        (60, 60, "mixed", "high"),
        (31, 89, "mixed", "high"),
        (30, 90, "conifer", "high"),
        (0, 200, "conifer", "high"),
        (0, 40, "conifer", "low"),
    ],
)
def test_leaf_type_thresholds(broadleaf: int, conifer: int, expected: str, reliability: str) -> None:
    result = summarise_one_square(forest_pixels(broadleaf=broadleaf, conifer=conifer))
    assert result["leaf_type"] == expected
    assert result["leaf_type_reliability"] == reliability


def test_broadleaf_share_is_empty_without_forest_and_low_for_little_forest() -> None:
    empty = summarise_one_square(forest_pixels(broadleaf=0, conifer=0))
    assert empty["forest_share"] == 0.0
    assert empty["broadleaf_share"] is None
    assert empty["broadleaf_share_source"] is None
    small = summarise_one_square(forest_pixels(broadleaf=20, conifer=0))
    assert small["broadleaf_share"] == 1.0
    assert small["broadleaf_share_reliability"] == "low"


def inventory_point(*, name: str, leaf_type: str | None, easting: float = 250, northing: float = 250) -> dict[str, Any]:
    return {"name": name, "leaf_type": leaf_type, "easting": easting, "northing": northing}


def inventory_square(*, points: list[dict[str, Any]], **forest_values: Any) -> dict[str, Any]:
    return inventory.summarise_square(
        points=points, centre=(250, 250), forest=forest_values, low_reliability_below=0.3
    )


def test_inventory_square_without_points_is_empty() -> None:
    result = inventory_square(points=[])
    assert result["regional_forest_type"] is None
    assert result["regional_forest_type_reliability"] is None
    assert result["regional_forest_points"] == 0


def test_inventory_takes_most_common_type() -> None:
    points = [
        inventory_point(name="beech woods", leaf_type="broadleaf"),
        inventory_point(name="chestnut woods", leaf_type="broadleaf"),
        inventory_point(name="chestnut woods", leaf_type="broadleaf"),
    ]
    result = inventory_square(points=points)
    assert result["regional_forest_type"] == "chestnut woods"
    assert result["regional_forest_points"] == 3
    assert result["regional_forest_type_source"] == inventory.LAYER_ID


def test_inventory_tie_goes_to_the_point_nearest_the_centre() -> None:
    points = [
        inventory_point(name="beech woods", leaf_type="broadleaf", easting=50, northing=50),
        inventory_point(name="silver fir woods", leaf_type="conifer", easting=240, northing=260),
    ]
    assert inventory_square(points=points)["regional_forest_type"] == "silver fir woods"


def test_inventory_reliability_without_conflict() -> None:
    beech = inventory_point(name="beech woods", leaf_type="broadleaf")
    fir = inventory_point(name="silver fir woods", leaf_type="conifer")
    agreeing = {"forest_share": 0.9, "leaf_type": "broadleaf"}
    assert inventory_square(points=[beech, beech], **agreeing)["regional_forest_type_reliability"] == "high"
    assert inventory_square(points=[beech], **agreeing)["regional_forest_type_reliability"] == "medium"
    assert inventory_square(points=[beech, beech, fir], **agreeing)["regional_forest_type_reliability"] == "medium"
    assert inventory_square(points=[beech, beech])["regional_forest_type_reliability"] == "high"


@pytest.mark.parametrize(
    ("leaf_type", "forest_share", "copernicus_leaf_type"),
    [
        ("broadleaf", 0.9, "conifer"),
        ("conifer", 0.9, "broadleaf"),
        ("broadleaf", 0.0, "no forest"),
        ("conifer", 0.0, "no forest"),
        (None, 0.3, "broadleaf"),
        (None, 0.9, "mixed"),
    ],
)
def test_inventory_conflict_with_satellite_map_is_low_reliability(
    leaf_type: str | None, forest_share: float, copernicus_leaf_type: str
) -> None:
    point = inventory_point(name="some type", leaf_type=leaf_type)
    result = inventory_square(
        points=[point, point], forest_share=forest_share, leaf_type=copernicus_leaf_type
    )
    assert result["regional_forest_type_reliability"] == "low"


@pytest.mark.parametrize(
    ("leaf_type", "forest_share", "copernicus_leaf_type"),
    [
        ("broadleaf", 0.9, "mixed"),
        ("conifer", 0.5, "mixed"),
        ("broadleaf", None, None),
        (None, 0.29, "broadleaf"),
        (None, 0.0, "no forest"),
        ("broadleaf", 0.9, "broadleaf"),
    ],
)
def test_inventory_mixed_or_missing_satellite_values_are_not_conflicts(
    leaf_type: str | None, forest_share: float | None, copernicus_leaf_type: str | None
) -> None:
    point = inventory_point(name="some type", leaf_type=leaf_type)
    result = inventory_square(
        points=[point, point], forest_share=forest_share, leaf_type=copernicus_leaf_type
    )
    assert result["regional_forest_type_reliability"] == "high"


def test_inventory_category_names_are_translated_and_whitespace_is_normalised() -> None:
    assert inventory.english_name(category="Faggete") == "beech woods"
    name = inventory.english_name(category="Pinete di rimboschimento di pino  nero ")
    assert name == "planted black pine woods"
    assert inventory.english_name(category=None) == "not woodland"
    assert inventory.english_name(category="") == "not woodland"


def test_inventory_unknown_category_raises_with_its_name() -> None:
    with pytest.raises(ValueError, match="Pineta fantasma"):
        inventory.english_name(category="Pineta fantasma")


def test_inventory_leaf_type_comes_from_the_conifer_or_broadleaf_text() -> None:
    assert inventory.leaf_type_of(conifer_or_broadleaf="latifoglie") == "broadleaf"
    assert inventory.leaf_type_of(conifer_or_broadleaf="conifere") == "conifer"
    assert inventory.leaf_type_of(conifer_or_broadleaf="Terreni saldi") is None
    assert inventory.leaf_type_of(conifer_or_broadleaf=None) is None


def test_inventory_points_are_assigned_to_the_square_that_contains_them() -> None:
    grid = forest_block_grid()
    inside = inventory_point(name="beech woods", leaf_type="broadleaf", easting=4_300_100, northing=2_300_400)
    outside = inventory_point(name="beech woods", leaf_type="broadleaf", easting=4_300_600, northing=2_300_400)
    assert inventory.points_by_square(points=[inside, outside], grid=grid) == [[inside]]


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

    def fake_forest_type(*, grid: SampleGrid, raw_dir: Path) -> Path:
        width = (grid.east_e - grid.west_e) // forest.PIXEL_M
        height = (grid.north_n - grid.south_n) // forest.PIXEL_M
        values = np.zeros((height, width), dtype="uint8")
        values[:, : width // 2] = 1
        values[:, width // 2 :] = 2
        values[: height // 3, width // 2 :] = 0
        values[2 * height // 3 :, : width // 4] = 2
        values[:5, :5] = 254
        values[-5:, :] = 255
        path = raw_dir / forest.RAW_NAME
        transform = from_origin(grid.west_e, grid.north_n, forest.PIXEL_M, forest.PIXEL_M)
        write_raster(path=path, values=values, crs="EPSG:3035", transform=transform, nodata=None)
        write_download_note(path=path, details={"url": forest.SERVICE_URL, "query": {"bbox": "test"}})
        return path

    def fake_inventory(*, raw_dir: Path) -> Path:
        to_gauss_boaga = Transformer.from_crs("EPSG:4326", "EPSG:3003", always_xy=True)
        survey = [
            (10.7020, 44.0820, "Faggete", "latifoglie"),
            (10.7022, 44.0821, "Faggete", "latifoglie"),
            (10.7050, 44.0850, "Abetine", "conifere"),
            (10.7010, 44.0870, "", ""),
            (10.7095, 44.0805, "Pinete di rimboschimento di pino  nero", "conifere"),
        ]
        path = raw_dir / inventory.RAW_DIR_NAME / inventory.TABLE_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            writer = shapefile.Writer(dbf=handle, encoding=inventory.ENCODING)
            writer.field("X_COORD", "N", 10, 0)
            writer.field("Y_COORD", "N", 10, 0)
            writer.field("CATFOR", "C", 60)
            writer.field("CONIF_LAT", "C", 20)
            for longitude, latitude, category, leaf in survey:
                x_coord, y_coord = to_gauss_boaga.transform(longitude, latitude)
                writer.record(round(x_coord), round(y_coord), category, leaf)
            writer.close()
        write_download_note(path=path, details={"url": inventory.DOWNLOAD_URL, "files": [inventory.TABLE_NAME]})
        return path

    def fake_query(*, latitude: float, longitude: float, layer: str) -> dict[str, str] | None:
        return unit("MAC2") if longitude > 10.705 else None

    monkeypatch.setattr(terrain, "download_dem", fake_dem)
    monkeypatch.setattr(soil, "download_soil", fake_soil)
    monkeypatch.setattr(rock, "query_point", fake_query)
    monkeypatch.setattr(forest, "download_forest_type", fake_forest_type)
    monkeypatch.setattr(inventory, "download_inventory", fake_inventory)
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
        "copernicus_forest_type_2018",
        "toscana_inventario_forestale_400m",
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
    assert all(
        any(value in gap["missing_values"] for value in ("soil_ph", "rock_unit_code", "regional_forest_type"))
        for gap in gaps
    )
    details = {row["layer_id"]: row for row in read_csv(reports / "p2_detail.csv")}
    assert set(details) == {
        "copernicus_dem_glo30",
        "soilgrids_phh2o_5-15cm",
        "soilgrids_clay_5-15cm",
        "soilgrids_sand_5-15cm",
        "soilgrids_silt_5-15cm",
        "toscana_geologia_10k",
        "copernicus_forest_type_2018",
        "toscana_inventario_forestale_400m",
    }
    assert details["toscana_inventario_forestale_400m"]["real_detail_m"] == "400.0"
    assert details["soilgrids_phh2o_5-15cm"]["coarser_than_square"] == "True"


def test_run_records_every_source_and_output(finished_run: dict[str, Any]) -> None:
    state = finished_run["state"]
    names = [source["name"] for source in state["sources"]]
    assert names[0] == "Copernicus DEM GLO-30 elevation map"
    assert len([name for name in names if name.startswith("ISRIC")]) == 12
    assert names[-3].startswith("Regione Toscana geology")
    assert names[-2] == "Copernicus forest type 2018"
    assert names[-1] == "Regione Toscana forest inventory"
    assert len(state["outputs"]) == 5


def test_run_fills_forest_values_with_reliability_and_no_tree_names(finished_run: dict[str, Any]) -> None:
    table = pq.read_table(finished_run["tmp_path"] / "processed" / "grid.parquet").to_pylist()
    leaf_types = {row["leaf_type"] for row in table}
    assert leaf_types <= {"no forest", "broadleaf", "conifer", "mixed", None}
    assert {"no forest", "broadleaf", "conifer"} <= leaf_types
    for row in table:
        if row["leaf_type"] is not None:
            assert row["forest_share"] is not None
            assert row["leaf_type_source"] == forest.LAYER_ID
        if row["broadleaf_share"] is None:
            assert row["broadleaf_share_source"] is None
    assert all(
        row["forest_share_source"] in (None, forest.LAYER_ID)
        and row["broadleaf_share_source"] in (None, forest.LAYER_ID)
        for row in table
    )


def test_run_fills_regional_forest_type_from_survey_points(finished_run: dict[str, Any]) -> None:
    table = pq.read_table(finished_run["tmp_path"] / "processed" / "grid.parquet")
    columns = table.column_names
    assert columns.index("regional_forest_points") == columns.index("regional_forest_type") + 1
    rows = table.to_pylist()
    assert sum(row["regional_forest_points"] for row in rows) == 5
    types = {row["regional_forest_type"] for row in rows}
    assert {"beech woods", "silver fir woods", "not woodland", "planted black pine woods"} <= types
    for row in rows:
        has_type = row["regional_forest_type"] is not None
        assert (row["regional_forest_type_source"] == inventory.LAYER_ID) is has_type
        assert (row["regional_forest_type_reliability"] is not None) is has_type
    reliabilities = {row["regional_forest_type_reliability"] for row in rows} - {None}
    assert reliabilities <= {"high", "medium", "low"}


def test_run_coverage_lists_forest_values(finished_run: dict[str, Any]) -> None:
    coverage = {row["value"]: row for row in read_csv(finished_run["tmp_path"] / "reports" / "p2_coverage.csv")}
    assert float(coverage["forest_share"]["share"]) > 0.5
    assert 0 < float(coverage["regional_forest_type"]["share"]) < 1
