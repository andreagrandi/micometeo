"""Rock type from the Tuscany 1:10,000 geology map, asked one point at a time.

The map service gives no shapes, so each square is sampled at the centres of its four quarters.
"""

import json
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from micometeo.habitat.grid import QUARTER_OFFSETS_M, SampleGrid, to_degrees

LAYER_ID = "toscana_geologia_10k"
SERVICE_URL = "https://www502.regione.toscana.it/geoscopio_qg/cgi-bin/qgis_mapserv"
LICENCE = "CC BY, version not stated in the metadata record"
CACHE_NAME = "toscana_geologia_10k_points.json"
CODE_FIELD = "Sigla unita' geologica"
NAME_FIELD = "Denominazione unita' geologica"
DESCRIPTION_FIELD = "Descrizione unita' geologica"
# Half the side of the tiny box around each point, in degrees, about 10 m.
HALF_BOX_DEGREES = 0.0001


def point_key(*, latitude: float, longitude: float) -> str:
    return f"{latitude:.6f},{longitude:.6f}"


def build_query(*, latitude: float, longitude: float, layer: str) -> dict[str, Any]:
    """Return the map service parameters that ask for the unit under one point."""
    return {
        "map": "dbgeologico_rt.qgs",
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetFeatureInfo",
        "LAYERS": layer,
        "QUERY_LAYERS": layer,
        "CRS": "EPSG:4326",
        "BBOX": ",".join(
            str(round(value, 7))
            for value in (
                latitude - HALF_BOX_DEGREES,
                longitude - HALF_BOX_DEGREES,
                latitude + HALF_BOX_DEGREES,
                longitude + HALF_BOX_DEGREES,
            )
        ),
        "WIDTH": 101,
        "HEIGHT": 101,
        "I": 50,
        "J": 50,
        "INFO_FORMAT": "application/json",
        "FEATURE_COUNT": 1,
    }


def query_point(
    *, latitude: float, longitude: float, layer: str, attempts: int = 3
) -> dict[str, str] | None:
    """Return code, name and description of the unit under a point, or None if there is none."""
    url = SERVICE_URL + "?" + urllib.parse.urlencode(
        build_query(latitude=latitude, longitude=longitude, layer=layer)
    )
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                answer = json.loads(response.read())
            break
        except (OSError, ValueError):
            if attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))
    features = answer.get("features") or []
    if not features:
        return None
    properties = features[0]["properties"]
    return {
        "code": properties.get(CODE_FIELD) or "",
        "name": properties.get(NAME_FIELD) or "",
        "description": properties.get(DESCRIPTION_FIELD) or "",
    }


def quarter_points(*, grid: SampleGrid) -> list[list[tuple[float, float]]]:
    """Return latitude and longitude of the four quarter centres of every square."""
    return [
        [
            to_degrees(easting=corner_e + offset_e, northing=corner_n + offset_n)
            for offset_e, offset_n in QUARTER_OFFSETS_M
        ]
        for corner_e, corner_n in grid.corners()
    ]


def fetch_points(
    *, points: list[tuple[float, float]], layer: str, cache_path: Path, pause_seconds: float
) -> dict[str, dict[str, str] | None]:
    """Return the unit under every point, asking the service only for points not cached."""
    answers: dict[str, dict[str, str] | None] = {}
    if cache_path.exists():
        answers = json.loads(cache_path.read_text(encoding="utf-8"))
    missing = [
        (latitude, longitude)
        for latitude, longitude in points
        if point_key(latitude=latitude, longitude=longitude) not in answers
    ]
    for number, (latitude, longitude) in enumerate(missing, start=1):
        key = point_key(latitude=latitude, longitude=longitude)
        answers[key] = query_point(latitude=latitude, longitude=longitude, layer=layer)
        if number % 100 == 0 or number == len(missing):
            cache_path.write_text(json.dumps(answers, indent=1), encoding="utf-8")
        time.sleep(pause_seconds)
    return answers


def summarise_square(*, answers: list[dict[str, str] | None]) -> dict[str, Any]:
    """Return the most common unit of the four quarters and how many agree with it.

    Ties go to the unit seen first in the order south-west, south-east, north-west, north-east.
    """
    units = [answer for answer in answers if answer and answer["code"]]
    if not units:
        return {
            "rock_unit_code": None,
            "rock_unit_name": None,
            "rock_description": None,
            "rock_unit_code_source": None,
            "rock_unit_code_reliability": None,
        }
    counts = Counter(unit["code"] for unit in units)
    top_count = max(counts.values())
    chosen = next(unit for unit in units if counts[unit["code"]] == top_count)
    reliability = {4: "high", 3: "medium"}.get(top_count, "low")
    return {
        "rock_unit_code": chosen["code"],
        "rock_unit_name": chosen["name"],
        "rock_description": chosen["description"],
        "rock_unit_code_source": LAYER_ID,
        "rock_unit_code_reliability": reliability,
    }


def code_lattice(
    *, grid: SampleGrid, answers: dict[str, dict[str, str] | None]
) -> list[list[str | None]]:
    """Return unit codes on the 250 m lattice of quarter centres, rows from the north."""
    lattice: list[list[str | None]] = [
        [None] * (grid.columns * 2) for _ in range(grid.rows * 2)
    ]
    for index, points in enumerate(quarter_points(grid=grid)):
        square_row, square_column = divmod(index, grid.columns)
        for (offset_e, offset_n), (latitude, longitude) in zip(QUARTER_OFFSETS_M, points):
            answer = answers.get(point_key(latitude=latitude, longitude=longitude))
            row = square_row * 2 + (0 if offset_n > 250 else 1)
            column = square_column * 2 + (0 if offset_e < 250 else 1)
            lattice[row][column] = answer["code"] if answer and answer["code"] else None
    return lattice
