"""Made-up demo scores and the grid lookup behind the demo API.

Nothing here describes real mushrooms or real weather.
"""

import gzip
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

NOTICE = "Made-up demo data. These scores do not describe real mushrooms or real weather."
TIMEZONE = ZoneInfo("Europe/Rome")
MAX_DAYS_AHEAD = 7
AVAILABLE_DAYS = 14
MAX_SQUARES_PER_REQUEST = 4000
MIN_ZOOM = 11
SOURCES = ["Made-up demo weather", "Made-up demo habitat"]
SPECIES = [
    {
        "id": "porcini",
        "name": "Porcini",
        "scientific_names": [
            "Boletus edulis",
            "Boletus aereus",
            "Boletus reticulatus",
            "Boletus pinophilus",
        ],
    },
    {
        "id": "ovolo",
        "name": "Ovolo",
        "scientific_names": ["Amanita caesarea"],
    },
]
SPECIES_IDS = [item["id"] for item in SPECIES]
GRID_PATH = Path(__file__).resolve().parent / "demo_grid.json.gz"


@dataclass(frozen=True)
class Square:
    """One 500 m square with its ring and bounds in lon/lat."""

    cell_id: str
    x: int
    y: int
    ring: list[list[float]]
    west: float
    south: float
    east: float
    north: float


def load_grid(path: Path = GRID_PATH) -> tuple[dict[str, float], list[Square]]:
    """Read the committed grid file into squares with precomputed bounds."""
    data = json.loads(gzip.decompress(path.read_bytes()))
    squares = []
    for row in data["cells"]:
        cell_id = row[0]
        points = [[row[i], row[i + 1]] for i in range(1, 9, 2)]
        lons = [point[0] for point in points]
        lats = [point[1] for point in points]
        easting, northing = cell_id.split("_")[1:]
        squares.append(
            Square(
                cell_id=cell_id,
                x=int(easting[1:]),
                y=int(northing[1:]),
                ring=points + [points[0]],
                west=min(lons),
                south=min(lats),
                east=max(lons),
                north=max(lats),
            )
        )
    return data["box"], squares


def today_in_rome() -> date:
    """Return today's date in Europe/Rome."""
    return datetime.now(tz=TIMEZONE).date()


def assessment_dates(today: date) -> list[date]:
    """List the 14 days ending today, newest first."""
    return [today - timedelta(days=offset) for offset in range(AVAILABLE_DAYS)]


def find_squares(
    squares: list[Square], west: float, south: float, east: float, north: float
) -> list[Square]:
    """Return the squares whose bounds overlap the box."""
    return [
        square
        for square in squares
        if square.east >= west
        and square.west <= east
        and square.north >= south
        and square.south <= north
    ]


def _phases(species: str, target_date: date) -> list[float]:
    """Return six stable phases from a hash of the species and date."""
    digest = hashlib.sha256(f"{species}|{target_date.isoformat()}".encode()).digest()
    return [digest[i] / 255 * 2 * math.pi for i in range(6)]


def score_for(square: Square, species: str, target_date: date) -> int:
    """Return a made-up score from 0 to 100 that varies smoothly over space."""
    p = _phases(species=species, target_date=target_date)
    x = square.x / 1000
    y = square.y / 1000
    wave = (
        math.sin(x * 0.55 + p[0])
        + math.sin(y * 0.70 + p[1])
        + math.sin((x + y) * 0.38 + p[2])
        + math.sin((x - y) * 0.90 + p[3])
        + 0.5 * math.sin(x * 1.7 + y * 1.3 + p[4])
    )
    value = (wave / 4.0 + 1) / 2
    return max(0, min(100, round(value * 100)))


def reliability_for(days_ahead: int) -> str:
    """Return high, medium or low depending on the days ahead."""
    if days_ahead <= 2:
        return "high"
    if days_ahead <= 5:
        return "medium"
    return "low"


def build_feature(
    square: Square, species: str, assessment: date, target: date
) -> dict:
    """Build the GeoJSON feature for one square."""
    days_ahead = (target - assessment).days
    return {
        "type": "Feature",
        "id": square.cell_id,
        "geometry": {"type": "Polygon", "coordinates": [square.ring]},
        "properties": {
            "cell_id": square.cell_id,
            "species": species,
            "assessment_date": assessment.isoformat(),
            "target_date": target.isoformat(),
            "days_ahead": days_ahead,
            "score_type": "conditions_today" if days_ahead == 0 else "forecast",
            "score": score_for(square=square, species=species, target_date=target),
            "reliability": reliability_for(days_ahead=days_ahead),
            "sources": SOURCES,
            "demo_data": True,
        },
    }
