"""P2: fill a 500 m grid of a Pistoia Apennines sample area with terrain, soil, rock type and forest."""

import csv
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from rasterio.warp import Resampling

from micometeo.context import RunContext
from micometeo.finds.grid import CELL_SIZE_M
from micometeo.habitat import detail, forest, inventory, rock, soil, terrain
from micometeo.habitat.grid import (
    SampleGrid,
    build_grid,
    note_path,
    read_download_note,
    square_blocks,
    square_rows,
    warp_to_grid,
    write_download_note,
)

ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = ROOT / "reports"
LAYERS_PATH = ROOT / "data" / "p2_layers.csv"
GRID_COLUMNS = ["cell_id", "corner_e", "corner_n", "centre_latitude", "centre_longitude"]
VALUE_COLUMNS = [
    "altitude_m",
    "slope_deg",
    "aspect_deg",
    "soil_ph",
    "clay_pct",
    "sand_pct",
    "silt_pct",
    "rock_unit_code",
    "forest_share",
    "broadleaf_share",
    "leaf_type",
    "regional_forest_type",
]
LAYER_COLUMNS = [
    "layer_id",
    "provider",
    "title",
    "url",
    "licence",
    "version",
    "download_date",
    "file_format",
    "coordinate_system",
    "stated_detail",
]
DETAIL_COLUMNS = [
    "layer_id",
    "used_for",
    "stated_detail",
    "real_detail_m",
    "mixed_square_share",
    "square_size_m",
    "coarser_than_square",
]


def output_columns() -> list[str]:
    """Return grid columns, then each value with its source and reliability columns."""
    columns = list(GRID_COLUMNS)
    for column in VALUE_COLUMNS:
        columns.append(column)
        if column == "rock_unit_code":
            columns += ["rock_unit_name", "rock_description"]
        if column == "regional_forest_type":
            columns.append("regional_forest_points")
        columns += [f"{column}_source", f"{column}_reliability"]
    return columns


def write_csv(*, rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def coverage_table(*, squares: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return how many squares have each value and their share of all squares."""
    total = len(squares)
    rows = []
    for column in VALUE_COLUMNS:
        with_value = sum(1 for square in squares if square.get(column) is not None)
        rows.append(
            {
                "value": column,
                "squares_with_value": with_value,
                "total_squares": total,
                "share": round(with_value / total, 3) if total else 0.0,
            }
        )
    return rows


def gaps_table(*, squares: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one row for every square that misses a value, naming the missing values."""
    rows = []
    for square in squares:
        missing = [column for column in VALUE_COLUMNS if square.get(column) is None]
        if missing:
            rows.append({"cell_id": square["cell_id"], "missing_values": " ".join(missing)})
    return rows


def add_terrain(
    *, context: RunContext, grid: SampleGrid, squares: list[dict[str, Any]], bounds: tuple
) -> tuple[Path, dict[str, Any]]:
    """Download the elevation map and add altitude, slope and slope direction to every square."""
    path = terrain.download_dem(bounds=bounds, raw_dir=context.raw_dir)
    note = read_download_note(path=path)
    context.add_source(
        name="Copernicus DEM GLO-30 elevation map",
        url=note["tiles"][0],
        licence=terrain.LICENCE,
        version="GLO-30 public release on AWS, tiles last modified "
        + "; ".join(note["last_modified"]),
        downloaded_at=note["downloaded_at"],
        query={"tiles": note["tiles"], "bounds": note["bounds"]},
    )
    context.add_input(path)
    altitude = warp_to_grid(path=path, grid=grid, resampling=Resampling.bilinear)
    for square, values in zip(
        squares,
        terrain.summarise_terrain(altitude=altitude, grid=grid, settings=context.config["terrain"]),
    ):
        square.update(values)
    layer = {
        "layer_id": terrain.LAYER_ID,
        "provider": "European Space Agency and Airbus, Copernicus programme",
        "title": "Copernicus DEM GLO-30, surface elevation",
        "url": note["tiles"][0],
        "licence": terrain.LICENCE,
        "version": "GLO-30 public release, tile last modified " + note["last_modified"][0],
        "download_date": note["downloaded_at"][:10],
        "file_format": "Cloud optimised GeoTIFF",
        "coordinate_system": "EPSG:4326 with EGM2008 heights",
        "stated_detail": "1 arc second, about 30 m",
    }
    return path, layer


def add_soil(
    *, context: RunContext, grid: SampleGrid, squares: list[dict[str, Any]], bounds: tuple
) -> tuple[dict[str, Path], list[dict[str, Any]]]:
    """Download SoilGrids acidity and texture and add them to every square."""
    settings = context.config["soil"]
    depth = settings["depth"]
    mean_paths = {}
    layers = []
    for prop in settings["properties"]:
        pixels = {}
        for stat in soil.STATS:
            path = soil.download_soil(
                prop=prop, depth=depth, stat=stat, bounds=bounds, raw_dir=context.raw_dir
            )
            note = read_download_note(path=path)
            context.add_source(
                name=f"ISRIC SoilGrids 2.0 {prop} {depth} {stat}",
                url=note["url"],
                licence=soil.LICENCE,
                version="SoilGrids 2.0",
                downloaded_at=note["downloaded_at"],
                query={"bounds": note["bounds"]},
            )
            context.add_input(path)
            pixels[stat] = warp_to_grid(path=path, grid=grid, resampling=Resampling.nearest)
            if stat == "mean":
                mean_paths[prop] = path
                download_date = note["downloaded_at"][:10]
        for square, values in zip(
            squares,
            soil.summarise_soil(
                prop=prop,
                depth=depth,
                pixels=pixels,
                grid=grid,
                max_range=settings["max_range"][prop],
            ),
        ):
            square.update(values)
        layers.append(
            {
                "layer_id": soil.layer_id(prop=prop, depth=depth),
                "provider": "ISRIC World Soil Information",
                "title": f"SoilGrids 2.0 {prop} at {depth}, mean with 5 and 95 percent values",
                "url": soil.FILE_URL.format(prop=prop, depth=depth, stat="mean"),
                "licence": soil.LICENCE,
                "version": "SoilGrids 2.0, files under data/latest",
                "download_date": download_date,
                "file_format": "GeoTIFF tiles listed in a GDAL VRT file",
                "coordinate_system": "Interrupted Goode Homolosine, ESRI:54052",
                "stated_detail": "250 m",
            }
        )
    return mean_paths, layers


def add_rock(
    *, context: RunContext, grid: SampleGrid, squares: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ask the geology map for the rock unit at four points per square and add it."""
    settings = context.config["rock"]
    points = rock.quarter_points(grid=grid)
    cache_path = context.raw_dir / rock.CACHE_NAME
    answers = rock.fetch_points(
        points=[point for square_points in points for point in square_points],
        layer=settings["layer"],
        cache_path=cache_path,
        pause_seconds=settings["pause_seconds"],
    )
    if not note_path(path=cache_path).exists():
        write_download_note(
            path=cache_path, details={"url": rock.SERVICE_URL, "layer": settings["layer"]}
        )
    note = read_download_note(path=cache_path)
    context.add_source(
        name="Regione Toscana geology database, 1:10,000 rock units",
        url=rock.SERVICE_URL,
        licence=rock.LICENCE,
        version="Database geologico regionale, map service as queried",
        downloaded_at=note["downloaded_at"],
        query={"layer": settings["layer"], "points": len(answers)},
    )
    context.add_input(cache_path)
    for square, square_points in zip(squares, points):
        square.update(
            rock.summarise_square(
                answers=[
                    answers.get(rock.point_key(latitude=latitude, longitude=longitude))
                    for latitude, longitude in square_points
                ]
            )
        )
    layer = {
        "layer_id": rock.LAYER_ID,
        "provider": "Regione Toscana, GEOscopio",
        "title": "Database geologico regionale, geological units of the 1:10,000 map",
        "url": rock.SERVICE_URL + "?map=dbgeologico_rt.qgs",
        "licence": rock.LICENCE,
        "version": "Database geologico regionale, record r_toscan:8c908a0d-bf9e-4657-8c1d-da64e64919aa",
        "download_date": note["downloaded_at"][:10],
        "file_format": "WMS GetFeatureInfo answers in JSON, one per point",
        "coordinate_system": "EPSG:4326 for the queries",
        "stated_detail": "1:10,000 map",
    }
    return layer, answers


def add_forest(
    *, context: RunContext, grid: SampleGrid, squares: list[dict[str, Any]]
) -> tuple[Path, dict[str, Any]]:
    """Download the forest type map and add forest share, broadleaf share and leaf type."""
    path = forest.download_forest_type(grid=grid, raw_dir=context.raw_dir)
    note = read_download_note(path=path)
    context.add_source(
        name="Copernicus forest type 2018",
        url=note["url"],
        licence=forest.LICENCE,
        version="High Resolution Layer Forest Type, reference year 2018",
        downloaded_at=note["downloaded_at"],
        query=note["query"],
    )
    context.add_input(path)
    pixels = forest.mask_unusable(
        pixels=warp_to_grid(path=path, grid=grid, resampling=Resampling.nearest)
    )
    for square, values in zip(
        squares,
        forest.summarise_forest(pixels=pixels, grid=grid, settings=context.config["forest"]),
    ):
        square.update(values)
    layer = {
        "layer_id": forest.LAYER_ID,
        "provider": "European Environment Agency, Copernicus Land Monitoring Service",
        "title": "High Resolution Layer Forest Type 2018, broadleaf and conifer forest",
        "url": note["url"],
        "licence": forest.LICENCE,
        "version": "Forest type 2018, forest means at least 10 percent tree cover over at least 0.5 ha",
        "download_date": note["downloaded_at"][:10],
        "file_format": "GeoTIFF exported from the EEA image service",
        "coordinate_system": "EPSG:3035, served by the EEA image service",
        "stated_detail": "10 m pixels",
    }
    return path, layer


def add_inventory(
    *, context: RunContext, grid: SampleGrid, squares: list[dict[str, Any]]
) -> tuple[list[list[dict[str, Any]]], dict[str, Any]]:
    """Download the Tuscany forest inventory and add the regional forest type to every square."""
    path = inventory.download_inventory(raw_dir=context.raw_dir)
    note = read_download_note(path=path)
    context.add_source(
        name="Regione Toscana forest inventory",
        url=note["url"],
        licence=inventory.LICENCE,
        version="Inventario forestale della Toscana, surveyed 1985 to 1993, revised 2009",
        downloaded_at=note["downloaded_at"],
        query={"files": note["files"]},
    )
    context.add_input(path)
    points = inventory.read_points(path=path, grid=grid)
    square_points = inventory.points_by_square(points=points, grid=grid)
    for square, in_square in zip(squares, square_points):
        square.update(
            inventory.summarise_square(
                points=in_square,
                centre=(square["corner_e"] + CELL_SIZE_M / 2, square["corner_n"] + CELL_SIZE_M / 2),
                forest=square,
                low_reliability_below=context.config["forest"]["low_reliability_below"],
            )
        )
    layer = {
        "layer_id": inventory.LAYER_ID,
        "provider": "Regione Toscana, GEOscopio",
        "title": "Inventario forestale della Toscana, forest category at survey points",
        "url": inventory.DOWNLOAD_URL,
        "licence": inventory.LICENCE,
        "version": "Field survey 1985 to 1993, dataset revised 2009",
        "download_date": note["downloaded_at"][:10],
        "file_format": "ESRI Shapefile, only the attribute table is read",
        "coordinate_system": "EPSG:3003, Gauss-Boaga west",
        "stated_detail": "one survey point per 400 m cell",
    }
    return square_points, layer


def detail_table(
    *,
    context: RunContext,
    grid: SampleGrid,
    dem_path: Path,
    soil_paths: dict[str, Path],
    rock_answers: dict[str, Any],
    forest_path: Path,
    inventory_points: list[list[dict[str, Any]]],
    box: tuple[float, float, float, float],
) -> list[dict[str, Any]]:
    """Measure the real detail of every layer inside the sample box."""
    rows = []
    values, spacing_east, spacing_north = detail.native_values(path=dem_path, bounds=box)
    altitude = warp_to_grid(path=dem_path, grid=grid, resampling=Resampling.bilinear)
    rows.append(
        {
            "layer_id": terrain.LAYER_ID,
            "used_for": "altitude_m slope_deg aspect_deg",
            "stated_detail": "about 30 m",
            "real_detail_m": detail.real_detail_m(
                values=values,
                tolerance=context.config["terrain"]["same_altitude_m"],
                spacing_east_m=spacing_east,
                spacing_north_m=spacing_north,
            ),
            "mixed_square_share": detail.mixed_square_share(
                blocks=np.round(square_blocks(pixels=altitude, grid=grid)).tolist()
            ),
        }
    )
    depth = context.config["soil"]["depth"]
    for prop, path in soil_paths.items():
        values, spacing_east, spacing_north = detail.native_values(path=path, bounds=box)
        pixels = warp_to_grid(path=path, grid=grid, resampling=Resampling.nearest)
        rows.append(
            {
                "layer_id": soil.layer_id(prop=prop, depth=depth),
                "used_for": soil.COLUMNS[prop],
                "stated_detail": "250 m",
                "real_detail_m": detail.real_detail_m(
                    values=values,
                    tolerance=0.0,
                    spacing_east_m=spacing_east,
                    spacing_north_m=spacing_north,
                ),
                "mixed_square_share": detail.mixed_square_share(
                    blocks=square_blocks(pixels=pixels, grid=grid).tolist()
                ),
            }
        )
    rock_blocks = [
        [
            (answers or {}).get("code") or None
            for answers in (
                rock_answers.get(rock.point_key(latitude=latitude, longitude=longitude))
                for latitude, longitude in square_points
            )
        ]
        for square_points in rock.quarter_points(grid=grid)
    ]
    rows.append(
        {
            "layer_id": rock.LAYER_ID,
            "used_for": "rock_unit_code rock_unit_name rock_description",
            "stated_detail": "1:10,000 map",
            "real_detail_m": detail.real_detail_m(
                values=rock.code_lattice(grid=grid, answers=rock_answers),
                tolerance=0.0,
                spacing_east_m=CELL_SIZE_M / 2,
                spacing_north_m=CELL_SIZE_M / 2,
            ),
            "mixed_square_share": detail.mixed_square_share(blocks=rock_blocks),
        }
    )
    values, spacing_east, spacing_north = detail.native_values(path=forest_path, bounds=box)
    forest_pixels = forest.mask_unusable(
        pixels=warp_to_grid(path=forest_path, grid=grid, resampling=Resampling.nearest)
    )
    rows.append(
        {
            "layer_id": forest.LAYER_ID,
            "used_for": "forest_share broadleaf_share leaf_type",
            "stated_detail": "10 m",
            "real_detail_m": detail.real_detail_m(
                values=forest.mask_unusable(pixels=np.array(values)).tolist(),
                tolerance=0.0,
                spacing_east_m=spacing_east,
                spacing_north_m=spacing_north,
            ),
            "mixed_square_share": detail.mixed_square_share(
                blocks=square_blocks(pixels=forest_pixels, grid=grid).tolist()
            ),
        }
    )
    rows.append(
        {
            "layer_id": inventory.LAYER_ID,
            "used_for": "regional_forest_type",
            "stated_detail": "one point per 400 m cell",
            "real_detail_m": 400.0,
            "mixed_square_share": detail.mixed_square_share(
                blocks=[
                    [point["name"] for point in in_square] if len(in_square) >= 2 else []
                    for in_square in inventory_points
                ]
            ),
        }
    )
    for row in rows:
        row["square_size_m"] = CELL_SIZE_M
        row["coarser_than_square"] = row["real_detail_m"] > CELL_SIZE_M
    return rows


def run(context: RunContext) -> None:
    """Build the sample grid, fill it from each layer and write the grid and the tables."""
    settings = context.config
    sample_box = settings["sample_box"]
    box = (sample_box["west"], sample_box["south"], sample_box["east"], sample_box["north"])
    grid = build_grid(west=box[0], south=box[1], east=box[2], north=box[3])
    bounds = grid.bounds_degrees(margin=settings["download_margin_degrees"])
    squares = square_rows(grid=grid)

    dem_path, dem_layer = add_terrain(context=context, grid=grid, squares=squares, bounds=bounds)
    soil_paths, soil_layers = add_soil(context=context, grid=grid, squares=squares, bounds=bounds)
    rock_layer, rock_answers = add_rock(context=context, grid=grid, squares=squares)
    forest_path, forest_layer = add_forest(context=context, grid=grid, squares=squares)
    inventory_points, inventory_layer = add_inventory(context=context, grid=grid, squares=squares)

    columns = output_columns()
    grid_path = context.output_dir / "grid.parquet"
    pq.write_table(
        pa.Table.from_pylist([{column: square.get(column) for column in columns} for square in squares]),
        grid_path,
    )

    layers_path = Path(settings.get("layers_path") or LAYERS_PATH)
    write_csv(
        rows=[dem_layer, *soil_layers, rock_layer, forest_layer, inventory_layer],
        columns=LAYER_COLUMNS,
        path=layers_path,
    )
    reports_dir = Path(settings.get("reports_dir") or REPORTS_DIR)
    coverage_path = reports_dir / "p2_coverage.csv"
    write_csv(
        rows=coverage_table(squares=squares),
        columns=["value", "squares_with_value", "total_squares", "share"],
        path=coverage_path,
    )
    gaps_path = reports_dir / "p2_gaps.csv"
    write_csv(rows=gaps_table(squares=squares), columns=["cell_id", "missing_values"], path=gaps_path)
    detail_path = reports_dir / "p2_detail.csv"
    write_csv(
        rows=detail_table(
            context=context,
            grid=grid,
            dem_path=dem_path,
            soil_paths=soil_paths,
            rock_answers=rock_answers,
            forest_path=forest_path,
            inventory_points=inventory_points,
            box=box,
        ),
        columns=DETAIL_COLUMNS,
        path=detail_path,
    )
    for path in (grid_path, layers_path, coverage_path, gaps_path, detail_path):
        context.add_output(path)
