"""Create aligned grid cells from transformed regional boundaries."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from micometeo.finds.grid import format_cell_id

from .source import RegionBoundary


@dataclass(frozen=True)
class GridChunkBounds:
    """Represent one aligned rectangular chunk in EPSG:3035 metres."""

    west_e: int
    south_n: int
    east_e: int
    north_n: int


@dataclass(frozen=True)
class GridCellDefinition:
    """Represent one positive-land square before database persistence."""

    cell_id: str
    corner_e: int
    corner_n: int
    geometry: Polygon
    land_geometry: MultiPolygon
    land_share: float
    owner_code: str
    owner_name: str


def aligned_bounds(*, regions: Iterable[RegionBoundary], cell_size_m: int) -> tuple[int, int, int, int]:
    """Return the outward-snapped bounds of all source regions."""
    geometries = [region.geometry for region in regions]
    if not geometries or any(geometry.is_empty for geometry in geometries):
        raise ValueError("At least one non-empty region is required.")
    west = min(geometry.bounds[0] for geometry in geometries)
    south = min(geometry.bounds[1] for geometry in geometries)
    east = max(geometry.bounds[2] for geometry in geometries)
    north = max(geometry.bounds[3] for geometry in geometries)
    return (
        math.floor(west / cell_size_m) * cell_size_m,
        math.floor(south / cell_size_m) * cell_size_m,
        math.ceil(east / cell_size_m) * cell_size_m,
        math.ceil(north / cell_size_m) * cell_size_m,
    )


def iter_chunk_bounds(
    *,
    regions: Iterable[RegionBoundary],
    cell_size_m: int = 500,
    chunk_size_m: int = 25_000,
) -> list[GridChunkBounds]:
    """Return aligned chunks that contain positive source-land area."""
    if cell_size_m <= 0 or chunk_size_m <= 0 or chunk_size_m % cell_size_m:
        raise ValueError("Chunk and cell sizes must be positive, with aligned chunk edges.")
    regions_list = list(regions)
    west, south, east, north = aligned_bounds(regions=regions_list, cell_size_m=cell_size_m)
    tree = STRtree([region.geometry for region in regions_list])
    chunks: list[GridChunkBounds] = []
    for south_n in range(south, north, chunk_size_m):
        for west_e in range(west, east, chunk_size_m):
            bounds = GridChunkBounds(
                west_e=west_e,
                south_n=south_n,
                east_e=min(west_e + chunk_size_m, east),
                north_n=min(south_n + chunk_size_m, north),
            )
            chunk_polygon = _chunk_polygon(bounds=bounds)
            candidate_indexes = tree.query(chunk_polygon, predicate="intersects")
            if any(
                regions_list[int(index)].geometry.intersection(chunk_polygon).area > 0
                for index in candidate_indexes
            ):
                chunks.append(bounds)
    return chunks


def cells_for_chunk(
    *,
    regions: Iterable[RegionBoundary],
    bounds: GridChunkBounds,
    cell_size_m: int = 500,
) -> list[GridCellDefinition]:
    """Return positive-land cells clipped against the source regions."""
    if cell_size_m <= 0 or any(value % cell_size_m for value in (bounds.west_e, bounds.south_n, bounds.east_e, bounds.north_n)):
        raise ValueError("Chunk bounds must align to the cell size.")
    regions_list = _clip_regions_to_chunk(regions=regions, bounds=bounds)
    tree = STRtree([region.geometry for region in regions_list])
    cells: list[GridCellDefinition] = []
    for corner_n in range(bounds.south_n, bounds.north_n, cell_size_m):
        for corner_e in range(bounds.west_e, bounds.east_e, cell_size_m):
            square = box(corner_e, corner_n, corner_e + cell_size_m, corner_n + cell_size_m)
            candidate_indexes = tree.query(square, predicate="intersects")
            intersections: list[tuple[RegionBoundary, float, object]] = []
            for index in candidate_indexes:
                region = regions_list[int(index)]
                clipped = region.geometry.intersection(square)
                if clipped.is_empty or clipped.area <= 0:
                    continue
                intersections.append((region, clipped.area, clipped))
            if not intersections:
                continue
            land = unary_union([clipped for _, _, clipped in intersections])
            if land.is_empty or land.area <= 0:
                continue
            land_geometry = _as_multipolygon(land)
            owner_region, _, _ = min(
                intersections,
                key=lambda item: (-item[1], item[0].istat_code),
            )
            cells.append(
                GridCellDefinition(
                    cell_id=format_cell_id(corner_e=corner_e, corner_n=corner_n, size_m=cell_size_m),
                    corner_e=corner_e,
                    corner_n=corner_n,
                    geometry=square,
                    land_geometry=land_geometry,
                    land_share=min(1.0, max(0.0, land.area / square.area)),
                    owner_code=owner_region.istat_code,
                    owner_name=owner_region.name,
                )
            )
    return cells


def _clip_regions_to_chunk(
    *, regions: Iterable[RegionBoundary], bounds: GridChunkBounds
) -> list[RegionBoundary]:
    """Clip candidate regions once so cells never intersect full national geometries."""
    regions_list = list(regions)
    chunk_polygon = _chunk_polygon(bounds=bounds)
    tree = STRtree([region.geometry for region in regions_list])
    clipped_regions: list[RegionBoundary] = []
    for index in tree.query(chunk_polygon, predicate="intersects"):
        region = regions_list[int(index)]
        clipped = region.geometry.intersection(chunk_polygon)
        if clipped.is_empty or clipped.area <= 0:
            continue
        clipped_regions.append(
            RegionBoundary(
                istat_code=region.istat_code,
                name=region.name,
                geometry=_as_multipolygon(clipped),
            )
        )
    return clipped_regions


def _chunk_polygon(*, bounds: GridChunkBounds) -> Polygon:
    return box(bounds.west_e, bounds.south_n, bounds.east_e, bounds.north_n)


def _as_multipolygon(geometry: object) -> MultiPolygon:
    if isinstance(geometry, Polygon):
        result = MultiPolygon([geometry])
    elif isinstance(geometry, MultiPolygon):
        result = geometry
    else:
        polygon_parts = [part for part in getattr(geometry, "geoms", ()) if isinstance(part, Polygon)]
        if not polygon_parts:
            raise ValueError("Positive land intersection has no polygon geometry.")
        result = MultiPolygon(polygon_parts)
    if not result.is_valid:
        raise ValueError("Positive land intersection is invalid.")
    return result
