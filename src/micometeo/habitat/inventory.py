"""Forest type from the Tuscany forest inventory, one survey point per 400 m cell.

Field teams visited the points between 1985 and 1993. Only the attribute table is read.
"""

import io
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import shapefile
from pyproj import Transformer

from micometeo.finds.grid import CELL_SIZE_M
from micometeo.habitat.grid import SampleGrid, write_download_note

LAYER_ID = "toscana_inventario_forestale_400m"
DOWNLOAD_URL = "https://www502.regione.toscana.it/geoscopio/download/tematici/ift/ift.zip"
LICENCE = "CC BY-SA 4.0"
RAW_DIR_NAME = "toscana_inventario_forestale"
TABLE_NAME = "ift_1c_polygon.dbf"
ENCODING = "cp1252"
# Margin in metres around the grid when picking points, so no point near an edge is lost.
MARGIN_M = 1000
NOT_WOODLAND = "not woodland"
CATEGORY_NAMES = {
    "Cerrete": "Turkey oak woods",
    "Castagneti": "chestnut woods",
    "Leccete": "holm oak woods",
    "Querceti di Roverella": "downy oak woods",
    "Faggete": "beech woods",
    "Ostrieti": "hop hornbeam woods",
    "Robinieti": "black locust woods",
    "Abetine": "silver fir woods",
    "Pinete di pino marittimo": "maritime pine woods",
    "Pinete di rimboschimento di pino nero": "planted black pine woods",
    "Pinete di pino domestico": "stone pine woods",
    "Pinete di pino d'Aleppo": "Aleppo pine woods",
    "Cipressete": "cypress woods",
    "Sugherete": "cork oak woods",
    "Impianti di douglasia": "Douglas fir plantations",
    "Impianti di specie non spontanee di minore impiego": "plantations of other non-native trees",
    "Boschi alveali e ripari": "riverside woods",
    "Alneti di ontano bianco e ontano napoletano": "alder woods",
    "Boschi planiziali di latifoglie miste": "lowland mixed broadleaf woods",
    "Boschi misti con betulla": "mixed woods with birch",
    "Boschi misti con cerro, rovere e carpino bianco": "mixed oak and hornbeam woods",
    "Macchie mediterranee": "Mediterranean scrub",
    "Arbusteti di post-coltura": "shrubs on former farmland",
    "terreni saldi": "open grassland or pasture",
    "non classificabile": "unclassified woodland",
}
LEAF_TYPES = {"latifoglie": "broadleaf", "conifere": "conifer"}


def download_inventory(*, raw_dir: Path) -> Path:
    """Unpack the inventory into the raw folder and return the attribute table, unless it is there."""
    folder = raw_dir / RAW_DIR_NAME
    path = folder / TABLE_NAME
    if path.exists():
        return path
    with urllib.request.urlopen(DOWNLOAD_URL, timeout=600) as response:
        outer = zipfile.ZipFile(io.BytesIO(response.read()))
    inner_name = next(name for name in outer.namelist() if name.startswith("ift_") and name.endswith(".zip"))
    inner = zipfile.ZipFile(io.BytesIO(outer.read(inner_name)))
    folder.mkdir(parents=True, exist_ok=True)
    inner.extractall(folder)
    write_download_note(path=path, details={"url": DOWNLOAD_URL, "files": inner.namelist()})
    return path


def english_name(*, category: str | None) -> str:
    """Return the English name of a forest category, or raise if the category is unknown."""
    text = " ".join((category or "").split())
    if not text:
        return NOT_WOODLAND
    if text not in CATEGORY_NAMES:
        raise ValueError(f"Unknown forest category in the inventory: {text!r}")
    return CATEGORY_NAMES[text]


def leaf_type_of(*, conifer_or_broadleaf: str | None) -> str | None:
    """Return broadleaf or conifer from the inventory text, or None when it is not forest."""
    return LEAF_TYPES.get((conifer_or_broadleaf or "").strip().lower())


def read_points(*, path: Path, grid: SampleGrid) -> list[dict[str, Any]]:
    """Return the survey points near the grid with EPSG:3035 position, English name and leaf type."""
    to_gauss_boaga = Transformer.from_crs("EPSG:3035", "EPSG:3003", always_xy=True)
    to_laea = Transformer.from_crs("EPSG:3003", "EPSG:3035", always_xy=True)
    corners_e, corners_n = to_gauss_boaga.transform(
        [grid.west_e, grid.east_e, grid.west_e, grid.east_e],
        [grid.south_n, grid.south_n, grid.north_n, grid.north_n],
    )
    west, east = min(corners_e) - MARGIN_M, max(corners_e) + MARGIN_M
    south, north = min(corners_n) - MARGIN_M, max(corners_n) + MARGIN_M
    kept = []
    with path.open("rb") as handle:
        reader = shapefile.Reader(dbf=handle, encoding=ENCODING)
        for record in reader.iterRecords(fields=["X_COORD", "Y_COORD", "CATFOR", "CONIF_LAT"]):
            x_coord, y_coord, category, conifer_or_broadleaf = record
            if x_coord is None or y_coord is None:
                continue
            if west <= x_coord <= east and south <= y_coord <= north:
                kept.append((x_coord, y_coord, category, conifer_or_broadleaf))
    if not kept:
        return []
    eastings, northings = to_laea.transform([k[0] for k in kept], [k[1] for k in kept])
    return [
        {
            "easting": float(easting),
            "northing": float(northing),
            "name": english_name(category=category),
            "leaf_type": leaf_type_of(conifer_or_broadleaf=conifer_or_broadleaf),
        }
        for easting, northing, (_, _, category, conifer_or_broadleaf) in zip(eastings, northings, kept)
    ]


def points_by_square(*, points: list[dict[str, Any]], grid: SampleGrid) -> list[list[dict[str, Any]]]:
    """Return the points inside each square, in the same order as the squares of the grid."""
    squares: list[list[dict[str, Any]]] = [[] for _ in range(grid.rows * grid.columns)]
    for point in points:
        column = int((point["easting"] - grid.west_e) // CELL_SIZE_M)
        row = int((grid.north_n - point["northing"]) // CELL_SIZE_M)
        if 0 <= column < grid.columns and 0 <= row < grid.rows:
            squares[row * grid.columns + column].append(point)
    return squares


def conflicts(
    *, leaf_type: str | None, forest_share: float | None, copernicus_leaf_type: str | None,
    low_reliability_below: float,
) -> bool:
    """Return True when the survey point and the satellite map clearly disagree.

    Missing values and the satellite value mixed never count as a disagreement.
    """
    if copernicus_leaf_type == "no forest" and leaf_type is not None:
        return True
    if leaf_type == "broadleaf" and copernicus_leaf_type == "conifer":
        return True
    if leaf_type == "conifer" and copernicus_leaf_type == "broadleaf":
        return True
    return leaf_type is None and forest_share is not None and forest_share >= low_reliability_below


def summarise_square(
    *, points: list[dict[str, Any]], centre: tuple[float, float], forest: dict[str, Any],
    low_reliability_below: float,
) -> dict[str, Any]:
    """Return the most common forest type of the points in one square, with reliability.

    Ties go to the type of the point nearest the square centre.
    """
    row: dict[str, Any] = {
        "regional_forest_type": None,
        "regional_forest_points": len(points),
        "regional_forest_type_source": None,
        "regional_forest_type_reliability": None,
    }
    if not points:
        return row
    counts = Counter(point["name"] for point in points)
    top_count = max(counts.values())
    chosen = min(
        (point for point in points if counts[point["name"]] == top_count),
        key=lambda point: np.hypot(point["easting"] - centre[0], point["northing"] - centre[1]),
    )
    if conflicts(
        leaf_type=chosen["leaf_type"],
        forest_share=forest.get("forest_share"),
        copernicus_leaf_type=forest.get("leaf_type"),
        low_reliability_below=low_reliability_below,
    ):
        reliability = "low"
    elif len(points) >= 2 and len(counts) == 1:
        reliability = "high"
    else:
        reliability = "medium"
    row["regional_forest_type"] = chosen["name"]
    row["regional_forest_type_source"] = LAYER_ID
    row["regional_forest_type_reliability"] = reliability
    return row
