"""Store daily weather rows from the Open-Meteo files, as an alternative to the API."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, NamedTuple
from uuid import UUID

from django.db import transaction

from sporameteo.weather import bucket_files
from sporameteo.weather.bucket_files import BucketSource, Match, WeatherFileSource
from sporameteo.weather.features import day_start
from sporameteo.weather.policy import FORECAST_DAYS, HISTORY_DAYS, PIPELINE_VERSION, WEATHER_HISTORY_VERSION

from .aggregation import aggregate_hourly
from .models import FileWeatherRead, WeatherDaily, WeatherSnapshot
from .services import WeatherDailyConflictError, build_weather_snapshot

SOURCE_PROVIDER = "open-meteo-files"
SOURCE_MODEL = "ecmwf_ifs"
SOURCE_ENDPOINT = "https://openmeteo.s3.amazonaws.com/data/ecmwf_ifs"
SOURCE_ID = "open-meteo-files:ecmwf_ifs"
VALUE_KIND = "modelled file values"
MAX_READ_BYTES = 1_000_000_000
BLOCK_SIZE = 200


@dataclass(frozen=True)
class FileWeatherPlan:
    """What a read of the files would do, worked out from the database only."""

    assessment_date: date
    cells_total: int
    cells_already_ready: int
    cells_to_write: int
    first_day: date | None
    last_day: date | None
    chunk_files: int
    estimated_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "assessment_date": self.assessment_date.isoformat(),
            "cells_total": self.cells_total,
            "cells_already_ready": self.cells_already_ready,
            "cells_to_write": self.cells_to_write,
            "first_day": self.first_day.isoformat() if self.first_day else None,
            "last_day": self.last_day.isoformat() if self.last_day else None,
            "chunk_files": self.chunk_files,
            "estimated_megabytes": round(self.estimated_bytes / 1_000_000, 1),
        }


def window_dates(*, assessment_date: date) -> list[date]:
    """Return the 38 dates of the weather window."""
    first = assessment_date - timedelta(days=HISTORY_DAYS)
    return [first + timedelta(days=offset) for offset in range(HISTORY_DAYS + 1 + FORECAST_DAYS)]


def _ready_cell_keys(*, cell_keys: list[str], assessment_date: date) -> set[str]:
    return set(
        WeatherSnapshot.objects.filter(
            cell_key__in=cell_keys, assessment_date=assessment_date, pipeline_version=PIPELINE_VERSION
        ).values_list("cell_key", flat=True)
    )


class StoredDay(NamedTuple):
    """The id and reference elevation of a stored daily row, which is all a snapshot needs from it."""

    id: UUID
    reference_elevation_m: float | None


def _reusable_rows(
    *, cell_keys: list[str], assessment_date: date, run_time: datetime | None
) -> dict[str, dict[date, StoredDay]]:
    """Return the stored file rows that stay valid, by cell and date, reading only the columns that are needed.

    A past day counts only when it never was a forecast. A day from the assessment date on counts only when it came from the newest run.
    """
    dates = window_dates(assessment_date=assessment_date)
    candidates = (
        WeatherDaily.objects.filter(
            cell_key__in=cell_keys,
            source_endpoint=SOURCE_ENDPOINT,
            date__gte=dates[0],
            date__lte=dates[-1],
            status=WeatherDaily.Status.COMPLETE,
        )
        .order_by("created_at", "id")
        .values_list("cell_key", "date", "forecast_issue_time", "metadata__history_version", "id", "reference_elevation_m")
    )
    rows: dict[str, dict[date, StoredDay]] = {key: {} for key in cell_keys}
    for cell_key, day, issue_time, history_version, row_id, elevation in candidates.iterator(chunk_size=5000):
        if day < assessment_date:
            if issue_time is not None or history_version != WEATHER_HISTORY_VERSION:
                continue
        elif run_time is None or issue_time != run_time:
            continue
        rows[cell_key].setdefault(day, StoredDay(id=row_id, reference_elevation_m=elevation))
    return rows


def _needed_dates(*, assessment_date: date, reusable: dict[date, StoredDay]) -> list[date]:
    return [day for day in window_dates(assessment_date=assessment_date) if day not in reusable]


def _blocks(*, keys: list[str], block_size: int) -> list[list[str]]:
    return [keys[start : start + block_size] for start in range(0, len(keys), block_size)]


def _scan_needed(
    *, open_keys: list[str], assessment_date: date, run_time: datetime | None, block_size: int
) -> tuple[set[str], date | None, date | None]:
    """Return the cells that need days and the first and last day needed, loading the stored rows one block at a time."""
    reading: set[str] = set()
    first_day: date | None = None
    last_day: date | None = None
    for block in _blocks(keys=open_keys, block_size=block_size):
        reusable = _reusable_rows(cell_keys=block, assessment_date=assessment_date, run_time=run_time)
        for key in block:
            days = _needed_dates(assessment_date=assessment_date, reusable=reusable[key])
            if days:
                reading.add(key)
                first_day = days[0] if first_day is None else min(first_day, days[0])
                last_day = days[-1] if last_day is None else max(last_day, days[-1])
    return reading, first_day, last_day


def plan_file_weather(*, cells: Any, assessment_date: date, block_size: int = BLOCK_SIZE) -> FileWeatherPlan:
    """Work out from the database what a read would do, without any network call.

    The newest run is unknown here, so every day from the assessment date on counts as needed.
    """
    keys = [cell.key for cell in cells]
    ready = _ready_cell_keys(cell_keys=keys, assessment_date=assessment_date)
    open_keys = [key for key in keys if key not in ready]
    needed, first_day, last_day = _scan_needed(
        open_keys=open_keys, assessment_date=assessment_date, run_time=None, block_size=block_size
    )
    if not needed:
        return FileWeatherPlan(
            assessment_date=assessment_date,
            cells_total=len(keys),
            cells_already_ready=len(ready),
            cells_to_write=len(open_keys),
            first_day=None,
            last_day=None,
            chunk_files=0,
            estimated_bytes=0,
        )
    first_hour, end_hour = bucket_files.local_window_hours(first_day=first_day, last_day=last_day)
    return FileWeatherPlan(
        assessment_date=assessment_date,
        cells_total=len(keys),
        cells_already_ready=len(ready),
        cells_to_write=len(open_keys),
        first_day=first_day,
        last_day=last_day,
        chunk_files=len(bucket_files.chunk_paths(first_hour=first_hour, last_hour=end_hour)),
        estimated_bytes=bucket_files.estimate_read_bytes(cell_count=len(needed), first_day=first_day, last_day=last_day),
    )


def _day_files(*, day: date, file_modified: dict[str, datetime]) -> dict[str, datetime]:
    """Return the modification time of the chunk files that hold the hours of one Italian day."""
    first_hour = int(day_start(day=day).timestamp()) // 3600
    last_hour = int(day_start(day=day + timedelta(days=1)).timestamp()) // 3600
    return {
        path: file_modified[path] for path in bucket_files.chunk_paths(first_hour=first_hour, last_hour=last_hour) if path in file_modified
    }


def _row_fields(
    *,
    read: FileWeatherRead,
    cell: Any,
    match: Match,
    retrieved_at: datetime,
    run_time: datetime,
    file_modified: dict[str, datetime],
    daily: Any,
) -> dict[str, Any]:
    is_forecast = daily.date >= read.assessment_date
    latitude, longitude = bucket_files.point_coordinates(point=match.point)
    day_files = _day_files(day=daily.date, file_modified=file_modified)
    elevation = None if math.isnan(match.place_height) else match.place_height
    return {
        "cell_key": cell.key,
        "date": daily.date,
        "source_provider": SOURCE_PROVIDER,
        "source_model": SOURCE_MODEL,
        "source_endpoint": SOURCE_ENDPOINT,
        "source_id": SOURCE_ID,
        "request_id": f"files:{read.id}",
        "attempt_id": read.id,
        "retrieved_at": retrieved_at,
        "forecast_issue_time": run_time if is_forecast else None,
        "publication_time": max(day_files.values(), default=None),
        "requested_latitude": cell.latitude,
        "requested_longitude": cell.longitude,
        "returned_latitude": latitude,
        "returned_longitude": longitude,
        "reference_elevation_m": elevation,
        "rain_mm": daily.rain_mm,
        "mean_temperature_c": daily.mean_temperature_c,
        "min_temperature_c": daily.min_temperature_c,
        "et0_mm": daily.et0_mm,
        "mean_soil_temperature_c": daily.mean_soil_temperature_c,
        "mean_soil_moisture": daily.mean_soil_moisture,
        "status": WeatherDaily.Status.COMPLETE,
        "metadata": {
            **daily.metadata,
            **({} if is_forecast else {"history_version": WEATHER_HISTORY_VERSION}),
            "location": {
                "grid_point": match.point,
                "grid_latitude": latitude,
                "grid_longitude": longitude,
                "grid_height_m": match.point_height,
                "height_correction_c": match.correction,
            },
            "source": {
                "provider": SOURCE_PROVIDER,
                "model": SOURCE_MODEL,
                "endpoint": SOURCE_ENDPOINT,
                "read_id": str(read.id),
                "retrieved_at": retrieved_at.isoformat(),
                "run_time": run_time.isoformat(),
                "file_modified": {path: moment.isoformat() for path, moment in day_files.items()},
                "value_kind": VALUE_KIND,
            },
        },
    }


def _is_complete(*, daily: Any) -> bool:
    return None not in (
        daily.rain_mm,
        daily.mean_temperature_c,
        daily.et0_mm,
        daily.mean_soil_temperature_c,
        daily.mean_soil_moisture,
    )


def _snapshot_for(*, cell_key: str, assessment_date: date, rows: dict[date, StoredDay], elevation: float | None) -> bool:
    """Build the snapshot when all 38 days have a row. Return whether one now exists."""
    if any(day not in rows for day in window_dates(assessment_date=assessment_date)):
        return False
    result = build_weather_snapshot(
        cell_key=cell_key,
        assessment_date=assessment_date,
        reference_elevation_m=elevation,
        new_daily_row_ids=[rows[day].id for day in window_dates(assessment_date=assessment_date)],
        pipeline_version=PIPELINE_VERSION,
    )
    return result.snapshot is not None


def _store_cell(
    *,
    read: FileWeatherRead,
    cell: Any,
    match: Match,
    hours: bucket_files.CellHours,
    needed: list[date],
    reused: dict[date, StoredDay],
    retrieved_at: datetime,
    run_time: datetime,
    file_modified: dict[str, datetime],
) -> tuple[bool, dict[str, Any] | None]:
    """Store the complete needed days of one cell. Return whether a snapshot exists and what is missing."""
    days = aggregate_hourly(
        hourly_timestamps=hours.timestamps,
        variables={
            "precipitation": hours.precipitation,
            "temperature": hours.temperature,
            "soil_moisture": hours.soil_moisture,
            "soil_temperature": hours.soil_temperature,
            "et0": hours.et0,
        },
        start=needed[0],
        end=needed[-1],
    )
    by_date = {daily.date: daily for daily in days}
    rows = dict(reused)
    incomplete: list[str] = []
    try:
        with transaction.atomic():
            for day in needed:
                daily = by_date[day]
                if not _is_complete(daily=daily):
                    incomplete.append(day.isoformat())
                    continue
                created = WeatherDaily.objects.create(
                    **_row_fields(
                        read=read,
                        cell=cell,
                        match=match,
                        retrieved_at=retrieved_at,
                        run_time=run_time,
                        file_modified=file_modified,
                        daily=daily,
                    )
                )
                rows[day] = StoredDay(id=created.id, reference_elevation_m=created.reference_elevation_m)
            elevation = None if math.isnan(match.place_height) else match.place_height
            has_snapshot = _snapshot_for(cell_key=cell.key, assessment_date=read.assessment_date, rows=rows, elevation=elevation)
    except WeatherDailyConflictError as exc:
        return False, {"reason": "conflict", "error": str(exc), "dates": []}
    if incomplete:
        return has_snapshot, {"reason": "missing_hours", "dates": incomplete}
    return has_snapshot, None


def store_file_weather(
    *,
    cells: Any,
    assessment_date: date,
    region_code: str,
    source: WeatherFileSource | None = None,
    block_size: int = BLOCK_SIZE,
) -> FileWeatherRead:
    """Read the files once for all cells that need days, store the complete days and build snapshots.

    The downloaded values stay in compact arrays. Stored rows are loaded and the Python values are built for
    block_size cells at a time. A file that fails to read ends the read as failed and stores no row.
    """
    plan = plan_file_weather(cells=cells, assessment_date=assessment_date, block_size=block_size)
    if plan.estimated_bytes > MAX_READ_BYTES:
        raise ValueError(f"The read would download about {plan.estimated_bytes} bytes, over the limit of {MAX_READ_BYTES}.")
    source = source or BucketSource()
    read = FileWeatherRead.objects.create(
        assessment_date=assessment_date,
        region_code=region_code,
        started_at=datetime.now(tz=UTC),
        cells_total=len(cells),
    )
    try:
        run_time = bucket_files.read_newest_run(source=source)
        read.run_time = run_time
        by_key = {cell.key: cell for cell in cells}
        ready = _ready_cell_keys(cell_keys=list(by_key), assessment_date=assessment_date)
        open_keys = [key for key in by_key if key not in ready]
        reading, first_day, last_day = _scan_needed(
            open_keys=open_keys, assessment_date=assessment_date, run_time=run_time, block_size=block_size
        )
        arrays: bucket_files.HourArrays | None = None
        file_modified: dict[str, datetime] = {}
        if reading:
            matches = bucket_files.match_cells(
                source=source,
                cells={key: (by_key[key].latitude, by_key[key].longitude) for key in open_keys if key in reading},
            )
            arrays = bucket_files.read_hour_arrays(source=source, matches=matches, first_day=first_day, last_day=last_day)
            file_modified = arrays.file_modified
        retrieved_at = datetime.now(tz=UTC)
    except Exception as exc:
        read.status = FileWeatherRead.Status.FAILED
        read.error = f"{type(exc).__name__}: {exc}"
        read.bytes_read = source.bytes_read()
        read.http_requests = source.request_count()
        read.finished_at = datetime.now(tz=UTC)
        read.save()
        return read

    written = 0
    missing: dict[str, Any] = {}
    timestamps = arrays.timestamps if arrays is not None else ()
    for block in _blocks(keys=open_keys, block_size=block_size):
        reusable = _reusable_rows(cell_keys=block, assessment_date=assessment_date, run_time=run_time)
        toa_cache: dict[tuple[float, float], Any] = {}
        for key in block:
            if key not in reading:
                rows = reusable[key]
                elevation = next(iter(rows.values())).reference_elevation_m
                try:
                    with transaction.atomic():
                        written += _snapshot_for(cell_key=key, assessment_date=assessment_date, rows=rows, elevation=elevation)
                except WeatherDailyConflictError as exc:
                    missing[key] = {"reason": "conflict", "error": str(exc), "dates": []}
                continue
            has_snapshot, problem = _store_cell(
                read=read,
                cell=by_key[key],
                match=arrays.matches[key],
                hours=bucket_files.cell_hours_from_arrays(arrays=arrays, key=key, timestamps=timestamps, toa_cache=toa_cache),
                needed=_needed_dates(assessment_date=assessment_date, reusable=reusable[key]),
                reused=reusable[key],
                retrieved_at=retrieved_at,
                run_time=run_time,
                file_modified=file_modified,
            )
            written += has_snapshot
            if problem is not None:
                missing[key] = problem
    read.cells_written = written
    read.cells_already_ready = len(ready)
    read.missing = missing
    read.file_modified = {path: moment.isoformat() for path, moment in file_modified.items()}
    read.bytes_read = source.bytes_read()
    read.http_requests = source.request_count()
    read.status = FileWeatherRead.Status.COMPLETE
    read.finished_at = datetime.now(tz=UTC)
    read.save()
    return read
