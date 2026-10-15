"""Forest share and leaf type from the Copernicus forest type map of 2018.

The map only says broadleaf or conifer. It never names a tree species.
"""

import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

from sporameteo.habitat.grid import SampleGrid, square_blocks, write_download_note
from sporameteo.habitat.terrain import coverage_reliability

LAYER_ID = "copernicus_forest_type_2018"
SERVICE_URL = (
    "https://image.discomap.eea.europa.eu/arcgis/rest/services/"
    "GioLandPublic/HRL_ForestType_2018/ImageServer/exportImage"
)
LICENCE = (
    "Copernicus Land Monitoring Service data, free and open access under EU Regulation "
    "1159/2013. Credit: © European Union, Copernicus Land Monitoring Service 2018, "
    "European Environment Agency"
)
RAW_NAME = "copernicus_forest_type_2018.tif"
PIXEL_M = 10
BROADLEAF = 1
CONIFER = 2
# Pixel values above the conifer value mean unclassifiable (254) or outside the area (255).
LEAF_TYPES = ["no forest", "broadleaf", "conifer", "mixed"]

# Copernicus HRL Forest Type 2018 codes used by the national build.  Codes
# 254 and 255 are kept as separate counts before either one is treated as
# missing for the fraction calculations.
NATIONAL_VALID_NONFOREST = 0
NATIONAL_BROADLEAF = BROADLEAF
NATIONAL_CONIFER = CONIFER
NATIONAL_UNCLASSIFIABLE = 254
NATIONAL_OUTSIDE = 255
NATIONAL_CODES = {
    NATIONAL_VALID_NONFOREST,
    NATIONAL_BROADLEAF,
    NATIONAL_CONIFER,
    NATIONAL_UNCLASSIFIABLE,
    NATIONAL_OUTSIDE,
}
NATIONAL_NO_FOREST_BELOW = 0.1
NATIONAL_BROADLEAF_FROM = 0.75
NATIONAL_HIGH_COVERAGE = 0.95
NATIONAL_LOW_COVERAGE = 0.5


def build_query(*, grid: SampleGrid) -> dict[str, Any]:
    """Return the image service parameters that ask for the grid area in 10 m pixels."""
    return {
        "bbox": f"{grid.west_e},{grid.south_n},{grid.east_e},{grid.north_n}",
        "bboxSR": 3035,
        "imageSR": 3035,
        "size": f"{(grid.east_e - grid.west_e) // PIXEL_M},{(grid.north_n - grid.south_n) // PIXEL_M}",
        "format": "tiff",
        "pixelType": "U8",
        "interpolation": "RSP_NearestNeighbor",
        "f": "image",
    }


def download_forest_type(*, grid: SampleGrid, raw_dir: Path) -> Path:
    """Save the forest type map of the grid area, unless it is already saved."""
    path = raw_dir / RAW_NAME
    if path.exists():
        return path
    query = build_query(grid=grid)
    with urllib.request.urlopen(SERVICE_URL + "?" + urllib.parse.urlencode(query), timeout=300) as response:
        content = response.read()
    if content[:2] not in (b"II", b"MM"):
        raise ValueError(f"The image service did not return a GeoTIFF: {content[:200]!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    write_download_note(path=path, details={"url": SERVICE_URL, "query": query})
    return path


def mask_unusable(*, pixels: np.ndarray) -> np.ndarray:
    """Turn the values 254 and 255 into NaN, so they count as missing."""
    return np.where(pixels > CONIFER, np.nan, pixels).astype("float32")


def leaf_type(*, forest_share: float, broadleaf_share: float | None, settings: dict[str, Any]) -> str:
    """Return no forest, broadleaf, conifer or mixed from the two shares."""
    if forest_share < settings["no_forest_below"] or broadleaf_share is None:
        return "no forest"
    if broadleaf_share >= settings["broadleaf_from"]:
        return "broadleaf"
    if broadleaf_share <= 1 - settings["broadleaf_from"]:
        return "conifer"
    return "mixed"


def summarise_forest(
    *, pixels: np.ndarray, grid: SampleGrid, settings: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return forest share, broadleaf share and leaf type with reliability for every square.

    The pixels hold 0 for no forest, 1 for broadleaf, 2 for conifer and NaN for missing.
    """
    rows = []
    for block in square_blocks(pixels=pixels, grid=grid):
        valid = block[~np.isnan(block)]
        reliability = coverage_reliability(valid_share=valid.size / block.size)
        row: dict[str, Any] = {
            "forest_share": None,
            "forest_share_source": None,
            "forest_share_reliability": None,
            "broadleaf_share": None,
            "broadleaf_share_source": None,
            "broadleaf_share_reliability": None,
            "leaf_type": None,
            "leaf_type_source": None,
            "leaf_type_reliability": None,
        }
        if reliability is None:
            rows.append(row)
            continue
        broadleaf = int(np.sum(valid == BROADLEAF))
        forest = broadleaf + int(np.sum(valid == CONIFER))
        forest_share = forest / valid.size
        broadleaf_share = broadleaf / forest if forest else None
        row["forest_share"] = round(forest_share, 3)
        row["forest_share_reliability"] = reliability
        if broadleaf_share is not None:
            row["broadleaf_share"] = round(broadleaf_share, 3)
            row["broadleaf_share_reliability"] = (
                "low" if forest_share < settings["no_forest_below"] else reliability
            )
        row["leaf_type"] = leaf_type(
            forest_share=forest_share, broadleaf_share=broadleaf_share, settings=settings
        )
        row["leaf_type_reliability"] = (
            "low"
            if settings["no_forest_below"] <= forest_share < settings["low_reliability_below"]
            else reliability
        )
        for column in ("forest_share", "broadleaf_share", "leaf_type"):
            row[f"{column}_source"] = LAYER_ID if row[column] is not None else None
        rows.append(row)
    return rows


def national_leaf_type(*, forest_share: float, broadleaf_share: float | None) -> str:
    """Classify a national square from unrounded forest fractions."""
    if forest_share < NATIONAL_NO_FOREST_BELOW or broadleaf_share is None:
        return "no forest"
    if broadleaf_share >= NATIONAL_BROADLEAF_FROM:
        return "broadleaf"
    if broadleaf_share <= 1 - NATIONAL_BROADLEAF_FROM:
        return "conifer"
    return "mixed"


def summarise_national_block(*, pixels: np.ndarray) -> dict[str, Any]:
    """Summarise one 500 metre block without rounding national fractions.

    The block contains the five source codes defined above.  Unclassifiable and
    outside pixels remain separate counts and do not count as valid land.
    """
    values = np.asarray(pixels)
    if values.size == 0:
        raise ValueError("A forest block must contain at least one pixel.")
    if not np.all(np.isfinite(values)):
        raise ValueError("A national forest block must contain integer source codes.")
    if not np.all(np.equal(values, values.astype("int64"))):
        raise ValueError("A national forest block must contain integer source codes.")
    integer_values = values.astype("int64", copy=False)
    observed = set(np.unique(integer_values).tolist())
    unsupported = observed - NATIONAL_CODES
    if unsupported:
        raise ValueError(f"Unsupported national forest source code(s): {sorted(unsupported)}.")

    valid_pixels = np.isin(
        integer_values,
        [NATIONAL_VALID_NONFOREST, NATIONAL_BROADLEAF, NATIONAL_CONIFER],
    )
    forest_pixels = np.isin(integer_values, [NATIONAL_BROADLEAF, NATIONAL_CONIFER])
    total_pixels = int(integer_values.size)
    valid_pixel_count = int(valid_pixels.sum())
    forest_pixel_count = int(forest_pixels.sum())
    broadleaf_pixel_count = int((integer_values == NATIONAL_BROADLEAF).sum())
    conifer_pixel_count = int((integer_values == NATIONAL_CONIFER).sum())
    unclassifiable_pixel_count = int((integer_values == NATIONAL_UNCLASSIFIABLE).sum())
    outside_pixel_count = int((integer_values == NATIONAL_OUTSIDE).sum())
    coverage = valid_pixel_count / total_pixels

    if coverage >= NATIONAL_HIGH_COVERAGE:
        coverage_quality = "high"
    elif coverage >= NATIONAL_LOW_COVERAGE:
        coverage_quality = "low"
    else:
        coverage_quality = "unavailable"

    forest_share = (
        forest_pixel_count / valid_pixel_count if valid_pixel_count else None
    )
    broadleaf_share = (
        broadleaf_pixel_count / forest_pixel_count if forest_pixel_count else None
    )
    usable = coverage_quality != "unavailable" and forest_share is not None
    if usable:
        leaf_type = national_leaf_type(
            forest_share=forest_share,
            broadleaf_share=broadleaf_share,
        )
        is_forest = forest_pixel_count * 10 >= valid_pixel_count
    else:
        leaf_type = None
        is_forest = None

    if valid_pixel_count == 0:
        missing_reason = "no_valid_pixels"
    elif coverage_quality == "unavailable":
        missing_reason = "insufficient_valid_coverage"
    elif unclassifiable_pixel_count and outside_pixel_count:
        missing_reason = "unclassifiable_and_outside_pixels"
    elif unclassifiable_pixel_count:
        missing_reason = "unclassifiable_pixels"
    elif outside_pixel_count:
        missing_reason = "outside_pixels"
    else:
        missing_reason = None

    return {
        "total_pixel_count": total_pixels,
        "valid_pixel_count": valid_pixel_count,
        "forest_pixel_count": forest_pixel_count,
        "broadleaf_pixel_count": broadleaf_pixel_count,
        "conifer_pixel_count": conifer_pixel_count,
        "unclassifiable_pixel_count": unclassifiable_pixel_count,
        "outside_pixel_count": outside_pixel_count,
        "valid_coverage": coverage,
        "coverage_quality": coverage_quality,
        "forest_share": forest_share if usable else None,
        "broadleaf_share": broadleaf_share if usable else None,
        "leaf_type": leaf_type,
        "is_forest": is_forest,
        "missing_reason": missing_reason,
    }


# These names keep the block operation easy to find from the application
# service and make the national operation explicit at call sites.
summarise_forest_block = summarise_national_block
summarise_block = summarise_national_block
