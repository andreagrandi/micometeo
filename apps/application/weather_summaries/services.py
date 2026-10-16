"""Persist normalized weather responses and freeze assessment summaries."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
import math
from typing import Any
from uuid import UUID

from django.db import transaction

from sporameteo.weather.policy import HISTORY_DAYS, WEATHER_HISTORY_VERSION, history_endpoint

from .aggregation import DailyWeather, aggregate_response
from .contracts import NormalizedProviderResponse
from .models import WeatherDaily, WeatherSnapshot, WeatherSnapshotDay, WeatherSummary


class WeatherDailyConflictError(ValueError):
    """Report a second response that would rewrite a protected daily row."""


class WeatherSnapshotIncompleteError(ValueError):
    """Report a requested snapshot with a required missing daily value."""


@dataclass(frozen=True)
class StoredWeatherResult:
    """Expose selected daily rows and a ready snapshot when available."""

    daily: tuple[WeatherDaily, ...]
    snapshot: WeatherSnapshot | None
    summaries: tuple[WeatherSummary, ...]

def _same_daily_content(*, existing: WeatherDaily, incoming: dict[str, Any]) -> bool:
    fields = (
        "cell_key",
        "date",
        "source_provider",
        "source_model",
        "source_endpoint",
        "source_id",
        "request_id",
        "attempt_id",
        "retrieved_at",
        "forecast_issue_time",
        "publication_time",
        "requested_latitude",
        "requested_longitude",
        "returned_latitude",
        "returned_longitude",
        "reference_elevation_m",
        "timezone",
        "rain_mm",
        "mean_temperature_c",
        "min_temperature_c",
        "et0_mm",
        "mean_soil_temperature_c",
        "mean_soil_moisture",
        "status",
        "metadata",
    )
    return all(getattr(existing, field) == incoming[field] for field in fields)


def _daily_kwargs(
    *,
    response: NormalizedProviderResponse,
    daily: DailyWeather,
) -> dict[str, Any]:
    history_metadata = (
        {"history_version": WEATHER_HISTORY_VERSION}
        if response.provider_endpoint == history_endpoint()
        else {}
    )
    return {
        "cell_key": response.location.cell_key,
        "date": daily.date,
        "source_provider": response.provider or response.source_id,
        "source_model": response.model,
        "source_endpoint": response.provider_endpoint,
        "source_id": response.source_id,
        "request_id": response.request_id,
        "attempt_id": response.attempt_id,
        "retrieved_at": response.retrieved_at,
        "forecast_issue_time": response.forecast_issue_time,
        "publication_time": response.publication_time,
        "requested_latitude": response.location.requested_latitude,
        "requested_longitude": response.location.requested_longitude,
        "returned_latitude": response.location.returned_latitude,
        "returned_longitude": response.location.returned_longitude,
        "reference_elevation_m": response.location.elevation_m,
        "timezone": response.location.timezone,
        "rain_mm": daily.rain_mm,
        "mean_temperature_c": daily.mean_temperature_c,
        "min_temperature_c": daily.min_temperature_c,
        "et0_mm": daily.et0_mm,
        "mean_soil_temperature_c": daily.mean_soil_temperature_c,
        "mean_soil_moisture": daily.mean_soil_moisture,
        "status": daily.status,
        "metadata": {
            **daily.metadata,
            **history_metadata,
            "location": dict(response.location.metadata),
            "source": {
                "provider": response.provider or response.source_id,
                "model": response.model,
                "endpoint": response.provider_endpoint,
                "request_id": response.request_id,
                "attempt_id": str(response.attempt_id),
                "retrieved_at": response.retrieved_at.isoformat(),
                "requested_start": (
                    response.requested_start.isoformat() if response.requested_start else None
                ),
                "requested_end": response.requested_end.isoformat() if response.requested_end else None,
                "value_kind": response.metadata.get("value_kind", "modelled provider values"),
                "forecast_issue_time": (
                    response.forecast_issue_time.isoformat()
                    if response.forecast_issue_time
                    else None
                ),
                "publication_time": (
                    response.publication_time.isoformat() if response.publication_time else None
                ),
            },
        },
    }


def stored_history_rows(*, cell_key: str, assessment_date: date) -> dict[date, WeatherDaily]:
    """Return completed history rows stored for one cell, without reading snapshots.

    Only rows from the configured history source and the current history version
    count, and the earliest stored row wins so stored history stays frozen.
    """
    first_day = assessment_date - timedelta(days=HISTORY_DAYS)
    candidates = WeatherDaily.objects.filter(
        cell_key=cell_key,
        date__gte=first_day,
        date__lte=assessment_date - timedelta(days=1),
        source_endpoint=history_endpoint(),
        status__in=[WeatherDaily.Status.COMPLETE, WeatherDaily.Status.CHECKED_KNOWN_MISSING],
    ).order_by("created_at", "id")
    rows: dict[date, WeatherDaily] = {}
    for row in candidates:
        if row.metadata.get("history_version", 1) != WEATHER_HISTORY_VERSION:
            continue
        rows.setdefault(row.date, row)
    return rows


def _period_dates(*, start: date, end: date) -> tuple[date, ...]:
    return tuple(start + timedelta(days=offset) for offset in range((end - start).days + 1))


def _window(
    *,
    rows: Mapping[date, WeatherDaily],
    start: date,
    end: date,
    field: str = "rain_mm",
    assessment_date: date | None = None,
) -> tuple[float | None, tuple[WeatherDaily, ...], int, int]:
    selected = tuple(rows[day] for day in _period_dates(start=start, end=end) if day in rows)
    expected = (end - start).days + 1
    cutoff = assessment_date or end + timedelta(days=1)
    completed_count = sum(day.date < cutoff for day in selected)
    forecast_count = sum(day.date >= cutoff for day in selected)
    if len(selected) != expected:
        return None, selected, completed_count, forecast_count
    values = [getattr(day, field) for day in selected]
    if any(value is None or not math.isfinite(float(value)) for value in values):
        return None, selected, completed_count, forecast_count
    return (
        round(sum(float(value) for value in values if value is not None), 4),
        selected,
        completed_count,
        forecast_count,
    )


def _summary_metadata(
    *,
    rows: tuple[WeatherDaily, ...],
    start: date,
    end: date,
    completed_count: int,
    forecast_count: int,
    value: float | None,
) -> dict[str, Any]:
    return {
        "unit": "mm",
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "inclusive": True,
        "completed_day_count": completed_count,
        "forecast_day_count": forecast_count,
        "daily_ids": [str(row.id) for row in rows],
        "source_ids": list(dict.fromkeys(row.source_id for row in rows)),
        "source_attempt_ids": list(dict.fromkeys(str(row.attempt_id) for row in rows)),
        "value_kinds": list(
            dict.fromkeys(
                row.metadata.get("source", {}).get("value_kind", "modelled provider values")
                for row in rows
            )
        ),
        "retrieval_quality": "complete" if value is not None else "checked_known_missing",
        "reasons": [
            row.metadata.get("variables", {}).get("precipitation", {}).get("reason")
            for row in rows
            if row.metadata.get("variables", {}).get("precipitation", {}).get("reason")
            not in {None, "complete"}
        ],
    }


def _make_summary(
    *,
    snapshot: WeatherSnapshot,
    assessment_date: date,
    target_date: date,
    rows: Mapping[date, WeatherDaily],
) -> WeatherSummary:
    days_ahead = (target_date - assessment_date).days
    visitor: dict[int, tuple[float | None, tuple[WeatherDaily, ...], int, int]] = {}
    for window_days in (7, 14, 21):
        start = assessment_date - timedelta(days=window_days)
        visitor[window_days] = _window(
            rows=rows,
            start=start,
            end=assessment_date - timedelta(days=1),
            assessment_date=assessment_date,
        )
    old_start = target_date - timedelta(days=21)
    old_end = target_date - timedelta(days=8)
    recent_start = target_date - timedelta(days=7)
    recent_end = target_date - timedelta(days=1)
    old_rain, old_rows, old_completed, old_forecast = _window(
        rows=rows,
        start=old_start,
        end=old_end,
        assessment_date=assessment_date,
    )
    recent_rain, recent_rows, recent_completed, recent_forecast = _window(
        rows=rows,
        start=recent_start,
        end=recent_end,
        assessment_date=assessment_date,
    )
    target = rows.get(target_date)
    target_rain = target.rain_mm if target else None
    target_mean_temperature = target.mean_temperature_c if target else None
    target_min_temperature = target.min_temperature_c if target else None
    target_et0 = target.et0_mm if target else None
    target_soil_temperature = target.mean_soil_temperature_c if target else None
    target_soil_moisture = target.mean_soil_moisture if target else None
    target_complete = target is not None and target.status == WeatherDaily.Status.COMPLETE
    target_temperature_complete = (
        target is not None
        and target.metadata.get("variables", {}).get("temperature", {}).get("reason")
        == "complete"
    )
    frost = (
        None
        if not target_temperature_complete or target_min_temperature is None
        else target_min_temperature < 0
    )
    all_summary_rows = tuple(
        row
        for period_rows in [
            visitor[7][1],
            visitor[14][1],
            visitor[21][1],
            old_rows,
            recent_rows,
            (target,) if target else (),
        ]
        for row in period_rows
    )
    metadata = {
        "assessment_date": assessment_date.isoformat(),
        "target_date": target_date.isoformat(),
        "days_ahead": days_ahead,
        "visitor_rain": {
            str(days): _summary_metadata(
                rows=value[1],
                start=assessment_date - timedelta(days=days),
                end=assessment_date - timedelta(days=1),
                completed_count=value[2],
                forecast_count=value[3],
                value=value[0],
            )
            for days, value in visitor.items()
        },
        "old_rain": _summary_metadata(
            rows=old_rows,
            start=old_start,
            end=old_end,
            completed_count=old_completed,
            forecast_count=old_forecast,
            value=old_rain,
        ),
        "recent_rain": _summary_metadata(
            rows=recent_rows,
            start=recent_start,
            end=recent_end,
            completed_count=recent_completed,
            forecast_count=recent_forecast,
            value=recent_rain,
        ),
        "target": {
            "unit": {
                "rain_mm": "mm",
                "mean_temperature_c": "deg_c",
                "min_temperature_c": "deg_c",
                "et0_mm": "mm",
                "mean_soil_temperature_c": "deg_c",
                "mean_soil_moisture": "m3_m3",
            },
            "period_start": target_date.isoformat(),
            "period_end": target_date.isoformat(),
            "inclusive": True,
            "completed_day_count": 0,
            "forecast_day_count": 1,
            "daily_ids": [str(target.id)] if target else [],
            "source_ids": [target.source_id] if target else [],
            "retrieval_quality": "complete" if target_complete else "checked_known_missing",
            "reasons": [] if target_complete else ["target_daily_missing_or_incomplete"],
            "frost_derivation": "target minimum temperature below 0 deg C"
            if frost is not None
            else "unavailable without a complete target temperature day",
            "hail": "unavailable, provider contract has no hail variable",
        },
        "source_ids": list(dict.fromkeys(row.source_id for row in all_summary_rows)),
        "source_attempt_ids": list(dict.fromkeys(str(row.attempt_id) for row in all_summary_rows)),
    }
    return WeatherSummary(
        snapshot=snapshot,
        target_date=target_date,
        days_ahead=days_ahead,
        visitor_rain_7_mm=visitor[7][0],
        visitor_rain_14_mm=visitor[14][0],
        visitor_rain_21_mm=visitor[21][0],
        old_rain_mm=old_rain,
        recent_rain_mm=recent_rain,
        target_rain_mm=target_rain,
        target_mean_temperature_c=target_mean_temperature,
        target_min_temperature_c=target_min_temperature,
        target_et0_mm=target_et0,
        target_mean_soil_temperature_c=target_soil_temperature,
        target_mean_soil_moisture=target_soil_moisture,
        frost=frost,
        hail=None,
        metadata=metadata,
    )


def reusable_previous_daily_rows(
    *,
    previous_snapshot: WeatherSnapshot,
    assessment_date: date,
    cell_key: str,
    reference_elevation_m: float | None,
) -> dict[date, WeatherDaily]:
    """Return rows dated before both assessment dates."""
    if previous_snapshot.status != WeatherSnapshot.Status.READY:
        raise WeatherDailyConflictError("previous snapshot is not ready")
    if previous_snapshot.cell_key != cell_key:
        raise WeatherDailyConflictError("previous snapshot belongs to another weather cell")
    if previous_snapshot.reference_elevation_m != reference_elevation_m:
        raise WeatherDailyConflictError("previous snapshot uses another reference elevation")
    return {
        link.date: link.daily
        for link in previous_snapshot.days.select_related("daily").all()
        if link.date < previous_snapshot.assessment_date and link.date < assessment_date
    }


def _make_snapshot(
    *,
    cell_key: str,
    assessment_date: date,
    reference_elevation_m: float | None,
    rows: Mapping[date, WeatherDaily],
    pipeline_version: int = 1,
) -> tuple[WeatherSnapshot, tuple[WeatherSummary, ...]]:
    dates = _period_dates(
        start=assessment_date - timedelta(days=30 if pipeline_version == 2 else 21),
        end=assessment_date + timedelta(days=7),
    )
    selected = tuple(rows[day] for day in dates)
    latest = max(row.retrieved_at for row in selected)
    snapshot = WeatherSnapshot(
        pipeline_version=pipeline_version,
        cell_key=cell_key,
        assessment_date=assessment_date,
        reference_elevation_m=reference_elevation_m,
        latest_retrieval=latest,
        source_ids=list(dict.fromkeys(row.source_id for row in selected)),
        source_attempt_ids=list(dict.fromkeys(str(row.attempt_id) for row in selected)),
        metadata={
            "daily_ids": [str(row.id) for row in selected],
            "date_start": dates[0].isoformat(),
            "date_end": dates[-1].isoformat(),
            "assessment_date": assessment_date.isoformat(),
        },
    )
    snapshot.save(force_insert=True)
    WeatherSnapshotDay.objects.bulk_create(
        [WeatherSnapshotDay(snapshot=snapshot, date=day, daily=rows[day]) for day in dates]
    )
    summaries = tuple(
        _make_summary(
            snapshot=snapshot,
            assessment_date=assessment_date,
            target_date=assessment_date + timedelta(days=days_ahead),
            rows=rows,
        )
        for days_ahead in range(8)
    )
    WeatherSummary.objects.bulk_create(list(summaries))
    return snapshot, summaries


def _response_date_range(
    *,
    response: NormalizedProviderResponse,
    start: date | None,
    end: date | None,
) -> tuple[date, date]:
    resolved_start = start or response.requested_start
    resolved_end = end or response.requested_end
    if resolved_start is None or resolved_end is None:
        values = aggregate_response(response=response, start=start, end=end)
        if not values:
            raise ValueError("provider response has no daily range")
        resolved_start = resolved_start or values[0].date
        resolved_end = resolved_end or values[-1].date
    if response.requested_start is not None and resolved_start != response.requested_start:
        raise ValueError("storage range must match the provider response start")
    if response.requested_end is not None and resolved_end != response.requested_end:
        raise ValueError("storage range must match the provider response end")
    if resolved_end < resolved_start:
        raise ValueError("storage end date must not precede its start date")
    return resolved_start, resolved_end


@transaction.atomic
def store_weather_daily_rows(
    response: NormalizedProviderResponse,
    start: date,
    end: date,
) -> tuple[WeatherDaily, ...]:
    """Store exactly one normalized response date range as immutable rows."""
    _response_date_range(response=response, start=start, end=end)
    daily_values = aggregate_response(response=response, start=start, end=end)
    expected_dates = _period_dates(start=start, end=end)
    if tuple(value.date for value in daily_values) != expected_dates:
        raise ValueError("provider response did not produce the exact requested date range")
    stored: list[WeatherDaily] = []
    for daily in daily_values:
        incoming = _daily_kwargs(response=response, daily=daily)
        existing = WeatherDaily.objects.filter(
            attempt_id=response.attempt_id,
            cell_key=response.location.cell_key,
            date=daily.date,
        ).first()
        if existing is not None:
            if not _same_daily_content(existing=existing, incoming=incoming):
                raise WeatherDailyConflictError(
                    f"weather daily row for attempt {response.attempt_id} and "
                    f"{response.location.cell_key} {daily.date} conflicts"
                )
            stored.append(existing)
            continue
        stored.append(WeatherDaily.objects.create(**incoming))
    return tuple(stored)


@transaction.atomic
def build_weather_snapshot(
    cell_key: str,
    assessment_date: date,
    reference_elevation_m: float | None,
    new_daily_row_ids: Iterable[UUID | str],
    previous_snapshot: WeatherSnapshot | None = None,
    pipeline_version: int = 1,
) -> StoredWeatherResult:
    """Build a snapshot from explicit new rows and one safe prior snapshot."""
    required_dates = _period_dates(
        start=assessment_date - timedelta(days=30 if pipeline_version == 2 else 21),
        end=assessment_date + timedelta(days=7),
    )
    requested_ids = tuple(UUID(str(row_id)) for row_id in new_daily_row_ids)
    if len(set(requested_ids)) != len(requested_ids):
        raise WeatherDailyConflictError("new daily row IDs must be unique")
    new_rows = tuple(
        WeatherDaily.objects.filter(id__in=requested_ids).order_by("date", "id")
    )
    if len(new_rows) != len(requested_ids):
        raise WeatherDailyConflictError("one or more new daily rows do not exist")
    new_by_date: dict[date, WeatherDaily] = {}
    for row in new_rows:
        if row.cell_key != cell_key:
            raise WeatherDailyConflictError("new daily row belongs to another weather cell")
        if row.reference_elevation_m != reference_elevation_m:
            raise WeatherDailyConflictError("new daily row uses another reference elevation")
        if row.date not in required_dates:
            raise WeatherDailyConflictError("new daily row falls outside the snapshot range")
        previous = new_by_date.get(row.date)
        if previous is not None and previous.id != row.id:
            raise WeatherDailyConflictError("multiple new daily rows cover one date")
        new_by_date[row.date] = row

    previous_rows = (
        reusable_previous_daily_rows(
            previous_snapshot=previous_snapshot,
            assessment_date=assessment_date,
            cell_key=cell_key,
            reference_elevation_m=reference_elevation_m,
        )
        if previous_snapshot is not None
        else {}
    )
    rows = {day: previous_rows[day] for day in required_dates if day in previous_rows}
    rows.update(new_by_date)
    if len(rows) != len(required_dates) or any(day not in rows for day in required_dates):
        return StoredWeatherResult(daily=new_rows, snapshot=None, summaries=())

    existing_snapshot = WeatherSnapshot.objects.filter(
        cell_key=cell_key,
        assessment_date=assessment_date,
        pipeline_version=pipeline_version,
    ).first()
    if existing_snapshot is not None:
        if existing_snapshot.reference_elevation_m != reference_elevation_m:
            raise WeatherDailyConflictError(
                f"snapshot for {cell_key} {assessment_date} uses another elevation"
            )
        summaries = tuple(existing_snapshot.summaries.order_by("days_ahead"))
        return StoredWeatherResult(daily=new_rows, snapshot=existing_snapshot, summaries=summaries)
    snapshot, summaries = _make_snapshot(
        pipeline_version=pipeline_version,
        cell_key=cell_key,
        assessment_date=assessment_date,
        reference_elevation_m=reference_elevation_m,
        rows=rows,
    )
    return StoredWeatherResult(daily=new_rows, snapshot=snapshot, summaries=summaries)


@transaction.atomic
def store_weather_response(
    response: NormalizedProviderResponse,
    assessment_date: date,
    previous_snapshot: WeatherSnapshot | None = None,
    start: date | None = None,
    end: date | None = None,
) -> StoredWeatherResult:
    """Store one response and atomically create a ready 38-day snapshot.

    The response range is the only range aggregated. An explicitly supplied
    ready snapshot can fill dates outside that range, while a prior forecast is
    never reused through an unrelated daily-row query.
    """
    response_start, response_end = _response_date_range(
        response=response,
        start=start,
        end=end,
    )
    stored = store_weather_daily_rows(
        response=response,
        start=response_start,
        end=response_end,
    )
    return build_weather_snapshot(
        cell_key=response.location.cell_key,
        assessment_date=assessment_date,
        reference_elevation_m=response.location.elevation_m,
        new_daily_row_ids=(row.id for row in stored),
        previous_snapshot=previous_snapshot,
    )


def retained_snapshot_ids(
    *,
    current_snapshot_id: str,
    previous_snapshot_id: str | None = None,
) -> tuple[str, ...]:
    """Return snapshot IDs that a retention job must keep for one estimate."""
    if not current_snapshot_id:
        raise ValueError("current_snapshot_id must not be empty")
    values = [current_snapshot_id]
    if previous_snapshot_id and previous_snapshot_id != current_snapshot_id:
        values.append(previous_snapshot_id)
    return tuple(values)
