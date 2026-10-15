"""Distance from finds and from random places to the nearest road or path in OpenStreetMap.

Roads come from Geofabrik regional extracts, read locally, so no shared server is involved.
"""

import json
import math
import random
import statistics
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import osmium
import osmium.filter
from pyproj import Transformer
from shapely import STRtree
from shapely.geometry import LineString, Point, box, shape
from shapely.ops import unary_union

GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_{name}.json.zip"
GEOFABRIK_URL = "https://download.geofabrik.de/europe/{name}-latest.osm.pbf"
USER_AGENT = "sporameteo-experiments/0.1 (research prototype)"
TIMEOUT_SECONDS = 600
PATH_TYPES = {"path", "footway", "track", "bridleway", "steps", "cycleway"}
IGNORED_TYPES = {
    "proposed",
    "construction",
    "abandoned",
    "razed",
    "platform",
    "corridor",
    "elevator",
    "bus_stop",
}
# Grid squares of 0.02 degrees, checked with their neighbours, reach at least 1.5 km
# from any point in the Alps and Apennines, which is more than the 1 km radius.
NEAR_CELL_DEGREES = 0.02
_TO_LAEA = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)


def _download(*, url: str, path: Path) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as reply:
        with temp_path.open("wb") as handle:
            while chunk := reply.read(1024 * 1024):
                handle.write(chunk)
    temp_path.replace(path)
    return path


def load_gadm(*, name: str, raw_dir: Path) -> list[dict[str, Any]]:
    """Download a GADM 4.1 outline file, reusing a saved copy, and return its features."""
    zip_path = _download(url=GADM_URL.format(name=name), path=raw_dir / f"gadm41_{name}.json.zip")
    with zipfile.ZipFile(zip_path) as archive:
        return json.loads(archive.read(archive.namelist()[0]))["features"]


def area_shapes(*, settings: dict[str, Any], raw_dir: Path) -> dict[str, Any]:
    """Build the home and comparison outlines used to draw random places."""
    regions = {
        feature["properties"]["GID_1"]: shape(feature["geometry"])
        for feature in load_gadm(name="ITA_1", raw_dir=raw_dir)
    }
    emilia = settings["emilia_apennines"]
    emilia_box = box(emilia["west"], emilia["south"], emilia["east"], emilia["north"])
    home = unary_union(
        [regions[settings["tuscany_gid"]], regions[emilia["gid"]].intersection(emilia_box)]
    )
    countries = [
        shape(feature["geometry"])
        for name in settings["roads"]["gadm_countries"]
        for feature in load_gadm(name=name, raw_dir=raw_dir)
    ]
    return {"home": home, "comparison": unary_union(countries)}


def random_points(*, area: Any, count: int, rng: random.Random) -> list[tuple[float, float]]:
    """Draw places spread evenly over an outline, as latitude and longitude pairs."""
    west, south, east, north = area.bounds
    points: list[tuple[float, float]] = []
    while len(points) < count:
        longitude, latitude = rng.uniform(west, east), rng.uniform(south, north)
        if area.contains(Point(longitude, latitude)):
            points.append((latitude, longitude))
    return points


def download_extract(*, name: str, raw_dir: Path) -> Path:
    """Download a Geofabrik extract such as italy/centro, reusing a saved copy."""
    file_name = name.split("/")[-1] + "-latest.osm.pbf"
    return _download(url=GEOFABRIK_URL.format(name=name), path=raw_dir / "osm" / file_name)


def extract_date(*, path: Path) -> str:
    """Return the date of the OpenStreetMap data inside an extract."""
    header = osmium.io.Reader(str(path), osmium.osm.NOTHING).header()
    return header.get("osmosis_replication_timestamp", "")


def _cell(longitude: float, latitude: float) -> tuple[int, int]:
    return (
        math.floor(longitude / NEAR_CELL_DEGREES),
        math.floor(latitude / NEAR_CELL_DEGREES),
    )


def near_cells(*, points: list[tuple[float, float]]) -> set[tuple[int, int]]:
    """Return the grid squares that hold a point, plus their eight neighbours."""
    cells = set()
    for latitude, longitude in points:
        x, y = _cell(longitude, latitude)
        cells.update((x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    return cells


def label_way(*, highway: str) -> str:
    """Return road or path for an OpenStreetMap highway type, or empty to skip it."""
    if highway in IGNORED_TYPES:
        return ""
    return "path" if highway in PATH_TYPES else "road"


def ways_near_points(
    *, paths: list[Path], points: list[tuple[float, float]]
) -> list[tuple[str, LineString]]:
    """Read roads and paths from extracts, keeping only ways that pass near a point."""
    cells = near_cells(points=points)
    ways = []
    for path in paths:
        processor = (
            osmium.FileProcessor(str(path))
            .with_locations()
            .with_filter(osmium.filter.EntityFilter(osmium.osm.WAY))
            .with_filter(osmium.filter.KeyFilter("highway"))
        )
        for way in processor:
            label = label_way(highway=way.tags.get("highway", ""))
            if not label:
                continue
            coordinates = [
                (node.lon, node.lat) for node in way.nodes if node.location.valid()
            ]
            if len(coordinates) < 2:
                continue
            if not any(_cell(lon, lat) in cells for lon, lat in coordinates):
                continue
            ways.append((label, to_metres(coordinates=coordinates)))
    return ways


def to_metres(*, coordinates: list[tuple[float, float]]) -> LineString:
    """Turn longitude and latitude pairs into a line in EPSG:3035 metres."""
    eastings, northings = _TO_LAEA.transform(
        [lon for lon, _ in coordinates], [lat for _, lat in coordinates]
    )
    return LineString(zip(eastings, northings, strict=True))


def nearest_distances(
    *,
    points: list[tuple[float, float]],
    ways: list[tuple[str, LineString]],
    radius_m: int,
) -> list[dict[str, float]]:
    """Return the distance to the nearest road and to the nearest road or path, capped at radius_m."""
    lines = {
        "road": [line for label, line in ways if label == "road"],
        "road_or_path": [line for _, line in ways],
    }
    trees = {name: STRtree(group) if group else None for name, group in lines.items()}
    results = []
    for latitude, longitude in points:
        point = Point(_TO_LAEA.transform(longitude, latitude))
        distances = {}
        for name, tree in trees.items():
            if tree is None:
                distances[name] = float(radius_m)
                continue
            nearest = lines[name][tree.nearest(point)]
            distances[name] = min(point.distance(nearest), float(radius_m))
        results.append(distances)
    return results


def summarise(
    *, distances: list[float], near_m: float, rng: random.Random, repeats: int = 1000
) -> dict[str, Any]:
    """Median distance and share of points within near_m, each with a 95 percent range.

    The range comes from redrawing the points with replacement many times.
    """
    count = len(distances)
    medians, shares = [], []
    for _ in range(repeats):
        sample = [distances[rng.randrange(count)] for _ in range(count)]
        medians.append(statistics.median(sample))
        shares.append(sum(value <= near_m for value in sample) / count)
    medians.sort()
    shares.sort()
    low, high = int(repeats * 0.025), int(repeats * 0.975) - 1
    return {
        "points": count,
        "median_m": round(statistics.median(distances)),
        "median_low_m": round(medians[low]),
        "median_high_m": round(medians[high]),
        "share_near": round(sum(value <= near_m for value in distances) / count, 3),
        "share_near_low": round(shares[low], 3),
        "share_near_high": round(shares[high], 3),
    }
