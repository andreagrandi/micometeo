"""Compare three tree sources within the P2 pilot area.

Read small samples in memory and print measurements without database access.
"""

from __future__ import annotations

import argparse
import io
import json
import time
import tomllib
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.windows import from_bounds

from micometeo.habitat.grid import build_grid
from micometeo.habitat.inventory import read_points


SPECIES = {
    "beech": ("Fagus-sylvatica", "fagus.sylvatica", 6956944, "beech woods"),
    "chestnut": ("Castanea-sativa", "castanea.sativa", 6951628, "chestnut woods"),
    "fir": ("Abies-alba", "abies.alba", 6953790, "silver fir woods"),
}
MAX_ARCHIVE_BYTES = 30_000_000
MAX_ARCHIVE_MEMBER_BYTES = 60_000_000
MAX_SAMPLE_PIXELS = 250_000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("JRC", "Bonannella"))
    parser.add_argument("--species", choices=tuple(SPECIES))
    options = parser.parse_args()
    with Path("experiments/p2_habitat/config.toml").open("rb") as handle:
        config = tomllib.load(handle)
    grid = build_grid(**config["settings"]["sample_box"])
    bounds = (grid.west_e, grid.south_n, grid.east_e, grid.north_n)
    started = time.monotonic()
    inventory = Path("data/raw/p2_habitat/toscana_inventario_forestale/ift_1c_polygon.dbf")
    points = [
        point for point in read_points(path=inventory, grid=grid)
        if grid.west_e <= point["easting"] < grid.east_e
        and grid.south_n <= point["northing"] < grid.north_n
    ]
    print(json.dumps({
        "inventory_points": len(points), "bounds": bounds,
        "inventory_categories": dict(Counter(point["name"] for point in points)),
        "inventory_read_seconds": round(time.monotonic() - started, 3),
        "inventory_dbf_bytes": inventory.stat().st_size,
    }), flush=True)
    reference = {value[3]: key for key, value in SPECIES.items()}
    for provider in ([options.provider] if options.provider else ("JRC", "Bonannella")):
        predictions = {}
        for species, (jrc_name, bon_name, record, category) in SPECIES.items():
            if options.species and species != options.species:
                continue
            started = time.monotonic()
            archive_bytes = None
            memory = None
            try:
                if provider == "JRC":
                    url = f"https://ies-ows.jrc.ec.europa.eu/efdac/download/Atlas/{jrc_name}_rpp.zip"
                    with urllib.request.urlopen(url=url, timeout=20) as response:
                        data = response.read(MAX_ARCHIVE_BYTES + 1)
                    if len(data) > MAX_ARCHIVE_BYTES:
                        raise ValueError("The archive exceeds the 30 MB test limit.")
                    archive_bytes = len(data)
                    with zipfile.ZipFile(file=io.BytesIO(initial_bytes=data)) as archive:
                        member = next(info for info in archive.infolist() if info.filename.endswith(".tif"))
                        if member.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                            raise ValueError("The raster exceeds the 60 MB test limit.")
                        memory = MemoryFile(file_or_bytes=archive.read(name=member.filename))
                    dataset = memory.open()
                else:
                    filename = f"veg_{bon_name}_anv.eml_p_30m_0..0cm_2018..2020_eumap_epsg3035_v0.3.tif"
                    url = f"https://zenodo.org/records/{record}/files/{filename}"
                    dataset = rasterio.open(fp=url)
                with dataset:
                    if dataset.crs.to_epsg() != 3035:
                        raise ValueError("The source needs a different coordinate conversion.")
                    window = from_bounds(*bounds, transform=dataset.transform)
                    left, top = int(np.floor(window.col_off)), int(np.floor(window.row_off))
                    right = int(np.ceil(window.col_off + window.width))
                    bottom = int(np.ceil(window.row_off + window.height))
                    if (right - left) * (bottom - top) > MAX_SAMPLE_PIXELS:
                        raise ValueError("The window exceeds the 250,000 pixel test limit.")
                    window = rasterio.windows.Window(left, top, right - left, bottom - top)
                    values = dataset.read(indexes=1, window=window, masked=True)
                    elapsed = time.monotonic() - started
                    repeated_at = time.monotonic()
                    repeated = dataset.read(indexes=1, window=window, masked=True)
                    repeat_seconds = time.monotonic() - repeated_at
                    transform = dataset.window_transform(window=window)
                    rows, cols = rasterio.transform.rowcol(
                        transform=transform, xs=[point["easting"] for point in points],
                        ys=[point["northing"] for point in points],
                    )
                    samples = values[rows, cols]
                    predictions[species] = samples
                    own = samples[[point["name"] == category for point in points]]
                    print(json.dumps({
                        "provider": provider, "species": species, "url": url,
                        "resolution_m": dataset.res, "nodata": dataset.nodata,
                        "dtype": dataset.dtypes[0], "scales": dataset.scales,
                        "archive_download_bytes": archive_bytes,
                        "window_pixels": int(values.size), "valid_pixels": int(values.count()),
                        "sample_min": float(values.min()), "sample_max": float(values.max()),
                        "cold_read_seconds": round(elapsed, 3),
                        "repeat_read_seconds": round(repeat_seconds, 6),
                        "repeat_identical": bool(np.array_equal(values.data, repeated.data)
                            and np.array_equal(np.ma.getmaskarray(values), np.ma.getmaskarray(repeated))),
                        "own_inventory_points": int(own.size),
                        "own_points_with_value": int(own.count()),
                        "own_mean_raw": float(own.mean()) if own.count() else None,
                    }), flush=True)
            except Exception as exc:
                print(json.dumps({
                    "provider": provider, "species": species, "error": str(exc),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }), flush=True)
            finally:
                if memory is not None:
                    memory.close()
        outcomes = Counter()
        confusion = Counter()
        if len(predictions) == len(SPECIES):
            for index, point in enumerate(points):
                expected = reference.get(point["name"])
                if expected is None:
                    continue
                if any(np.ma.is_masked(value[index]) for value in predictions.values()):
                    outcomes["missing_competitor"] += 1
                    continue
                scores = {name: float(value[index]) for name, value in predictions.items()}
                winners = [name for name, value in scores.items() if value == max(scores.values())]
                if len(winners) != 1:
                    outcomes["tie"] += 1
                    continue
                outcomes["agree" if winners[0] == expected else "disagree"] += 1
                confusion[f"{expected}/{winners[0]}"] += 1
        print(json.dumps({
            "provider": provider, "comparison": dict(outcomes), "confusion": dict(confusion),
            "comparison_status": "complete" if len(predictions) == len(SPECIES) else "incomplete",
        }), flush=True)


if __name__ == "__main__":
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        GDAL_HTTP_TIMEOUT="20", GDAL_HTTP_CONNECTTIMEOUT="10", GDAL_HTTP_MAX_RETRY="0",
    ):
        main()
