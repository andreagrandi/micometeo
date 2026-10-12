"""Measure estimate calculation and storage in a disposable benchmark database."""

from __future__ import annotations

import time
import uuid
from datetime import date, timedelta
from typing import Any

from django.db import connection, transaction
from django.utils import timezone

from national_forest.models import ForestBuild, ForestCell
from national_terrain.models import TerrainBuild
from weather_requests.eligibility import canonical_cell_key
from weather_summaries.models import WeatherDaily, WeatherSnapshot, WeatherSnapshotDay, WeatherSummary

from .services import calculate_and_publish_estimates


BENCHMARK_SOURCE = "synthetic-benchmark-29dweather"


def _database_sizes() -> dict[str, Any]:
    table_names = (
        "estimate_updates_estimateupdate",
        "estimate_updates_estimateresult",
        "estimate_updates_estimatetask",
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_database_size(current_database())")
        database_bytes = int(cursor.fetchone()[0])
        relation_sizes: dict[str, dict[str, int]] = {}
        for table_name in table_names:
            cursor.execute(
                """
                SELECT pg_relation_size(%s::regclass),
                       pg_indexes_size(%s::regclass),
                       pg_total_relation_size(%s::regclass)
                """,
                [table_name, table_name, table_name],
            )
            heap_bytes, index_bytes, total_bytes = cursor.fetchone()
            relation_sizes[table_name] = {
                "heap_bytes": int(heap_bytes),
                "index_bytes": int(index_bytes),
                "total_bytes": int(total_bytes),
            }
        cursor.execute(
            """
            SELECT COALESCE(SUM(pg_relation_size(indexrelid)), 0)
            FROM pg_index
            JOIN pg_class ON pg_class.oid = pg_index.indexrelid
            WHERE pg_class.relname = %s
            """,
            ["estimate_forest_cell_weather_lookup_idx"],
        )
        lookup_index_bytes = int(cursor.fetchone()[0])
    estimate_bytes = sum(item["total_bytes"] for item in relation_sizes.values())
    return {
        "database_bytes": database_bytes,
        "estimate_tables_bytes": estimate_bytes,
        "estimate_table_bytes": relation_sizes,
        "forest_lookup_index_bytes": lookup_index_bytes,
    }


def _synthetic_daily_rows(*, snapshot: WeatherSnapshot, assessment_date: date) -> None:
    """Link synthetic daily temperatures to the snapshot for the 20-day temperature period."""
    attempt_id = uuid.uuid4()
    retrieved_at = timezone.now()
    days = [assessment_date + timedelta(days=offset) for offset in range(-21, 8)]
    rows = [
        WeatherDaily(
            cell_key=snapshot.cell_key,
            date=day,
            source_provider=BENCHMARK_SOURCE,
            source_model=BENCHMARK_SOURCE,
            source_endpoint="https://example.test/synthetic-benchmark",
            source_id=BENCHMARK_SOURCE,
            request_id=BENCHMARK_SOURCE,
            attempt_id=attempt_id,
            retrieved_at=retrieved_at,
            requested_latitude=0.0,
            requested_longitude=0.0,
            returned_latitude=0.0,
            returned_longitude=0.0,
            reference_elevation_m=snapshot.reference_elevation_m,
            rain_mm=0.0,
            mean_temperature_c=16.25,
            min_temperature_c=8.0,
            status=WeatherDaily.Status.COMPLETE,
            metadata={"benchmark": BENCHMARK_SOURCE},
        )
        for day in days
    ]
    WeatherDaily.objects.bulk_create(rows)
    WeatherSnapshotDay.objects.bulk_create(
        [WeatherSnapshotDay(snapshot=snapshot, date=row.date, daily=row) for row in rows]
    )


def _synthetic_snapshot(*, cell_key: str, assessment_date: date) -> WeatherSnapshot:
    metadata = {
        "benchmark": BENCHMARK_SOURCE,
        "network_used": False,
        "date_start": (assessment_date - timedelta(days=21)).isoformat(),
        "date_end": (assessment_date + timedelta(days=7)).isoformat(),
    }
    snapshot, created = WeatherSnapshot.objects.get_or_create(
        cell_key=cell_key,
        assessment_date=assessment_date,
        defaults={
            "reference_elevation_m": 500.0,
            "latest_retrieval": timezone.now(),
            "source_ids": [BENCHMARK_SOURCE],
            "source_attempt_ids": [BENCHMARK_SOURCE],
            "metadata": metadata,
        },
    )
    if not created:
        if snapshot.metadata.get("benchmark") != BENCHMARK_SOURCE:
            raise ValueError(
                f"Snapshot {snapshot.id} already contains non-benchmark weather inputs."
            )
        return snapshot
    _synthetic_daily_rows(snapshot=snapshot, assessment_date=assessment_date)
    summaries = []
    for days_ahead in range(8):
        target_date = assessment_date + timedelta(days=days_ahead)
        summaries.append(
            WeatherSummary(
                snapshot=snapshot,
                target_date=target_date,
                days_ahead=days_ahead,
                old_rain_mm=60.0,
                recent_rain_mm=30.0,
                target_mean_temperature_c=16.25,
                metadata={
                    "benchmark": BENCHMARK_SOURCE,
                    "old_rain": {
                        "period_start": (target_date - timedelta(days=21)).isoformat(),
                        "period_end": (target_date - timedelta(days=8)).isoformat(),
                        "completed_day_count": 14,
                        "forecast_day_count": 0,
                        "source_ids": [BENCHMARK_SOURCE],
                    },
                    "recent_rain": {
                        "period_start": (target_date - timedelta(days=7)).isoformat(),
                        "period_end": (target_date - timedelta(days=1)).isoformat(),
                        "completed_day_count": 7 - days_ahead,
                        "forecast_day_count": days_ahead,
                        "source_ids": [BENCHMARK_SOURCE],
                    },
                    "target": {
                        "period_start": target_date.isoformat(),
                        "period_end": target_date.isoformat(),
                        "completed_day_count": 0,
                        "forecast_day_count": 1,
                        "source_ids": [BENCHMARK_SOURCE],
                    },
                },
            )
        )
    WeatherSummary.objects.bulk_create(summaries)
    return snapshot


def benchmark_estimate_updates(
    *,
    forest_build_version: str,
    terrain_build_version: str,
    assessment_date: date,
    cell_key: str | None = None,
) -> dict[str, Any]:
    """Run a resumable local benchmark using synthetic weather only."""
    if "estimate_benchmark" not in connection.settings_dict["NAME"]:
        raise ValueError(
            "The database name must contain estimate_benchmark. Use a disposable benchmark database."
        )
    forest_build = ForestBuild.objects.get(version=forest_build_version)
    TerrainBuild.objects.get(version=terrain_build_version)
    rows = ForestCell.objects.filter(build=forest_build, is_forest=True).only(
        "weather_latitude", "weather_longitude"
    )
    cells = sorted(
        {
            canonical_cell_key(latitude=row.weather_latitude, longitude=row.weather_longitude)
            for row in rows
            if row.weather_latitude is not None and row.weather_longitude is not None
        }
    )
    if cell_key is not None:
        if cell_key not in cells:
            raise ValueError(f"No completed forest square belongs to weather cell {cell_key!r}.")
        cells = [cell_key]
    if not cells:
        raise ValueError("The selected forest build has no weather cells.")
    before = _database_sizes()
    started = time.monotonic()
    measurements: list[dict[str, Any]] = []
    for current_cell in cells:
        cell_started = time.monotonic()
        with transaction.atomic():
            first_snapshot = _synthetic_snapshot(
                cell_key=current_cell,
                assessment_date=assessment_date,
            )
            second_snapshot = _synthetic_snapshot(
                cell_key=current_cell,
                assessment_date=assessment_date + timedelta(days=1),
            )
        first = calculate_and_publish_estimates(
            snapshot_id=first_snapshot.id,
            cell_key=current_cell,
            assessment_date=assessment_date,
            forest_build_version=forest_build_version,
            terrain_build_version=terrain_build_version,
        )
        second = calculate_and_publish_estimates(
            snapshot_id=second_snapshot.id,
            cell_key=current_cell,
            assessment_date=assessment_date + timedelta(days=1),
            forest_build_version=forest_build_version,
            terrain_build_version=terrain_build_version,
        )
        measurements.append(
            {
                "cell_key": current_cell,
                "elapsed_seconds": round(time.monotonic() - cell_started, 4),
                "assessment_count": 2,
                "row_counts": [first.update.row_count, second.update.row_count],
                "update_ids": [str(first.update.public_id), str(second.update.public_id)],
            }
        )
    after = _database_sizes()
    return {
        "benchmark_source": BENCHMARK_SOURCE,
        "network_used": False,
        "mode": "cell" if cell_key else "national",
        "cell_count": len(cells),
        "elapsed_seconds": round(time.monotonic() - started, 4),
        "cells": measurements,
        "database_before": before,
        "database_after": after,
        "database_growth_bytes": after["database_bytes"] - before["database_bytes"],
        "estimate_growth_bytes": after["estimate_tables_bytes"] - before["estimate_tables_bytes"],
        "target_estimate_storage_bytes": 100 * 1024 * 1024,
    }
