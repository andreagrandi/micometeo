"""Cache requested JRC squares and freeze their inputs with each update.

Area detail reads use the saved inputs, never current files or cache rows.
"""

import logging
import hashlib
from pathlib import Path
from typing import Any

from django.conf import settings

from sporameteo.forecast_method import CURRENT_METHOD, HostTrees
from sporameteo.host_trees import read_manifest, sample_squares
from national_forest.models import ForestCell
from national_grid.models import GridBuildCell

from .models import HostTreeCache


logger = logging.getLogger(__name__)


def calculation_version() -> str:
    try:
        selected = read_manifest(directory=Path(settings.SPORAMETEO_JRC_DIRECTORY))
        source = selected[1] if selected is not None else "missing"
    except (OSError, ValueError, KeyError):
        source = "missing"
    return hashlib.sha256(f"{CURRENT_METHOD.version}:{source}".encode()).hexdigest()


def host_tree_source_version() -> str:
    """Return the version of the local JRC files, or an empty string when unusable."""
    try:
        selected = read_manifest(directory=Path(settings.SPORAMETEO_JRC_DIRECTORY))
    except (OSError, ValueError, KeyError):
        return ""
    return selected[1] if selected is not None else ""


def tree_inputs_for_area(*, forest_cells: list[ForestCell]) -> dict[str, Any]:
    directory = Path(settings.SPORAMETEO_JRC_DIRECTORY)
    try:
        selected = read_manifest(directory=directory)
        if selected is None:
            return {}
        manifest, version = selected
        memberships = {row.id: row.grid_build_cell_id for row in forest_cells}
        grid_memberships = list(GridBuildCell.objects.filter(id__in=memberships.values()).select_related("cell"))
        cells = [row.cell for row in grid_memberships]
        cached = {
            row.cell_id: row.values for row in HostTreeCache.objects.filter(
                source_version=version, cell_id__in=[cell.cell_id for cell in cells],
            )
        }
        missing = {
            cell.cell_id: (cell.corner_e + 250.0, cell.corner_n + 250.0)
            for cell in cells if cell.cell_id not in cached
        }
        sampled = sample_squares(directory=directory, manifest=manifest, version=version, centres=missing)
        HostTreeCache.objects.bulk_create(
            [HostTreeCache(source_version=version, cell_id=key, values=list(value.values))
             for key, value in sampled.items()],
            ignore_conflicts=True,
        )
        cached.update({key: list(value.values) for key, value in sampled.items()})
        cell_ids = {row.id: row.cell_id for row in grid_memberships}
        return {
            "source": {
                "source_id": f"jrc:{version}", "source_year": manifest["source_year"],
                "resolution_m": manifest["resolution_m"], "metadata": manifest,
            },
            "cells": {str(key): cached[cell_ids[value]] for key, value in memberships.items()},
        }
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("JRC data unavailable; using forest-only estimates: %s", exc)
        return {}


def saved_host_trees(*, tree_inputs: dict[str, Any], forest_cell_id: int) -> HostTrees | None:
    if not tree_inputs:
        return None
    return HostTrees(values=tuple(tree_inputs["cells"][str(forest_cell_id)]), **tree_inputs["source"])
