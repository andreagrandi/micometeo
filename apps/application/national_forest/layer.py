"""Write the deterministic two kilometre forest overview layer."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models import ExpressionWrapper, F, FloatField, Value
from django.db.models.functions import Floor
from pyproj import Transformer

LAYER_SIZE_M = 2_000
CELL_SIZE_M = 500
LAYER_CRS = "EPSG:3035"
OUTPUT_CRS = "EPSG:4326"
_TO_WGS84 = Transformer.from_crs(LAYER_CRS, OUTPUT_CRS, always_xy=True)
REPOSITORY_ROOT = Path(settings.BASE_DIR).parent.parent


def stored_layer_path(*, path: Path) -> str:
    """Return the repository-relative path of a layer file, or the absolute path outside it."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def resolve_layer_path(*, value: str) -> Path:
    """Turn a stored layer path into a real path, using the repository root for relative values."""
    path = Path(value)
    return path if path.is_absolute() else REPOSITORY_ROOT / path


@dataclass(frozen=True)
class LayerArtifact:
    """Describe one validated forest layer file."""

    path: Path
    sha256: str
    raw_bytes: int
    gzip_bytes: int
    feature_count: int


def _row_value(row: Any, name: str, alternate: str | None = None) -> Any:
    if isinstance(row, dict):
        value = row.get(name)
        return row.get(alternate) if value is None and alternate else value
    value = getattr(row, name, None)
    return getattr(row, alternate, None) if value is None and alternate else value


def _row_corner(row: Any) -> tuple[int, int]:
    west = _row_value(row, "corner_e")
    south = _row_value(row, "corner_n")
    if west is not None and south is not None:
        return int(west), int(south)
    membership = _row_value(row, "grid_build_cell")
    cell = getattr(membership, "cell", None)
    if cell is None:
        raise ValueError("A forest layer row needs grid cell corners.")
    return int(cell.corner_e), int(cell.corner_n)


def _row_counts(row: Any) -> tuple[int, int]:
    forest = _row_value(row, "forest_pixel_count", "forest_pixels")
    valid = _row_value(row, "valid_pixel_count", "valid_pixels")
    if forest is None or valid is None:
        forest_share = _row_value(row, "forest_share")
        valid = _row_value(row, "valid_pixel_count", "valid_pixels")
        if forest_share is None or valid is None:
            raise ValueError("A forest layer row needs forest and valid pixel counts.")
        forest = float(forest_share) * int(valid)
    return int(forest), int(valid)


def _row_is_available(row: Any) -> bool:
    """Return whether a forest cell has a usable public classification."""
    missing = object()
    if isinstance(row, dict):
        value = row.get("is_forest", missing)
    else:
        value = getattr(row, "is_forest", missing)
    return value is missing or value is not None


def _row_sort_key(row: Any) -> tuple[int, int, int, int]:
    """Order coarse layer groups before their source cells."""
    corner_e, corner_n = _row_corner(row)
    group_e, group_n = _group_key(corner_e=corner_e, corner_n=corner_n)
    return (-group_n, group_e, -corner_n, corner_e)


def _ordered_rows(rows: Iterable[Any]) -> Iterator[Any]:
    """Order small in-memory fixtures while leaving database streams bounded."""
    if isinstance(rows, Sequence):
        yield from sorted(rows, key=_row_sort_key)
        return
    yield from rows


def _group_key(*, corner_e: int, corner_n: int) -> tuple[int, int]:
    return (
        math.floor(corner_e / LAYER_SIZE_M) * LAYER_SIZE_M,
        math.floor(corner_n / LAYER_SIZE_M) * LAYER_SIZE_M,
    )


def _feature(*, west: int, south: int, forest_pixels: int, valid_pixels: int) -> dict[str, Any]:
    """Return one WGS84 GeoJSON feature with its weighted forest fraction."""
    if valid_pixels <= 0 or forest_pixels <= 0:
        raise ValueError("A forest layer feature needs positive forest and valid counts.")
    points = []
    for easting, northing in (
        (west, south),
        (west + LAYER_SIZE_M, south),
        (west + LAYER_SIZE_M, south + LAYER_SIZE_M),
        (west, south + LAYER_SIZE_M),
        (west, south),
    ):
        longitude, latitude = _TO_WGS84.transform(easting, northing)
        points.append([longitude, latitude])
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [points]},
        "properties": {"forest_share": forest_pixels / valid_pixels},
    }


def _stream_json(target: Any, *, rows: Iterable[Any]) -> tuple[int, int]:
    """Write features to a gzip stream and return raw bytes and feature count."""
    raw_bytes = 0
    feature_count = 0

    def write(value: bytes) -> None:
        nonlocal raw_bytes
        target.write(value)
        raw_bytes += len(value)

    write(b'{"type":"FeatureCollection","features":[')
    current_key: tuple[int, int] | None = None
    forest_pixels = 0
    valid_pixels = 0
    first = True
    for row in _ordered_rows(rows):
        if not _row_is_available(row):
            continue
        corner_e, corner_n = _row_corner(row)
        key = _group_key(corner_e=corner_e, corner_n=corner_n)
        row_forest, row_valid = _row_counts(row)
        if current_key is None:
            current_key = key
        if key != current_key:
            if forest_pixels > 0 and valid_pixels > 0:
                if not first:
                    write(b",")
                encoded = json.dumps(
                    _feature(
                        west=current_key[0],
                        south=current_key[1],
                        forest_pixels=forest_pixels,
                        valid_pixels=valid_pixels,
                    ),
                    allow_nan=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                write(encoded)
                feature_count += 1
                first = False
            current_key = key
            forest_pixels = 0
            valid_pixels = 0
        forest_pixels += row_forest
        valid_pixels += row_valid

    if current_key is not None and forest_pixels > 0 and valid_pixels > 0:
        if not first:
            write(b",")
        encoded = json.dumps(
            _feature(
                west=current_key[0],
                south=current_key[1],
                forest_pixels=forest_pixels,
                valid_pixels=valid_pixels,
            ),
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        write(encoded)
        feature_count += 1
    write(b"]}")
    return raw_bytes, feature_count


def write_forest_layer(*, rows: Iterable[Any], output_path: Path) -> LayerArtifact:
    """Write a deterministic gzip GeoJSON layer from a bounded row stream."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            with gzip.GzipFile(
                fileobj=handle,
                mode="wb",
                filename="",
                mtime=0,
                compresslevel=9,
            ) as target:
                raw_bytes, feature_count = _stream_json(target, rows=rows)
        validate_layer(path=temporary_path)
        digest = hashlib.sha256(temporary_path.read_bytes()).hexdigest()
        gzip_bytes = temporary_path.stat().st_size
        os.replace(temporary_path, output_path)
        temporary_path = None
        return LayerArtifact(
            path=output_path,
            sha256=digest,
            raw_bytes=raw_bytes,
            gzip_bytes=gzip_bytes,
            feature_count=feature_count,
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def validate_layer(*, path: Path) -> dict[str, Any]:
    """Validate the final gzip GeoJSON artifact before build completion."""
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            document = json.load(handle)
    except (OSError, EOFError, json.JSONDecodeError) as exc:
        raise ValueError(f"Forest layer is not valid gzip GeoJSON: {exc}") from exc
    if document.get("type") != "FeatureCollection" or not isinstance(document.get("features"), list):
        raise ValueError("Forest layer must be a GeoJSON FeatureCollection.")
    for feature in document["features"]:
        if feature.get("type") != "Feature":
            raise ValueError("Forest layer contains a non-feature object.")
        properties = feature.get("properties")
        if not isinstance(properties, dict) or set(properties) != {"forest_share"}:
            raise ValueError("Forest layer features may contain only forest_share.")
        share = properties["forest_share"]
        if not isinstance(share, (float, int)) or not 0 <= share <= 1:
            raise ValueError("Forest layer forest_share must be between zero and one.")
    return {
        "feature_count": len(document["features"]),
        "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "gzip_bytes": Path(path).stat().st_size,
    }


def rows_from_cells(*, cells: Any) -> Iterator[dict[str, Any]]:
    """Stream ordered rows from a ForestCell queryset for the layer writer."""
    corner_e = "grid_build_cell__cell__corner_e"
    corner_n = "grid_build_cell__cell__corner_n"
    group_e = ExpressionWrapper(
        F(corner_e) / Value(float(LAYER_SIZE_M)),
        output_field=FloatField(),
    )
    group_n = ExpressionWrapper(
        F(corner_n) / Value(float(LAYER_SIZE_M)),
        output_field=FloatField(),
    )
    queryset = (
        cells.filter(is_forest__isnull=False)
        .annotate(_layer_group_e=Floor(group_e), _layer_group_n=Floor(group_n))
        .order_by("-_layer_group_n", "_layer_group_e", f"-{corner_n}", corner_e)
        .values_list(
            corner_e,
            corner_n,
            "forest_pixel_count",
            "valid_pixel_count",
        )
    )
    for corner_e_value, corner_n_value, forest_pixels, valid_pixels in queryset.iterator(chunk_size=2_000):
        yield {
            "corner_e": corner_e_value,
            "corner_n": corner_n_value,
            "forest_pixel_count": forest_pixels,
            "valid_pixel_count": valid_pixels,
        }
