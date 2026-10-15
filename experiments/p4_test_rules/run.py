"""P4a: split find days into tuning, test and final sets so the sets stay apart in space and time."""

import csv
import json
import math
import random
import time
import tomllib
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import rasterio
import shapely
from pyproj import Transformer
from rasterio.warp import transform_bounds

from sporameteo.context import RunContext
from sporameteo.finds.roads import area_shapes
from sporameteo.habitat.forest import LICENCE, SERVICE_URL, mask_unusable
from sporameteo.habitat.grid import read_download_note, write_download_note

ROOT = Path(__file__).resolve().parent.parent.parent
SQUARE_SIZE_M = 500
TO_WGS84 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)
PIXELS_PER_SIDE = SQUARE_SIZE_M // 100
POINT_COLUMNS = [
    "case_id",
    "set",
    "area",
    "point_kind",
    "cell_id",
    "latitude",
    "longitude",
    "assessment_date",
]
POINT_COUNT_COLUMNS = ["area", "set", "point_kind", "cases_with_points", "points", "cases_without_known_spots"]
CASE_COLUMNS = [
    "case_id",
    "area",
    "cell_id",
    "assessment_date",
    "year",
    "block_id",
    "block_group",
    "set",
    "record_ids",
    "find_count",
    "latitude",
    "longitude",
]
BLOCK_COLUMNS = ["block_id", "block_group", "comparison_cases"]
COUNT_COLUMNS = ["area", "set", "year_band", "cases", "finds"]
HOME_GROUP = "home"


def write_csv(*, rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def read_finds(*, path: Path) -> list[dict[str, Any]]:
    columns = ["record_id", "area", "event_date", "year", "latitude", "longitude", "cell_id"]
    finds = pq.read_table(path, columns=columns).to_pylist()
    return sorted(finds, key=lambda find: find["record_id"])


def parse_cell_id(*, cell_id: str) -> tuple[int, int]:
    """Return the lower-left corner (east, north) of a square ID like 500m_E4465500_N2301000."""
    _, east, north = cell_id.split("_")
    return int(east.removeprefix("E")), int(north.removeprefix("N"))


def block_corner(*, east: int, north: int, block_size_m: int) -> tuple[int, int]:
    return east // block_size_m * block_size_m, north // block_size_m * block_size_m


def block_id_for(*, cell_id: str, block_size_m: int) -> str:
    """Return the ID of the block that holds the lower-left corner of the square."""
    east, north = parse_cell_id(cell_id=cell_id)
    block_east, block_north = block_corner(east=east, north=north, block_size_m=block_size_m)
    return f"{block_size_m // 1000}km_E{block_east}_N{block_north}"


def parse_block_id(*, block_id: str) -> tuple[int, int, int]:
    """Return the block size in metres and its lower-left corner (east, north)."""
    size, east, north = block_id.split("_")
    return int(size.removesuffix("km")) * 1000, int(east.removeprefix("E")), int(north.removeprefix("N"))


def square_centre(*, cell_id: str) -> tuple[float, float]:
    """Return the centre of the square in EPSG:3035 metres."""
    east, north = parse_cell_id(cell_id=cell_id)
    return east + SQUARE_SIZE_M / 2, north + SQUARE_SIZE_M / 2


def distance_to_block(*, east: float, north: float, block_id: str) -> float:
    """Return the distance in metres from a point to a block, 0 inside it."""
    size, block_east, block_north = parse_block_id(block_id=block_id)
    gap_east = max(block_east - east, 0, east - (block_east + size))
    gap_north = max(block_north - north, 0, north - (block_north + size))
    return (gap_east**2 + gap_north**2) ** 0.5


def build_cases(*, finds: list[dict[str, Any]], block_size_m: int) -> list[dict[str, Any]]:
    """Group finds into one case per 500 m square and day, sorted by case ID."""
    grouped: dict[str, dict[str, Any]] = {}
    for find in finds:
        case_id = f"{find['cell_id']}_{find['event_date']}"
        case = grouped.get(case_id)
        if case is None:
            east, north = square_centre(cell_id=find["cell_id"])
            longitude, latitude = TO_WGS84.transform(east, north)
            case = grouped[case_id] = {
                "case_id": case_id,
                "area": find["area"],
                "cell_id": find["cell_id"],
                "assessment_date": find["event_date"],
                "year": int(find["year"]),
                "block_id": block_id_for(cell_id=find["cell_id"], block_size_m=block_size_m),
                "record_ids": [],
                "latitude": latitude,
                "longitude": longitude,
            }
        case["record_ids"].append(find["record_id"])
    cases = [grouped[case_id] for case_id in sorted(grouped)]
    for case in cases:
        case["record_ids"] = sorted(case["record_ids"])
        case["find_count"] = len(case["record_ids"])
    return cases


def assign_block_groups(
    *, block_counts: dict[str, int], seed: int, tuning_share: float, test_share: float
) -> dict[str, str]:
    """Shuffle the blocks with the seed and fill tuning, then test, then final by share of cases."""
    total = sum(block_counts.values())
    tuning_limit = tuning_share * total
    test_limit = (tuning_share + test_share) * total
    order = sorted(block_counts)
    random.Random(seed).shuffle(order)
    groups: dict[str, str] = {}
    running = 0
    for block_id in order:
        if running < tuning_limit:
            groups[block_id] = "tuning"
        elif running < test_limit:
            groups[block_id] = "test"
        else:
            groups[block_id] = "final"
        running += block_counts[block_id]
    return groups


def near_held_out_block(*, case: dict[str, Any], held_out: list[str], buffer_m: float) -> bool:
    east, north = square_centre(cell_id=case["cell_id"])
    return any(distance_to_block(east=east, north=north, block_id=block) <= buffer_m for block in held_out)


def set_for_case(
    *,
    case: dict[str, Any],
    block_group: str,
    held_out_blocks: list[str],
    final_from_year: int,
    test_from_year: int,
    buffer_m: float,
) -> str:
    """Return the set of a case. The first rule that matches wins."""
    if case["area"] == "home":
        return "home_test" if case["year"] < final_from_year else "home_final"
    if case["year"] >= final_from_year or block_group == "final":
        return "final"
    if case["year"] >= test_from_year or block_group == "test":
        return "test"
    if near_held_out_block(case=case, held_out=held_out_blocks, buffer_m=buffer_m):
        return "buffer"
    return "tuning"


def assign_sets(*, cases: list[dict[str, Any]], settings: dict[str, Any], seed: int) -> list[dict[str, Any]]:
    """Add block_group and set to every case. Return the blocks of the comparison area."""
    block_counts: dict[str, int] = defaultdict(int)
    for case in cases:
        if case["area"] != "home":
            block_counts[case["block_id"]] += 1
    groups = assign_block_groups(
        block_counts=block_counts,
        seed=seed,
        tuning_share=settings["tuning_share"],
        test_share=settings["test_share"],
    )
    held_out = sorted(block for block, group in groups.items() if group in ("test", "final"))
    for case in cases:
        case["block_group"] = HOME_GROUP if case["area"] == "home" else groups[case["block_id"]]
        case["set"] = set_for_case(
            case=case,
            block_group=case["block_group"],
            held_out_blocks=held_out,
            final_from_year=settings["final_from_year"],
            test_from_year=settings["test_from_year"],
            buffer_m=settings["buffer_m"],
        )
    return [
        {"block_id": block, "block_group": groups[block], "comparison_cases": block_counts[block]}
        for block in sorted(groups)
    ]


def check_separation(*, cases: list[dict[str, Any]], buffer_m: float) -> None:
    """Raise ValueError if a find is in two sets, tuning touches held-out blocks, or home is tuning."""
    set_of_record: dict[str, str] = {}
    for case in cases:
        for record_id in case["record_ids"]:
            earlier = set_of_record.setdefault(record_id, case["set"])
            if earlier != case["set"]:
                raise ValueError(f"Find {record_id} is in sets {earlier} and {case['set']}")
    held_out = sorted({case["block_id"] for case in cases if case["block_group"] in ("test", "final")})
    for case in cases:
        if case["set"] != "tuning":
            continue
        if case["area"] == "home":
            raise ValueError(f"Home case {case['case_id']} is in tuning")
        if case["block_group"] in ("test", "final"):
            raise ValueError(f"Tuning case {case['case_id']} lies in a {case['block_group']} block")
        if near_held_out_block(case=case, held_out=held_out, buffer_m=buffer_m):
            raise ValueError(f"Tuning case {case['case_id']} lies within {buffer_m} m of a test or final block")


def year_band(*, year: int, settings: dict[str, Any]) -> str:
    if year >= settings["final_from_year"]:
        return f"{settings['final_from_year']} and later"
    if year >= settings["test_from_year"]:
        return f"{settings['test_from_year']} to {settings['final_from_year'] - 1}"
    return f"before {settings['test_from_year']}"


def count_rows(*, cases: list[dict[str, Any]], settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Count cases and finds per area and set, and per area, set and year band. Counts only."""
    totals: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0])
    for case in cases:
        band = year_band(year=case["year"], settings=settings)
        for key in ((case["area"], case["set"], "all"), (case["area"], case["set"], band)):
            totals[key][0] += 1
            totals[key][1] += case["find_count"]
    return [
        {"area": area, "set": set_name, "year_band": band, "cases": cases_count, "finds": finds_count}
        for (area, set_name, band), (cases_count, finds_count) in sorted(totals.items())
    ]


def align_bounds(*, bounds: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    """Widen west, south, east, north bounds to whole multiples of the square size."""
    west, south, east, north = bounds
    step = SQUARE_SIZE_M
    return (
        math.floor(west / step) * step,
        math.floor(south / step) * step,
        math.ceil(east / step) * step,
        math.ceil(north / step) * step,
    )


def tile_boxes(*, bounds: tuple[int, int, int, int], tile_m: int) -> list[tuple[int, int, int, int]]:
    """Cut aligned bounds into boxes no larger than tile_m on a side, west to east, south to north."""
    west, south, east, north = bounds
    return [
        (tile_west, tile_south, min(tile_west + tile_m, east), min(tile_south + tile_m, north))
        for tile_south in range(south, north, tile_m)
        for tile_west in range(west, east, tile_m)
    ]


def tile_query(*, box: tuple[int, int, int, int], pixel_m: int) -> dict[str, Any]:
    """Return the image service parameters that ask for one tile in pixel_m metre pixels."""
    west, south, east, north = box
    return {
        "bbox": f"{west},{south},{east},{north}",
        "bboxSR": 3035,
        "imageSR": 3035,
        "size": f"{(east - west) // pixel_m},{(north - south) // pixel_m}",
        "format": "tiff",
        "pixelType": "U8",
        "interpolation": "RSP_NearestNeighbor",
        "f": "image",
    }


def download_tile(*, context: RunContext, box: tuple[int, int, int, int], pixel_m: int) -> Path:
    """Save one forest type tile, unless it is already saved, and record it in the run."""
    path = context.raw_dir / f"forest_type_2018_{pixel_m}m_E{box[0]}_N{box[1]}_E{box[2]}_N{box[3]}.tif"
    query = tile_query(box=box, pixel_m=pixel_m)
    if not path.exists():
        with urllib.request.urlopen(SERVICE_URL + "?" + urllib.parse.urlencode(query), timeout=300) as response:
            content = response.read()
        if content[:2] not in (b"II", b"MM"):
            raise ValueError(f"The image service did not return a GeoTIFF: {content[:200]!r}")
        path.write_bytes(content)
        write_download_note(path=path, details={"url": SERVICE_URL, "query": query})
    note = read_download_note(path=path)
    context.add_source(
        name="Copernicus forest type 2018 tile",
        url=note["url"],
        licence=LICENCE,
        version="Forest type 2018 from the EEA image service",
        downloaded_at=note["downloaded_at"],
        query=note["query"],
    )
    context.add_input(path)
    return path


def square_forest_shares(*, pixels: np.ndarray) -> np.ndarray:
    """Return the share of forest pixels among usable ones for each 500 m square, NaN if none are usable.

    The pixels are 100 m values: 0 no forest, 1 broadleaf, 2 conifer, above 2 unusable.
    """
    values = mask_unusable(pixels=pixels)
    rows, columns = values.shape
    blocks = values.reshape(rows // PIXELS_PER_SIDE, PIXELS_PER_SIDE, columns // PIXELS_PER_SIDE, PIXELS_PER_SIDE)
    usable = (~np.isnan(blocks)).sum(axis=(1, 3))
    forest = ((blocks == 1) | (blocks == 2)).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(usable > 0, forest / np.maximum(usable, 1), np.nan)


def forest_square_corners(
    *, pixels: np.ndarray, west: int, north: int, from_share: float
) -> tuple[np.ndarray, np.ndarray]:
    """Return the lower-left corners (east, north) of the forest squares of a tile.

    West and north are the top-left corner of the tile. A square with no usable pixel is not forest.
    """
    shares = square_forest_shares(pixels=pixels)
    rows, columns = np.nonzero(np.nan_to_num(shares, nan=-1.0) >= from_share)
    return west + columns * SQUARE_SIZE_M, north - (rows + 1) * SQUARE_SIZE_M


def read_tile_squares(*, path: Path, box: tuple[int, int, int, int], pixel_m: int, from_share: float):
    expected = ((box[3] - box[1]) // pixel_m, (box[2] - box[0]) // pixel_m)
    with rasterio.open(path) as source:
        pixels = source.read(1)
    if pixels.shape != expected:
        raise ValueError(f"{path.name} has shape {pixels.shape}, expected {expected}")
    return forest_square_corners(pixels=pixels, west=box[0], north=box[3], from_share=from_share)


def squares_inside(*, east: np.ndarray, north: np.ndarray, outline: Any) -> np.ndarray:
    """Return a mask of the squares whose centre lies inside the outline, a shape in degrees."""
    longitude, latitude = TO_WGS84.transform(east + SQUARE_SIZE_M / 2, north + SQUARE_SIZE_M / 2)
    return shapely.contains_xy(outline, longitude, latitude)


def near_blocks_mask(*, east: np.ndarray, north: np.ndarray, blocks: list[str], distance_m: float) -> np.ndarray:
    """Return a mask of the squares whose centre is within distance_m of any of the blocks."""
    centre_east, centre_north = east + SQUARE_SIZE_M / 2, north + SQUARE_SIZE_M / 2
    near = np.zeros(east.shape, dtype=bool)
    for block_id in blocks:
        size, block_east, block_north = parse_block_id(block_id=block_id)
        gap_east = np.maximum(np.maximum(block_east - centre_east, centre_east - (block_east + size)), 0)
        gap_north = np.maximum(np.maximum(block_north - centre_north, centre_north - (block_north + size)), 0)
        near |= np.hypot(gap_east, gap_north) <= distance_m
    return near


def sorted_pool(*, east: np.ndarray, north: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.lexsort((north, east))
    return east[order], north[order]


def build_pools(
    *,
    squares: dict[str, tuple[np.ndarray, np.ndarray]],
    groups: dict[str, str],
    block_size_m: int,
    buffer_m: float,
) -> dict[tuple[str, str, bool], tuple[np.ndarray, np.ndarray]]:
    """Return forest squares per (area, block group, tuning buffer applied).

    The home area is one group. Comparison squares count only in blocks that hold a case.
    The buffered tuning pool drops squares within buffer_m of a test or final block.
    """
    pools: dict[tuple[str, str, bool], tuple[np.ndarray, np.ndarray]] = {}
    pools[("home", HOME_GROUP, False)] = sorted_pool(east=squares["home"][0], north=squares["home"][1])
    east, north = squares["comparison"]
    block_east, block_north = east // block_size_m * block_size_m, north // block_size_m * block_size_m
    for group in ("tuning", "test", "final"):
        keep = np.zeros(east.shape, dtype=bool)
        for block_id, block_group in groups.items():
            if block_group == group:
                _, corner_east, corner_north = parse_block_id(block_id=block_id)
                keep |= (block_east == corner_east) & (block_north == corner_north)
        pools[("comparison", group, False)] = sorted_pool(east=east[keep], north=north[keep])
    held_out = sorted(block for block, group in groups.items() if group in ("test", "final"))
    tuning_east, tuning_north = pools[("comparison", "tuning", False)]
    far = ~near_blocks_mask(east=tuning_east, north=tuning_north, blocks=held_out, distance_m=buffer_m)
    pools[("comparison", "tuning", True)] = (tuning_east[far], tuning_north[far])
    return pools


def cell_id_for(*, east: int, north: int) -> str:
    return f"{SQUARE_SIZE_M}m_E{east}_N{north}"


def draw_forest_points(
    *, pool: tuple[np.ndarray, np.ndarray], excluded: set[str], count: int, rng: random.Random
) -> list[str]:
    """Draw up to count squares from the pool without replacement, skipping the excluded cell IDs.

    The draw takes enough extra indexes to cover every excluded square, then drops them.
    """
    east, north = pool
    wanted = min(len(east), count + len(excluded))
    chosen: list[str] = []
    for index in rng.sample(range(len(east)), wanted):
        cell_id = cell_id_for(east=int(east[index]), north=int(north[index]))
        if cell_id not in excluded:
            chosen.append(cell_id)
            if len(chosen) == count:
                break
    return chosen


def build_points(
    *,
    cases: list[dict[str, Any]],
    pools: dict[tuple[str, str, bool], tuple[np.ndarray, np.ndarray]],
    settings: dict[str, Any],
    rng: random.Random,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the comparison points and the cases that got no known spots.

    Cases are taken in sorted case_id order and share one random generator, so a run repeats.
    Buffer cases get no points.
    """
    find_cells_by_day: dict[str, set[str]] = defaultdict(set)
    dates_by_cell: dict[tuple[str, str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for case in cases:
        find_cells_by_day[case["assessment_date"]].add(case["cell_id"])
        dates_by_cell[(case["area"], case["block_group"], case["set"])][case["cell_id"]].add(case["assessment_date"])
    points: list[dict[str, Any]] = []
    without_known: list[dict[str, Any]] = []
    for case in sorted(cases, key=lambda item: item["case_id"]):
        if case["set"] == "buffer":
            continue
        day = case["assessment_date"]
        excluded = find_cells_by_day[day]
        base = {"case_id": case["case_id"], "set": case["set"], "area": case["area"], "assessment_date": day}
        pool = pools[(case["area"], case["block_group"], case["set"] == "tuning")]
        forest = draw_forest_points(pool=pool, excluded=excluded, count=settings["forest_points_per_case"], rng=rng)
        points += [{**base, "point_kind": "forest", "cell_id": cell_id} for cell_id in forest]
        known = sorted(
            cell_id
            for cell_id, dates in dates_by_cell[(case["area"], case["block_group"], case["set"])].items()
            if dates != {day} and cell_id not in excluded
        )
        if len(known) < settings["min_known_spots"]:
            without_known.append(case)
            continue
        for cell_id in rng.sample(known, min(len(known), settings["known_spots_per_case"])):
            points.append({**base, "point_kind": "known_spot", "cell_id": cell_id})
    return points, without_known


def add_coordinates(*, points: list[dict[str, Any]]) -> None:
    """Add the latitude and longitude of the square centre to every point."""
    corners = [parse_cell_id(cell_id=point["cell_id"]) for point in points]
    if not corners:
        return
    east = np.array([corner[0] + SQUARE_SIZE_M / 2 for corner in corners])
    north = np.array([corner[1] + SQUARE_SIZE_M / 2 for corner in corners])
    longitude, latitude = TO_WGS84.transform(east, north)
    for point, lat, lon in zip(points, latitude, longitude):
        point["latitude"], point["longitude"] = float(lat), float(lon)


def point_count_rows(*, points: list[dict[str, Any]], without_known: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Count the cases with points, the points and the cases with no known spots. Counts only."""
    cases_with: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    totals: dict[tuple[str, str, str], int] = defaultdict(int)
    for point in points:
        key = (point["area"], point["set"], point["point_kind"])
        cases_with[key].add(point["case_id"])
        totals[key] += 1
    missing: dict[tuple[str, str], int] = defaultdict(int)
    for case in without_known:
        missing[(case["area"], case["set"])] += 1
    keys = set(totals) | {(area, set_name, "known_spot") for area, set_name in missing}
    return [
        {
            "area": area,
            "set": set_name,
            "point_kind": kind,
            "cases_with_points": len(cases_with[(area, set_name, kind)]),
            "points": totals[(area, set_name, kind)],
            "cases_without_known_spots": missing[(area, set_name)] if kind == "known_spot" else 0,
        }
        for area, set_name, kind in sorted(keys)
    ]


def load_forest_squares(*, context: RunContext, outlines: dict[str, Any]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Download the forest tiles of each area and return its forest squares inside the outline."""
    settings = context.config
    squares: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for area, outline in outlines.items():
        bounds = align_bounds(bounds=transform_bounds("EPSG:4326", "EPSG:3035", *outline.bounds, densify_pts=21))
        found_east, found_north = [], []
        for box in tile_boxes(bounds=bounds, tile_m=settings["tile_pixels"] * settings["pixel_m"]):
            path = download_tile(context=context, box=box, pixel_m=settings["pixel_m"])
            tile_east, tile_north = read_tile_squares(
                path=path, box=box, pixel_m=settings["pixel_m"], from_share=settings["forest_from_share"]
            )
            found_east.append(tile_east)
            found_north.append(tile_north)
        east, north = np.concatenate(found_east), np.concatenate(found_north)
        inside = squares_inside(east=east, north=north, outline=outline)
        squares[area] = (east[inside], north[inside])
    return squares


def run(context: RunContext) -> None:
    """Group finds into cases, assign sets, check the separation, then draw comparison points."""
    started = time.monotonic()
    settings = context.config
    reports_dir = Path(settings.get("reports_dir") or "reports")
    if not reports_dir.is_absolute():
        reports_dir = ROOT / reports_dir
    finds_path = Path(settings["finds_path"])
    if not finds_path.is_absolute():
        finds_path = ROOT / finds_path
    context.add_input(finds_path)

    finds = read_finds(path=finds_path)
    cases = build_cases(finds=finds, block_size_m=settings["block_size_m"])
    blocks = assign_sets(cases=cases, settings=settings, seed=context.seed)
    check_separation(cases=cases, buffer_m=settings["buffer_m"])

    cases_path = context.output_dir / "cases.parquet"
    pq.write_table(pa.Table.from_pylist([{column: case[column] for column in CASE_COLUMNS} for case in cases]), cases_path)
    blocks_path = context.output_dir / "blocks.csv"
    write_csv(rows=blocks, columns=BLOCK_COLUMNS, path=blocks_path)
    counts = count_rows(cases=cases, settings=settings)
    counts_path = reports_dir / "p4a_split_counts.csv"
    write_csv(rows=counts, columns=COUNT_COLUMNS, path=counts_path)
    for path in (cases_path, blocks_path, counts_path):
        context.add_output(path)

    # Area outlines come from the GADM files that the P1 run saved. Nothing is downloaded for them.
    p1_config = ROOT / settings["p1_config_path"]
    p1_settings = tomllib.loads(p1_config.read_text(encoding="utf-8"))["settings"]
    outlines = area_shapes(settings=p1_settings, raw_dir=ROOT / settings["p1_raw_dir"])
    squares = load_forest_squares(context=context, outlines=outlines)
    groups = {block["block_id"]: block["block_group"] for block in blocks}
    pools = build_pools(
        squares=squares, groups=groups, block_size_m=settings["block_size_m"], buffer_m=settings["buffer_m"]
    )
    pool_sizes = {f"{area}/{group}{'/buffer_dropped' if buffered else ''}": len(pool[0]) for (area, group, buffered), pool in pools.items()}

    points, without_known = build_points(cases=cases, pools=pools, settings=settings, rng=random.Random(context.seed))
    add_coordinates(points=points)
    points_path = context.output_dir / "comparison_points.parquet"
    pq.write_table(pa.Table.from_pylist([{column: point[column] for column in POINT_COLUMNS} for point in points]), points_path)
    point_counts_path = reports_dir / "p4a_point_counts.csv"
    write_csv(rows=point_count_rows(points=points, without_known=without_known), columns=POINT_COUNT_COLUMNS, path=point_counts_path)
    for path in (points_path, point_counts_path):
        context.add_output(path)
    print(json.dumps({"pool_sizes": pool_sizes, "points": len(points), "seconds": round(time.monotonic() - started)}, indent=2))
