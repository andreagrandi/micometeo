"""Build the sample map layers for the agent mockup.

Writes assets/italy_forest.png and assets/sample_squares.js. All values are illustrative.
"""

import gzip
import json
import math
from pathlib import Path

import matplotlib
import numpy as np
from PIL import Image
from pyproj import Transformer
import shapely
from shapely import STRtree, points
from shapely.geometry import shape

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402

SOURCE = Path("data/processed/mvp_forest/italy-forest-copernicus-2018-v1/forest_layer_2000m.geojson.gz")
ASSETS = Path("docs/design/agent/assets")
DATES = [f"2026-10-{day}" for day in range(12, 20)]
CENTRE_LAT, CENTRE_LON = 44.1318, 10.6625
ROWS, COLS = 36, 40
IMAGE_HEIGHT = 1400
FOREST_RGB = (0x3F / 255, 0x7D / 255, 0x4E / 255)

to_mercator = Transformer.from_crs(4326, 3857, always_xy=True).transform
to_degrees = Transformer.from_crs(3857, 4326, always_xy=True).transform


def to_array(coords: np.ndarray) -> np.ndarray:
    """Convert lon/lat coordinates to Web Mercator.

    Used with shapely.transform.
    """
    return np.column_stack(to_mercator(coords[:, 0], coords[:, 1]))


def load_polygons() -> tuple[list, np.ndarray]:
    """Read the 2 km forest polygons and their forest share.

    Returns the polygons in lon/lat and the shares as fractions from 0 to 1.
    """
    with gzip.open(SOURCE, "rt") as handle:
        features = json.load(handle)["features"]
    polygons = [shape(feature["geometry"]) for feature in features]
    shares = np.array([feature["properties"]["forest_share"] for feature in features])
    return polygons, shares


def build_image(polygons: list, shares: np.ndarray) -> tuple[list[list[float]], int, int]:
    """Draw the national forest PNG in Web Mercator and save it.

    Returns the lat/lon bounds, the width and the height.
    """
    projected = [shapely.transform(polygon, to_array) for polygon in polygons]
    x_min, y_min, x_max, y_max = (
        min(p.bounds[0] for p in projected),
        min(p.bounds[1] for p in projected),
        max(p.bounds[2] for p in projected),
        max(p.bounds[3] for p in projected),
    )
    width = round(IMAGE_HEIGHT * (x_max - x_min) / (y_max - y_min))
    rings, colours = [], []
    for polygon, share in zip(projected, shares):
        # The app shows no estimate under 10% forest, so the national view leaves it blank too.
        if share < 0.10:
            continue
        for part in getattr(polygon, "geoms", [polygon]):
            rings.append(np.asarray(part.exterior.coords))
            colours.append((*FOREST_RGB, 0.15 + 0.6 * share))

    figure = plt.figure(figsize=(width / 100, IMAGE_HEIGHT / 100), dpi=100)
    axes = figure.add_axes((0, 0, 1, 1))
    axes.set_axis_off()
    axes.set_xlim(x_min, x_max)
    axes.set_ylim(y_min, y_max)
    axes.add_collection(PolyCollection(rings, facecolors=colours, edgecolors="none", antialiaseds=False))
    figure.canvas.draw()
    rgba = np.asarray(figure.canvas.buffer_rgba())
    # A 32 colour palette keeps the file small.
    Image.fromarray(rgba).quantize(colors=32, method=Image.Quantize.FASTOCTREE).save(ASSETS / "italy_forest.png")
    plt.close(figure)

    west, south = to_degrees(x_min, y_min)
    east, north = to_degrees(x_max, y_max)
    return [[round(south, 5), round(west, 5)], [round(north, 5), round(east, 5)]], width, IMAGE_HEIGHT


def build_squares(polygons: list, shares: np.ndarray) -> list[dict]:
    """Build the 500 m squares around Abetone with illustrative estimates.

    Squares with little forest or missing data get no estimates.
    """
    rng = np.random.default_rng(seed=53)
    lat_step = 0.0045
    lon_step = lat_step / math.cos(math.radians(CENTRE_LAT))
    south = CENTRE_LAT - 18.5 * lat_step
    west = CENTRE_LON - 20.5 * lon_step
    tree = STRtree(polygons)
    phase = rng.uniform(0, 2 * math.pi, size=3)
    day_curve = 0.8 + 0.3 * np.sin(np.pi * (np.arange(len(DATES)) + 0.5) / len(DATES))
    missing_rows, missing_cols = range(26, 29), range(8, 11)

    squares = []
    for row in range(ROWS):
        for col in range(COLS):
            sq_south, sq_west = south + row * lat_step, west + col * lon_step
            square_id = "abetone-sample" if (row, col) == (18, 20) else f"r{row}c{col}"
            centre = points(sq_west + lon_step / 2, sq_south + lat_step / 2)
            hits = tree.query(centre, predicate="within")
            share = 100 * shares[hits[0]] if len(hits) else 0
            share = int(np.clip(round(share + rng.uniform(-12, 12)), 0, 100))
            is_missing = row in missing_rows and col in missing_cols
            if is_missing:
                share = max(share, 45)
            estimates, reason = None, None
            if square_id == "abetone-sample":
                share, estimates = 68, [42, 45, 47, 48, 46, 43, 40, 38]
            elif is_missing:
                reason = "missing_data"
            elif share < 10:
                reason = "less_forest"
            else:
                wave = (
                    np.sin(col / 5 + phase[0]) + np.sin(row / 6 + phase[1]) + np.sin((row + col) / 9 + phase[2])
                ) / 3
                base = 0.55 * (45 + 30 * wave) + 0.45 * share
                estimates = [int(v) for v in np.clip(np.round(base * day_curve), 5, 85)]
            squares.append(
                {
                    "id": square_id,
                    "bounds": [
                        [round(sq_south, 5), round(sq_west, 5)],
                        [round(sq_south + lat_step, 5), round(sq_west + lon_step, 5)],
                    ],
                    "forest_share": share,
                    "estimates": estimates,
                    "no_estimate_reason": reason,
                }
            )
    return squares


def main() -> None:
    """Build both files and print a short summary.

    Run from the repository root.
    """
    ASSETS.mkdir(parents=True, exist_ok=True)
    polygons, shares = load_polygons()
    bounds, width, height = build_image(polygons, shares)
    squares = build_squares(polygons, shares)
    sample = {
        "dates": DATES,
        "selected_square_id": "abetone-sample",
        "national_forest": {"url": "assets/italy_forest.png", "bounds": bounds},
        "squares": squares,
    }
    text = json.dumps(sample, separators=(",", ":"))
    (ASSETS / "sample_squares.js").write_text(f"window.SPORAMETEO_SAMPLE = {text};\n")

    png_bytes = (ASSETS / "italy_forest.png").stat().st_size
    print(f"italy_forest.png: {width} x {height} px, {png_bytes} bytes, bounds {bounds}")
    print(f"sample_squares.js: {(ASSETS / 'sample_squares.js').stat().st_size} bytes")
    for reason in (None, "less_forest", "missing_data"):
        count = sum(1 for s in squares if s["no_estimate_reason"] == reason)
        print(f"squares with reason {reason}: {count}")


if __name__ == "__main__":
    main()
