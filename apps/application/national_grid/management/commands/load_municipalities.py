"""Store ISTAT municipalities and name the municipality of each grid square."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from national_grid.models import GridBuildCell, GridCell, GridRegion, Municipality
from national_grid.source import (
    ARCHIVE_SHA256,
    BoundarySourceError,
    MunicipalityBoundary,
    read_municipalities,
)

# The largest overlap wins and the lowest code breaks a tie, like owner_region in geometry.py.
ASSIGN_SQL = """
WITH owned AS (
    SELECT DISTINCT build_cell.cell_id
    FROM {build_cell} AS build_cell
    JOIN {region} AS region ON region.id = build_cell.owner_region_id
    WHERE region.istat_code = %(region_code)s
),
best AS (
    SELECT DISTINCT ON (overlap.cell_id) overlap.cell_id, overlap.istat_code
    FROM (
        SELECT cell.cell_id,
               municipality.istat_code,
               ST_Area(ST_Intersection(municipality.geometry, cell.geometry)) AS area
        FROM owned
        JOIN {cell} AS cell ON cell.cell_id = owned.cell_id
        JOIN {municipality} AS municipality ON ST_Intersects(municipality.geometry, cell.geometry)
        WHERE municipality.region_code = %(region_code)s
    ) AS overlap
    WHERE overlap.area > 0
    ORDER BY overlap.cell_id, overlap.area DESC, overlap.istat_code
),
changes AS (
    SELECT cell.cell_id, best.istat_code, cell.municipality_id AS old_code
    FROM best
    JOIN {cell} AS cell ON cell.cell_id = best.cell_id
    WHERE cell.municipality_id IS DISTINCT FROM best.istat_code
),
updated AS (
    UPDATE {cell} AS cell
    SET municipality_id = changes.istat_code
    FROM changes
    WHERE cell.cell_id = changes.cell_id
    RETURNING cell.cell_id
)
SELECT count(*) FILTER (WHERE old_code IS NULL), count(*) FILTER (WHERE old_code IS NOT NULL)
FROM changes
"""


class Command(BaseCommand):
    """Load municipality borders and assign them to the squares of one region."""

    help = "Store municipalities of one region and name the municipality of each of its squares."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--archive-path",
            type=Path,
            default=Path(settings.BASE_DIR).parents[1] / "data/raw/mvp_boundaries/Limiti01012026.zip",
        )
        parser.add_argument("--expected-sha256", default=ARCHIVE_SHA256)
        parser.add_argument("--region-code", default="09")

    def handle(self, *args: Any, **options: Any) -> None:
        region_code = str(options["region_code"])
        try:
            boundaries = read_municipalities(
                archive_path=Path(options["archive_path"]),
                region_code=region_code,
                expected_sha256=str(options["expected_sha256"]),
            )
        except (BoundarySourceError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        with transaction.atomic():
            result = _store_municipalities(boundaries=boundaries)
            result.update(_assign_squares(region_code=region_code))
        self.stdout.write(json.dumps(result, sort_keys=True))


def _store_municipalities(*, boundaries: tuple[MunicipalityBoundary, ...]) -> dict[str, int]:
    existing = {item.istat_code: item for item in Municipality.objects.all()}
    created: list[Municipality] = []
    changed: list[Municipality] = []
    unchanged = 0
    for boundary in boundaries:
        geometry = GEOSGeometry(boundary.geometry.wkb_hex, srid=3035)
        stored = existing.get(boundary.istat_code)
        if stored is None:
            created.append(
                Municipality(
                    istat_code=boundary.istat_code,
                    name=boundary.name,
                    region_code=boundary.region_code,
                    geometry=geometry,
                )
            )
        elif (
            stored.name != boundary.name
            or stored.region_code != boundary.region_code
            or not stored.geometry.equals_exact(geometry, 0)
        ):
            stored.name = boundary.name
            stored.region_code = boundary.region_code
            stored.geometry = geometry
            changed.append(stored)
        else:
            unchanged += 1
    Municipality.objects.bulk_create(created)
    Municipality.objects.bulk_update(changed, ["name", "region_code", "geometry"])
    return {
        "municipalities_created": len(created),
        "municipalities_updated": len(changed),
        "municipalities_unchanged": unchanged,
    }


def _assign_squares(*, region_code: str) -> dict[str, int]:
    sql = ASSIGN_SQL.format(
        build_cell=GridBuildCell._meta.db_table,
        region=GridRegion._meta.db_table,
        cell=GridCell._meta.db_table,
        municipality=Municipality._meta.db_table,
    )
    with connection.cursor() as cursor:
        cursor.execute(sql, {"region_code": region_code})
        assigned, changed = cursor.fetchone()
    without = (
        GridCell.objects.filter(
            build_memberships__owner_region__istat_code=region_code, municipality__isnull=True
        )
        .distinct()
        .count()
    )
    return {
        "squares_assigned": assigned,
        "squares_changed": changed,
        "squares_without_municipality": without,
    }
