"""P1: download porcini finds from GBIF and iNaturalist, clean them and count them."""

import json
import random
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pyarrow as pa
import pyarrow.parquet as pq

from micometeo.context import RunContext
from micometeo.finds import gbif, inaturalist, roads
from micometeo.finds.cleaning import apply_filters, mark_duplicates
from micometeo.finds.counts import (
    COUNT_COLUMNS,
    DROPPED_COLUMNS,
    count_table,
    dropped_table,
    in_stage,
    write_csv,
)
from micometeo.finds.records import FIND_COLUMNS

ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = ROOT / "reports"
RECORD_COLUMNS = FIND_COLUMNS + ["duplicate_rule", "failed_filter"]


def now_utc() -> str:
    """Return the current time in UTC as text."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def download_gbif(
    *, context: RunContext, settings: dict[str, Any]
) -> tuple[list[dict[str, Any]], str]:
    """Fetch the GBIF download, request a new one if no key is set, and parse it."""
    predicate = gbif.build_predicate(settings=settings)
    key = settings.get("gbif_download_key") or ""
    if not key:
        key = gbif.request_download(predicate=predicate, login=gbif.read_login())
    zip_path, status = gbif.fetch_download(key=key, raw_dir=context.raw_dir)
    retrieved_at = now_utc()
    records = gbif.parse_archive(zip_path=zip_path, settings=settings, retrieved_at=retrieved_at)
    context.add_source(
        name="GBIF occurrence download",
        url=f"https://www.gbif.org/occurrence/download/{key}",
        licence=json.dumps(Counter(record["licence"] for record in records)),
        version=status.get("doi") or "",
        downloaded_at=retrieved_at,
        query={
            "download_key": key,
            "doi": status.get("doi"),
            "created": status.get("created"),
            "total_records": status.get("totalRecords"),
            "predicate": predicate,
        },
    )
    context.add_input(zip_path)
    return records, (status.get("created") or retrieved_at)[:10]


def download_inaturalist(
    *, context: RunContext, settings: dict[str, Any]
) -> list[dict[str, Any]]:
    """Download and parse iNaturalist observations for every configured place."""
    records = []
    for place_name, place in settings["inat_places"].items():
        paths = inaturalist.download_place(
            settings=settings,
            place_name=place_name,
            place_id=place["place_id"],
            raw_dir=context.raw_dir,
        )
        retrieved_at = now_utc()
        place_records = inaturalist.parse_pages(
            paths=paths,
            area=place["area"],
            settings=settings,
            retrieved_at=retrieved_at,
            max_latitude=place.get("max_latitude"),
        )
        query = inaturalist.build_query(settings=settings, place_id=place["place_id"])
        query.pop("id_above")
        query["max_latitude"] = place.get("max_latitude")
        context.add_source(
            name=f"iNaturalist observations, {place_name}",
            url=inaturalist.API_URL,
            licence=json.dumps(Counter(record["licence"] for record in place_records)),
            version="v1",
            downloaded_at=retrieved_at,
            query=query,
        )
        for path in paths:
            context.add_input(path)
        records += place_records
    return records


def write_parquet(*, records: list[dict[str, Any]], path: Path) -> None:
    """Write records to a Parquet table with the shared find columns."""
    table = pa.Table.from_pylist(
        [{column: record.get(column) for column in RECORD_COLUMNS} for record in records]
    )
    pq.write_table(table, path)


def plot_map(*, records: list[dict[str, Any]], boxes: dict[str, Any], path: Path) -> None:
    """Plot eligible finds as dots, one panel per area. Blurred records have no position."""
    figure, axes = plt.subplots(1, 2, figsize=(12, 5))
    for axis, area, title in zip(
        axes, ["home", "comparison"], ["Tuscany and Apennines", "Switzerland and Austria"]
    ):
        points = [
            record
            for record in records
            if record["area"] == area
            and in_stage(record=record, stage="eligible")
            and not record["coordinates_obscured"]
            and record["latitude"] is not None
        ]
        box = boxes[area]
        axis.plot(
            [box["west"], box["east"], box["east"], box["west"], box["west"]],
            [box["south"], box["south"], box["north"], box["north"], box["south"]],
            color="0.8",
            linewidth=1,
        )
        axis.scatter(
            [record["longitude"] for record in points],
            [record["latitude"] for record in points],
            s=4,
            alpha=0.6,
        )
        axis.set_title(f"{title}: {len(points)} finds")
        axis.set_xlabel("Longitude")
        axis.set_ylabel("Latitude")
        axis.set_aspect("equal")
    figure.tight_layout()
    figure.savefig(path, dpi=120)
    plt.close(figure)


def road_check(
    *, context: RunContext, settings: dict[str, Any], records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Compare road and path distances of eligible finds with random places in each area."""
    options = settings["roads"]
    rng = random.Random(context.seed)
    shapes = roads.area_shapes(settings=settings, raw_dir=context.raw_dir)
    rows = []
    for area in ("home", "comparison"):
        finds = [
            (record["latitude"], record["longitude"])
            for record in records
            if record["area"] == area and in_stage(record=record, stage="eligible")
        ]
        if len(finds) > options["max_finds_per_area"]:
            finds = rng.sample(finds, options["max_finds_per_area"])
        groups = {
            "finds": finds,
            "random_places": roads.random_points(
                area=shapes[area], count=options["random_points_per_area"], rng=rng
            ),
        }
        extract_paths = [
            roads.download_extract(name=name, raw_dir=context.raw_dir)
            for name in options["extracts"][area]
        ]
        ways = roads.ways_near_points(
            paths=extract_paths, points=groups["finds"] + groups["random_places"]
        )
        for name, path in zip(options["extracts"][area], extract_paths, strict=True):
            context.add_input(path)
            context.add_source(
                name=f"OpenStreetMap extract {name} from Geofabrik",
                url=roads.GEOFABRIK_URL.format(name=name),
                licence="ODbL 1.0",
                version=roads.extract_date(path=path),
                downloaded_at=now_utc(),
                query={"highway": "any", "area": area, **options},
            )
        for group, points in groups.items():
            distances = roads.nearest_distances(
                points=points, ways=ways, radius_m=options["radius_m"]
            )
            for kind in ("road", "road_or_path"):
                summary = roads.summarise(
                    distances=[distance[kind] for distance in distances],
                    near_m=options["near_m"],
                    rng=rng,
                )
                rows.append({"area": area, "group": group, "nearest": kind, **summary})
    for path in sorted(context.raw_dir.glob("gadm41_*.json.zip")):
        context.add_input(path)
    context.add_source(
        name="GADM 4.1 area outlines",
        url=roads.GADM_URL,
        licence="GADM licence, free for non-commercial use",
        version="4.1",
        downloaded_at=now_utc(),
        query={"files": ["ITA_1", *options["gadm_countries"]]},
    )
    return rows


def run(context: RunContext) -> None:
    """Download, clean, count and plot porcini finds for both areas."""
    settings = context.config
    gbif_records, download_date = download_gbif(context=context, settings=settings)
    records = download_inaturalist(context=context, settings=settings) + gbif_records

    filters = settings["filters"]
    mark_duplicates(records=records, max_distance_m=filters["duplicate_distance_m"])
    apply_filters(records=records, filters=filters, download_date=download_date)

    all_path = context.output_dir / "all_records.parquet"
    write_parquet(records=records, path=all_path)
    finds_path = context.output_dir / "finds.parquet"
    write_parquet(
        records=[record for record in records if in_stage(record=record, stage="eligible")],
        path=finds_path,
    )

    reports_dir = Path(settings.get("reports_dir") or REPORTS_DIR)
    reports_dir.mkdir(parents=True, exist_ok=True)
    counts_path = reports_dir / "p1_counts.csv"
    write_csv(rows=count_table(records=records), columns=COUNT_COLUMNS, path=counts_path)
    dropped_path = reports_dir / "p1_dropped.csv"
    write_csv(rows=dropped_table(records=records), columns=DROPPED_COLUMNS, path=dropped_path)
    map_path = reports_dir / "p1_map.png"
    plot_map(records=records, boxes=filters["area_boxes"], path=map_path)

    road_path = reports_dir / "p1_road_distance.csv"
    road_rows = road_check(context=context, settings=settings, records=records)
    write_csv(rows=road_rows, columns=list(road_rows[0]), path=road_path)

    for path in (all_path, finds_path, counts_path, dropped_path, map_path, road_path):
        context.add_output(path)
