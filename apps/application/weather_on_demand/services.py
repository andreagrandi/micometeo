from __future__ import annotations

import hashlib
import os
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.apps import apps
from django.db import (
    DatabaseError,
    IntegrityError,
    InterfaceError,
    OperationalError,
    connection,
    transaction,
)
from django.db.models import Count, Sum
from django_tasks_db.models import DBTaskResult
from django.utils import timezone

from micometeo.weather.openmeteo import ARCHIVE_URL, FORECAST_URL
from micometeo.weather.policy import PIPELINE_VERSION, HISTORY_DAYS
from weather_requests.eligibility import WeatherCell
from weather_requests.planning import (
    DEFAULT_MODEL,
    MAX_LOCATIONS,
    combine_request_specs,
    plan_current_weather_requests,
    request_compatibility_key,
)
from weather_requests.provider import (
    PendingRequestError,
    PermanentProviderError,
    ProviderResult,
    ResponseValidationError,
    WeatherProvider,
    get_or_create_request,
    request_spec_from_request,
)
from weather_requests.models import WeatherRequest, WeatherRequestAttempt
from weather_summaries.models import WeatherDaily, WeatherSnapshot
from weather_summaries.provider_adapter import normalized_provider_responses
from weather_summaries.services import (
    WeatherDailyConflictError,
    build_weather_snapshot,
    reusable_previous_daily_rows,
    store_weather_daily_rows,
    store_weather_response,
)

from .models import (
    WeatherCleanupJob,
    WeatherFetch,
    WeatherFetchBatch,
    WeatherFetchPart,
    WeatherVisitorReservation,
    WeatherVisitorWindow,
)


ROME = ZoneInfo("Europe/Rome")
VISITOR_WINDOW = timedelta(seconds=60)
VISITOR_CELL_LIMIT = 100
DEFAULT_WAIT_SECONDS = 3.0
RETRY_DELAY = timedelta(minutes=2)
WEATHER_FETCH_TASK_PATH = "weather_on_demand.tasks.weather_fetch_task"
WEATHER_CLEANUP_TASK_PATH = "weather_on_demand.tasks.weather_cleanup_task"
_ESTIMATE_CALLBACK: Callable[..., Any] | None = None
_CLEANUP_CALLBACK: Callable[..., Any] | None = None


class WeatherOnDemandError(RuntimeError):
    """Report an invalid or incomplete on-demand weather operation."""


@dataclass(frozen=True)
class CellWeatherResult:
    """Describe one cell using current or previous dated weather."""

    cell_key: str
    state: str
    assessment_date: date | None
    fetched_at: datetime | None
    source: str | None
    snapshot_id: str | None
    reason_code: str
    full_reason: str

    @property
    def status(self) -> str:
        """Return the public state name."""
        return self.state

    def as_dict(self) -> dict[str, Any]:
        """Return the result in the API response shape."""
        return {
            "cell_key": self.cell_key,
            "state": self.state,
            "status": self.state,
            "assessment_date": (
                self.assessment_date.isoformat() if self.assessment_date else None
            ),
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "source": self.source,
            "snapshot_id": self.snapshot_id,
            "reason_code": self.reason_code,
            "full_reason": self.full_reason,
        }


@dataclass(frozen=True)
class WeatherLookupResult:
    """Return one dated result for every requested weather cell."""

    assessment_date: date
    cells: tuple[CellWeatherResult, ...]

    @property
    def by_cell(self) -> dict[str, CellWeatherResult]:
        """Return results indexed by weather cell key."""
        return {item.cell_key: item for item in self.cells}

    def __getitem__(self, cell_key: str) -> CellWeatherResult:
        return self.by_cell[cell_key]

    def as_dict(self) -> dict[str, Any]:
        """Return the public response shape."""
        return {
            "assessment_date": self.assessment_date.isoformat(),
            "cells": [item.as_dict() for item in self.cells],
        }


def _clock_now(clock: Callable[[], datetime] | None = None) -> datetime:
    value = clock() if clock is not None else timezone.now()
    if not isinstance(value, datetime):
        raise TypeError("The weather clock must return a datetime.")
    if timezone.is_naive(value):
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def italian_assessment_date(*, clock: Callable[[], datetime] | None = None) -> date:
    """Return today's date at the Europe/Rome boundary."""
    return _clock_now(clock).astimezone(ROME).date()


def opaque_visitor_hash(*, visitor_id: str | bytes | None) -> str:
    """Hash a visitor identifier without storing its original value."""
    value = "anonymous" if visitor_id is None else str(visitor_id)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def configure_estimate_callback(callback: Callable[..., Any] | None) -> None:
    """Set the optional callback invoked after a snapshot commits."""
    global _ESTIMATE_CALLBACK
    _ESTIMATE_CALLBACK = callback


set_estimate_callback = configure_estimate_callback


def configure_cleanup_callback(callback: Callable[..., Any] | None) -> None:
    """Set the optional estimate-retention callback used by cleanup."""
    global _CLEANUP_CALLBACK
    _CLEANUP_CALLBACK = callback


set_cleanup_callback = configure_cleanup_callback


def _notify_snapshot_ready(
    *,
    snapshot_id: uuid.UUID | str,
    cell_key: str,
    assessment_date: date,
    forest_build_version: str,
) -> None:
    callback = _ESTIMATE_CALLBACK
    if callback is None:
        return
    try:
        callback(
            snapshot_id=str(snapshot_id),
            cell_key=cell_key,
            assessment_date=assessment_date,
            forest_build_version=forest_build_version,
        )
    except Exception:
        return


def _dispatch_estimate_callback(*, fetch_id: uuid.UUID) -> None:
    """Run the optional estimate callback and retain failures for retry."""
    callback = _ESTIMATE_CALLBACK
    if callback is None:
        return
    with transaction.atomic():
        fetch = (
            WeatherFetch.objects.select_for_update()
            .filter(id=fetch_id, status=WeatherFetch.Status.COMPLETED, snapshot__isnull=False)
            .first()
        )
        if fetch is None or fetch.estimate_callback_status in {"completed", "running"}:
            return
        now = timezone.now()
        fetch.estimate_callback_status = "running"
        fetch.estimate_callback_started_at = now
        fetch.estimate_callback_attempts += 1
        fetch.save(
            update_fields=[
                "estimate_callback_status",
                "estimate_callback_started_at",
                "estimate_callback_attempts",
                "updated_at",
            ]
        )
    request = WeatherRequest.objects.filter(id=fetch.request_id).first()
    try:
        result = callback(
            snapshot_id=str(fetch.snapshot_id),
            cell_key=fetch.cell_key,
            assessment_date=fetch.assessment_date,
            forest_build_version=(request.forest_build_version if request else ""),
        )
        if (
            result is not None
            and getattr(result, "state", None) == "waiting"
            and getattr(result, "task_id", None) is None
        ):
            raise RuntimeError("The estimate callback returned a waiting task without a queue ID.")
    except Exception as exc:
        WeatherFetch.objects.filter(id=fetch.id).update(
            estimate_callback_status="pending",
            estimate_callback_retry_at=now + RETRY_DELAY,
            estimate_callback_started_at=None,
            estimate_callback_reason=str(exc),
            updated_at=timezone.now(),
        )
        return
    WeatherFetch.objects.filter(id=fetch.id).update(
        estimate_callback_status="completed",
        estimate_callback_retry_at=None,
        estimate_callback_started_at=None,
        estimate_callback_reason="",
        updated_at=timezone.now(),
    )


def notify_snapshot_ready(
    *,
    snapshot_id: uuid.UUID | str,
    cell_key: str,
    assessment_date: date,
    forest_build_version: str = "",
) -> None:
    """Invoke the configured estimate adapter after snapshot storage."""
    _notify_snapshot_ready(
        snapshot_id=snapshot_id,
        cell_key=cell_key,
        assessment_date=assessment_date,
        forest_build_version=forest_build_version,
    )


def weather_fetch_lock_key(*, cell_key: str, assessment_date: date) -> int:
    """Return a signed advisory lock key for one cell and Italian date."""
    value = f"weather-fetch:{cell_key}:{assessment_date.isoformat()}"
    return int.from_bytes(
        hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest(),
        byteorder="big",
        signed=True,
    )


def weather_task_lock_keys(*, batch_id: uuid.UUID | str) -> tuple[str, ...]:
    """Return every advisory key claimed by one weather queue task."""
    parsed_batch_id = uuid.UUID(str(batch_id))
    batch = (
        WeatherFetchBatch.objects.filter(id=parsed_batch_id)
        .prefetch_related("fetches", "parts__fetch")
        .first()
    )
    if batch is None:
        return ()
    fetches = {fetch.id: fetch for fetch in batch.fetches.all()}
    fetches.update({part.fetch.id: part.fetch for part in batch.parts.all()})
    return tuple(
        [batch.logical_key]
        + [
            f"weather-fetch:{fetch.cell_key}:{fetch.assessment_date.isoformat()}"
            for fetch in sorted(fetches.values(), key=lambda item: item.cell_key)
        ]
    )


def weather_cleanup_task_lock_keys(*, job_id: uuid.UUID | str) -> tuple[str, ...]:
    """Return the advisory key claimed by one cleanup queue task."""
    job = WeatherCleanupJob.objects.filter(id=uuid.UUID(str(job_id))).first()
    return (job.logical_key,) if job is not None else ()


@contextmanager
def weather_cell_locks(
    *,
    keys: Iterable[tuple[str, date]],
    wait: bool,
) -> Iterator[bool]:
    """Hold sorted PostgreSQL advisory locks for weather cell dates."""
    values = sorted({(str(cell), day) for cell, day in keys})
    if not values:
        yield True
        return
    lock_ids = [
        weather_fetch_lock_key(cell_key=cell, assessment_date=day)
        for cell, day in values
    ]
    acquired: list[int] = []
    try:
        with connection.cursor() as cursor:
            for lock_id in lock_ids:
                if wait:
                    cursor.execute("SELECT pg_advisory_lock(%s)", [lock_id])
                    locked = True
                else:
                    cursor.execute("SELECT pg_try_advisory_lock(%s)", [lock_id])
                    locked = bool(cursor.fetchone()[0])
                if not locked:
                    break
                acquired.append(lock_id)
        if len(acquired) != len(lock_ids):
            if acquired:
                with connection.cursor() as cursor:
                    for lock_id in reversed(acquired):
                        cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_id])
            yield False
            return
        yield True
    except DatabaseError:
        if connection.vendor != "postgresql":
            yield True
            return
        raise
    finally:
        if acquired and len(acquired) == len(lock_ids):
            with connection.cursor() as cursor:
                for lock_id in reversed(acquired):
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_id])


def _previous_snapshot(*, cell_key: str, assessment_date: date) -> WeatherSnapshot | None:
    return (
        WeatherSnapshot.objects.filter(
            cell_key=cell_key,
            assessment_date__lt=assessment_date,
            status=WeatherSnapshot.Status.READY,
            pipeline_version=PIPELINE_VERSION,
        )
        .order_by("-assessment_date", "-created_at")
        .first()
    )


def _snapshot_for_date(*, cell_key: str, assessment_date: date) -> WeatherSnapshot | None:
    return WeatherSnapshot.objects.filter(
        cell_key=cell_key,
        assessment_date=assessment_date,
        status=WeatherSnapshot.Status.READY,
        pipeline_version=PIPELINE_VERSION,
    ).first()


def _stored_dates(*, snapshot: WeatherSnapshot | None) -> set[date]:
    if snapshot is None:
        return set()
    return set(snapshot.days.values_list("date", flat=True))


def _ensure_visitor_window(*, visitor_hash: str, now: datetime) -> WeatherVisitorWindow:
    try:
        return WeatherVisitorWindow.objects.select_for_update().get(
            visitor_hash=visitor_hash
        )
    except WeatherVisitorWindow.DoesNotExist:
        try:
            WeatherVisitorWindow.objects.create(
                visitor_hash=visitor_hash,
                window_started_at=now,
                new_cell_count=0,
            )
        except IntegrityError:
            pass
        return WeatherVisitorWindow.objects.select_for_update().get(
            visitor_hash=visitor_hash
        )


def _reserve_visitor_slots(
    *,
    visitor_hash: str,
    cell_keys: Sequence[str],
    assessment_date: date,
    now: datetime,
) -> set[str]:
    if not cell_keys:
        return set()
    with transaction.atomic():
        window = _ensure_visitor_window(visitor_hash=visitor_hash, now=now)
        cutoff = now - VISITOR_WINDOW
        WeatherVisitorReservation.objects.filter(
            visitor_hash=visitor_hash,
            reserved_at__lte=cutoff,
        ).delete()
        active_count = WeatherVisitorReservation.objects.filter(
            visitor_hash=visitor_hash,
            reserved_at__gt=cutoff,
        ).count()
        available = max(0, VISITOR_CELL_LIMIT - active_count)
        accepted_keys = set(sorted(cell_keys)[:available])
        WeatherVisitorReservation.objects.bulk_create(
            [
                WeatherVisitorReservation(
                    visitor_hash=visitor_hash,
                    cell_key=cell_key,
                    assessment_date=assessment_date,
                    reserved_at=now,
                )
                for cell_key in sorted(accepted_keys)
            ]
        )
        active_reservations = WeatherVisitorReservation.objects.filter(
            visitor_hash=visitor_hash,
            reserved_at__gt=cutoff,
        )
        active_count = active_reservations.count()
        oldest = active_reservations.order_by("reserved_at").values_list(
            "reserved_at", flat=True
        ).first()
        window.window_started_at = oldest or now
        window.new_cell_count = active_count
        window.save(update_fields=["window_started_at", "new_cell_count", "updated_at"])
        return accepted_keys


def _ensure_fetch(
    *,
    cell_key: str,
    assessment_date: date,
    previous_snapshot: WeatherSnapshot | None,
    visitor_hash: str,
    now: datetime,
) -> tuple[WeatherFetch, bool]:
    fetch = (
        WeatherFetch.objects.select_for_update()
        .filter(cell_key=cell_key, assessment_date=assessment_date, pipeline_version=PIPELINE_VERSION)
        .first()
    )
    if fetch is None:
        try:
            with transaction.atomic():
                fetch = WeatherFetch.objects.create(
                    pipeline_version=PIPELINE_VERSION,
                    cell_key=cell_key,
                    assessment_date=assessment_date,
                    previous_snapshot=previous_snapshot,
                    visitor_hash=visitor_hash,
                    reason_code="fetch_pending",
                    first_requested_at=now,
                )
            return fetch, True
        except IntegrityError:
            fetch = WeatherFetch.objects.select_for_update().get(
                pipeline_version=PIPELINE_VERSION,
                cell_key=cell_key,
                assessment_date=assessment_date,
            )
    return fetch, False


def _mark_visitor_limited(
    *,
    fetch: WeatherFetch,
    visitor_hash: str,
    now: datetime,
) -> None:
    fetch.status = WeatherFetch.Status.PENDING
    fetch.reason_code = "visitor_limit"
    fetch.full_reason = "This visitor reached the limit of 100 new weather cells in 60 seconds."
    fetch.retry_at = now + VISITOR_WINDOW
    fetch.visitor_hash = visitor_hash
    fetch.save(
        update_fields=[
            "status",
            "reason_code",
            "full_reason",
            "retry_at",
            "visitor_hash",
            "updated_at",
        ]
    )


def _plan_batches(
    *,
    cells: Sequence[WeatherCell],
    assessment_date: date,
    visitor_hash: str,
    now: datetime,
    model: str,
    forest_build_version: str,
    options: Mapping[str, str] | None,
) -> tuple[WeatherFetchBatch, ...]:
    cells_by_key = {cell.key: cell for cell in cells}
    available: list[tuple[WeatherCell, WeatherFetch, Any]] = []
    pending_batches: dict[uuid.UUID, WeatherFetchBatch] = {}
    endpoint = os.environ.get("MICOMETEO_WEATHER_ENDPOINT", FORECAST_URL)
    with transaction.atomic():
        fetches: dict[str, WeatherFetch] = {}
        trigger_keys: set[str] = set()
        for cell in sorted(cells, key=lambda item: item.key):
            current_snapshot = _snapshot_for_date(
                cell_key=cell.key,
                assessment_date=assessment_date,
            )
            if current_snapshot is not None:
                with weather_cell_locks(
                    keys=[(cell.key, assessment_date)],
                    wait=True,
                ):
                    fetch, _created = _ensure_fetch(
                        cell_key=cell.key,
                        assessment_date=assessment_date,
                        previous_snapshot=None,
                        visitor_hash=visitor_hash,
                        now=now,
                    )
                if (
                    fetch.status != WeatherFetch.Status.COMPLETED
                    or fetch.snapshot_id != current_snapshot.id
                ):
                    fetch.status = WeatherFetch.Status.COMPLETED
                    fetch.snapshot = current_snapshot
                    fetch.fetched_at = current_snapshot.latest_retrieval
                    fetch.completed_at = now
                    fetch.reason_code = "ready"
                    fetch.full_reason = ""
                    fetch.save(
                        update_fields=[
                            "status",
                            "snapshot",
                            "fetched_at",
                            "completed_at",
                            "reason_code",
                            "full_reason",
                            "updated_at",
                        ]
                    )
                transaction.on_commit(
                    lambda fetch_id=fetch.id: _dispatch_estimate_callback(fetch_id=fetch_id)
                )
                continue
            previous = _previous_snapshot(
                cell_key=cell.key,
                assessment_date=assessment_date,
            )
            with weather_cell_locks(
                keys=[(cell.key, assessment_date)],
                wait=False,
            ) as acquired:
                if not acquired:
                    continue
                fetch, _created = _ensure_fetch(
                    cell_key=cell.key,
                    assessment_date=assessment_date,
                    previous_snapshot=previous,
                    visitor_hash=visitor_hash,
                    now=now,
                )
            fetches[cell.key] = fetch
            if fetch.status == WeatherFetch.Status.COMPLETED and fetch.snapshot_id:
                continue
            if fetch.status == WeatherFetch.Status.FAILED:
                continue
            active_parts = list(
                WeatherFetchPart.objects.filter(
                    fetch=fetch,
                    status__in=[
                        WeatherFetchPart.Status.PENDING,
                        WeatherFetchPart.Status.RUNNING,
                    ],
                    batch__status__in=[
                        WeatherFetchBatch.Status.PENDING,
                        WeatherFetchBatch.Status.RUNNING,
                    ],
                ).select_related("batch")
            )
            for part in active_parts:
                if part.batch_id is not None:
                    pending_batches[part.batch_id] = part.batch
            if active_parts:
                continue
            if fetch.reason_code == "visitor_limit" and fetch.visitor_hash == visitor_hash:
                if fetch.retry_at is None or fetch.retry_at > now:
                    continue
            if fetch.status == WeatherFetch.Status.RUNNING:
                continue
            if fetch.retry_at is None or fetch.retry_at <= now:
                trigger_keys.add(cell.key)

        accepted_keys = _reserve_visitor_slots(
            visitor_hash=visitor_hash,
            cell_keys=tuple(trigger_keys),
            assessment_date=assessment_date,
            now=now,
        )
        for cell_key, fetch in fetches.items():
            if fetch.batch_id is not None or fetch.status == WeatherFetch.Status.RUNNING:
                continue
            if (
                fetch.reason_code == "visitor_limit"
                and fetch.visitor_hash == visitor_hash
                and (fetch.retry_at is None or fetch.retry_at > now)
            ):
                continue
            is_new = cell_key in trigger_keys
            if not is_new:
                continue
            if is_new and cell_key not in accepted_keys:
                _mark_visitor_limited(fetch=fetch, visitor_hash=visitor_hash, now=now)
                continue
            previous = fetch.previous_snapshot
            completed_dates: set[date] = set()
            if previous is not None:
                completed_dates.update(
                    reusable_previous_daily_rows(
                        previous_snapshot=previous,
                        assessment_date=assessment_date,
                        cell_key=fetch.cell_key,
                        reference_elevation_m=previous.reference_elevation_m,
                    )
                )
            completed_part_ids = list(
                WeatherFetchPart.objects.filter(
                    fetch=fetch,
                    status=WeatherFetchPart.Status.COMPLETED,
                ).values_list("daily_ids", flat=True)
            )
            daily_ids = {
                str(row_id)
                for part_ids in completed_part_ids
                for row_id in (part_ids or [])
            }
            if daily_ids:
                completed_dates.update(
                    WeatherDaily.objects.filter(id__in=daily_ids).values_list("date", flat=True)
                )
            specs = plan_current_weather_requests(
                locations=[cells_by_key[cell_key]],
                assessment_date=assessment_date,
                completed_dates=completed_dates,
                model=model,
                endpoint=endpoint,
                history_endpoint=os.environ.get("MICOMETEO_WEATHER_HISTORY_ENDPOINT", ARCHIVE_URL),
                options=options,
                forest_build_version=forest_build_version,
            )
            for spec in specs:
                requested_dates = {
                    spec.start_date + timedelta(days=offset)
                    for offset in range((spec.end_date - spec.start_date).days + 1)
                }
                if requested_dates.issubset(completed_dates):
                    continue
                available.append((cells_by_key[cell_key], fetch, spec))

        groups: dict[tuple[Any, ...], list[tuple[WeatherCell, WeatherFetch, Any]]] = defaultdict(list)
        for item in available:
            groups[request_compatibility_key(spec=item[2])].append(item)
        for group in groups.values():
            for offset in range(0, len(group), MAX_LOCATIONS):
                chunk = group[offset : offset + MAX_LOCATIONS]
                combined = combine_request_specs(specs=[item[2] for item in chunk])
                request = get_or_create_request(
                    spec=combined,
                    provenance={"source": "weather_on_demand", "assessment_date": assessment_date.isoformat()},
                )
                logical_key = f"weather-fetch:{assessment_date.isoformat()}:{combined.digest}"
                batch, _created = WeatherFetchBatch.objects.get_or_create(
                    logical_key=logical_key,
                    defaults={
                        "assessment_date": assessment_date,
                        "request": request,
                        "canonical_spec": combined.as_dict(),
                    },
                )
                if batch.request_id != request.id:
                    raise WeatherOnDemandError("A weather batch logical key has another request.")
                for _cell, fetch, _spec in chunk:
                    if fetch.batch_id is None:
                        fetch.batch = batch
                    fetch.request = request
                    fetch.status = WeatherFetch.Status.PENDING
                    fetch.reason_code = "fetch_pending"
                    fetch.full_reason = ""
                    fetch.retry_at = None
                    fetch.save(
                        update_fields=[
                            "batch",
                            "request",
                            "status",
                            "reason_code",
                            "full_reason",
                            "retry_at",
                            "updated_at",
                        ]
                    )
                    part, _part_created = WeatherFetchPart.objects.get_or_create(
                        fetch=fetch,
                        start_date=combined.start_date,
                        end_date=combined.end_date,
                        defaults={
                            "batch": batch,
                            "request": request,
                            "reason_code": "fetch_pending",
                        },
                    )
                    if part.batch_id != batch.id or part.request_id != request.id:
                        raise WeatherOnDemandError(
                            "A weather fetch part has another durable batch or request."
                        )
                    if part.status in {
                        WeatherFetchPart.Status.FAILED,
                        WeatherFetchPart.Status.PENDING,
                    }:
                        part.status = WeatherFetchPart.Status.PENDING
                        part.retry_at = None
                        part.reason_code = "fetch_pending"
                        part.full_reason = ""
                        part.save(
                            update_fields=[
                                "status",
                                "retry_at",
                                "reason_code",
                                "full_reason",
                                "updated_at",
                            ]
                        )
                pending_batches[batch.id] = batch
    return tuple(pending_batches.values())


def _enqueue_batch(*, batch_id: uuid.UUID, run_after: datetime | None = None) -> uuid.UUID | None:
    from .tasks import weather_fetch_task

    try:
        task = weather_fetch_task.using(run_after=run_after) if run_after else weather_fetch_task
        with transaction.atomic():
            batch = WeatherFetchBatch.objects.select_for_update().get(id=batch_id)
            if _queue_task_is_active(task_id=batch.task_id):
                return batch.task_id
            task_result = task.enqueue(batch_id=str(batch_id))
            task_id = uuid.UUID(str(task_result.id))
            batch.task_id = task_id
            batch.save(update_fields=["task_id", "updated_at"])
            return task_id
    except Exception as exc:
        WeatherFetchBatch.objects.filter(id=batch_id).update(
            task_id=None,
            status=WeatherFetchBatch.Status.PENDING,
            reason_code="queue_failure",
            full_reason=str(exc),
            retry_at=timezone.now() + RETRY_DELAY,
            updated_at=timezone.now(),
        )
        return None


def _schedule_batch(*, batch: WeatherFetchBatch, run_after: datetime | None = None) -> None:
    if run_after is None and batch.retry_at is not None and batch.retry_at > timezone.now():
        run_after = batch.retry_at
    if _queue_task_is_active(task_id=batch.task_id):
        return
    transaction.on_commit(
        lambda: _enqueue_batch(batch_id=batch.id, run_after=run_after)
    )


def _queue_task_is_active(
    *,
    task_id: uuid.UUID | None,
    logical_keys: Iterable[str] = (),
) -> bool:
    """Return whether a queued task is live or still waiting to run."""
    if task_id is None:
        return False
    task_result = DBTaskResult.objects.filter(id=task_id).first()
    if task_result is None or task_result.status not in {"READY", "RUNNING"}:
        return False
    if task_result.status == "READY":
        return True
    keys = tuple(logical_keys)
    if not keys:
        return True
    from background_jobs.services import logical_job_locks

    with logical_job_locks(logical_keys=keys, wait=False) as acquired:
        if not acquired:
            return True
        with transaction.atomic():
            current = DBTaskResult.objects.select_for_update().filter(id=task_id).first()
            if current is not None and current.status == "RUNNING":
                current.set_failed(RuntimeError("The worker stopped before the task completed."))
    return False


def _start_injected_batch(
    *,
    batch_id: uuid.UUID,
    transport: Callable[..., Any] | None,
    clock: Callable[[], datetime] | None,
    provider: WeatherProvider | None,
) -> None:
    def run() -> None:
        from django.db import close_old_connections

        close_old_connections()
        try:
            batch = WeatherFetchBatch.objects.get(id=batch_id)
            part_keys = list(
                batch.parts.values_list("fetch__cell_key", "fetch__assessment_date")
            )
            if not part_keys:
                part_keys = list(
                    batch.fetches.values_list("cell_key", "assessment_date")
                )
            with weather_cell_locks(keys=part_keys, wait=True):
                process_weather_fetch_batch(
                    batch_id=batch_id,
                    transport=transport,
                    clock=clock,
                    provider=provider,
                )
        finally:
            close_old_connections()

    threading.Thread(target=run, name="weather-on-demand-test-fetch", daemon=True).start()


def _claim_batch(*, batch_id: uuid.UUID, now: datetime) -> WeatherFetchBatch | None:
    with transaction.atomic():
        batch = (
            WeatherFetchBatch.objects.select_for_update()
            .select_related("request")
            .filter(id=batch_id)
            .first()
        )
        if batch is None or batch.status in {
            WeatherFetchBatch.Status.COMPLETED,
            WeatherFetchBatch.Status.FAILED,
        }:
            return None
        if batch.status == WeatherFetchBatch.Status.RUNNING:
            return None
        if batch.retry_at is not None and batch.retry_at > now:
            return None
        batch.status = WeatherFetchBatch.Status.RUNNING
        batch.started_at = now
        batch.reason_code = "fetch_running"
        batch.full_reason = ""
        batch.save(
            update_fields=[
                "status",
                "started_at",
                "reason_code",
                "full_reason",
                "updated_at",
            ]
        )
        batch.fetches.filter(status=WeatherFetch.Status.PENDING).update(
            status=WeatherFetch.Status.RUNNING,
            started_at=now,
            reason_code="fetch_running",
            full_reason="",
            updated_at=now,
        )
        WeatherFetch.objects.filter(
            id__in=batch.parts.values_list("fetch_id", flat=True),
            status=WeatherFetch.Status.PENDING,
        ).update(
            status=WeatherFetch.Status.RUNNING,
            started_at=now,
            reason_code="fetch_running",
            full_reason="",
            updated_at=now,
        )
        batch.parts.filter(status=WeatherFetchPart.Status.PENDING).update(
            status=WeatherFetchPart.Status.RUNNING,
            started_at=now,
            reason_code="fetch_running",
            full_reason="",
            updated_at=now,
        )
        return batch


def _retry_reason(*, error: BaseException, status: int | None = None) -> str:
    if status == 429:
        return "provider_refused"
    if isinstance(error, PendingRequestError):
        return "provider_unavailable"
    if isinstance(error, (PermanentProviderError, ResponseValidationError)):
        return "provider_refused"
    return "storage_recovery"


def _is_transient_storage_error(*, error: BaseException) -> bool:
    """Return whether an unexpected storage error can be retried safely."""
    return isinstance(error, (OperationalError, InterfaceError, InterruptedError, TimeoutError))


def _pending_reason(*, batch: WeatherFetchBatch, error: PendingRequestError) -> str:
    """Map a pending provider result to a stable visitor-facing reason."""
    if "quota" in str(error).lower():
        return "quota_exhausted"
    attempt = (
        WeatherRequestAttempt.objects.filter(request_id=batch.request_id)
        .order_by("-attempt_number")
        .first()
    )
    if attempt is not None and attempt.http_status == 429:
        return "provider_refused"
    return "provider_unavailable"


def _batch_pending(
    *,
    batch_id: uuid.UUID,
    reason_code: str,
    full_reason: str,
    retry_at: datetime,
    now: datetime,
) -> None:
    with transaction.atomic():
        batch = WeatherFetchBatch.objects.select_for_update().get(id=batch_id)
        batch.status = WeatherFetchBatch.Status.PENDING
        batch.task_id = None
        batch.retry_at = retry_at
        batch.reason_code = reason_code
        batch.full_reason = full_reason
        batch.save(
            update_fields=[
                "status",
                "task_id",
                "retry_at",
                "reason_code",
                "full_reason",
                "updated_at",
            ]
        )
        batch.fetches.filter(status=WeatherFetch.Status.RUNNING).update(
            status=WeatherFetch.Status.PENDING,
            retry_at=retry_at,
            reason_code=reason_code,
            full_reason=full_reason,
            updated_at=now,
        )
        WeatherFetch.objects.filter(
            id__in=batch.parts.values_list("fetch_id", flat=True),
            status=WeatherFetch.Status.RUNNING,
        ).update(
            status=WeatherFetch.Status.PENDING,
            retry_at=retry_at,
            reason_code=reason_code,
            full_reason=full_reason,
            updated_at=now,
        )
        batch.parts.filter(status=WeatherFetchPart.Status.RUNNING).update(
            status=WeatherFetchPart.Status.PENDING,
            retry_at=retry_at,
            reason_code=reason_code,
            full_reason=full_reason,
            updated_at=now,
        )
    _schedule_batch(batch=batch, run_after=retry_at)


def _related_weather_scope(
    *,
    batch_id: uuid.UUID,
) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    """Return batches and fetches connected through multipart siblings."""
    batch_ids = {batch_id}
    fetch_ids: set[uuid.UUID] = set()
    while True:
        previous_batch_ids = set(batch_ids)
        previous_fetch_ids = set(fetch_ids)
        fetch_ids.update(
            WeatherFetch.objects.filter(batch_id__in=batch_ids).values_list("id", flat=True)
        )
        fetch_ids.update(
            WeatherFetchPart.objects.filter(batch_id__in=batch_ids).values_list(
                "fetch_id", flat=True
            )
        )
        batch_ids.update(
            WeatherFetch.objects.filter(
                id__in=fetch_ids,
                batch_id__isnull=False,
            ).values_list("batch_id", flat=True)
        )
        batch_ids.update(
            WeatherFetchPart.objects.filter(
                fetch_id__in=fetch_ids,
                batch_id__isnull=False,
            ).values_list("batch_id", flat=True)
        )
        if batch_ids == previous_batch_ids and fetch_ids == previous_fetch_ids:
            return batch_ids, fetch_ids


def _batch_failed(
    *,
    batch_id: uuid.UUID,
    reason_code: str,
    full_reason: str,
    now: datetime,
) -> None:
    """Stop a batch after a permanent provider or validation failure."""
    with transaction.atomic():
        batch = WeatherFetchBatch.objects.get(id=batch_id)
        batch_ids, fetch_ids = _related_weather_scope(batch_id=batch.id)
        locked_batches = list(
            WeatherFetchBatch.objects.select_for_update()
            .filter(id__in=batch_ids)
            .order_by("id")
        )
        if not any(locked.id == batch_id for locked in locked_batches):
            return
        list(
            WeatherFetch.objects.select_for_update()
            .filter(id__in=fetch_ids)
            .order_by("id")
        )
        list(
            WeatherFetchPart.objects.select_for_update()
            .filter(fetch_id__in=fetch_ids)
            .order_by("id")
        )
        WeatherFetchBatch.objects.filter(
            id__in=batch_ids,
            status__in=[WeatherFetchBatch.Status.PENDING, WeatherFetchBatch.Status.RUNNING],
        ).update(
            status=WeatherFetchBatch.Status.FAILED,
            task_id=None,
            retry_at=None,
            reason_code=reason_code,
            full_reason=full_reason,
            updated_at=now,
        )
        WeatherFetch.objects.filter(
            id__in=fetch_ids,
            status__in=[WeatherFetch.Status.PENDING, WeatherFetch.Status.RUNNING],
        ).update(
            status=WeatherFetch.Status.FAILED,
            retry_at=None,
            reason_code=reason_code,
            full_reason=full_reason,
            updated_at=now,
        )
        WeatherFetchPart.objects.filter(
            fetch_id__in=fetch_ids,
            status__in=[WeatherFetchPart.Status.PENDING, WeatherFetchPart.Status.RUNNING],
        ).update(
            status=WeatherFetchPart.Status.FAILED,
            retry_at=None,
            reason_code=reason_code,
            full_reason=full_reason,
            updated_at=now,
        )


def reopen_weather_fetch(*, batch_id: uuid.UUID | str, now: datetime | None = None) -> WeatherFetchBatch:
    """Explicitly reopen one permanently failed provider batch."""
    current = _clock_now(lambda: now) if now is not None else _clock_now()
    parsed_batch_id = uuid.UUID(str(batch_id))
    reopened_batch_ids: set[uuid.UUID] = set()
    with transaction.atomic():
        batch = WeatherFetchBatch.objects.get(id=parsed_batch_id)
        if batch.status != WeatherFetchBatch.Status.FAILED:
            raise WeatherOnDemandError("Only a failed weather batch can be reopened.")
        batch_ids, fetch_ids = _related_weather_scope(batch_id=batch.id)
        locked_batches = list(
            WeatherFetchBatch.objects.select_for_update()
            .filter(id__in=batch_ids)
            .order_by("id")
        )
        batch = next(
            (locked for locked in locked_batches if locked.id == parsed_batch_id),
            None,
        )
        if batch is None or batch.status != WeatherFetchBatch.Status.FAILED:
            raise WeatherOnDemandError("Only a failed weather batch can be reopened.")
        list(
            WeatherFetch.objects.select_for_update()
            .filter(id__in=fetch_ids)
            .order_by("id")
        )
        list(
            WeatherFetchPart.objects.select_for_update()
            .filter(fetch_id__in=fetch_ids)
            .order_by("id")
        )
        request_ids = WeatherFetchBatch.objects.filter(
            id__in=batch_ids,
        ).values_list("request_id", flat=True)
        WeatherRequest.objects.filter(
            id__in=request_ids,
            status=WeatherRequest.Status.FAILED,
        ).update(
            status=WeatherRequest.Status.PENDING,
            retry_at=current,
            failed_at=None,
            latest_provider_message="",
            updated_at=current,
        )
        reopened_batch_ids.update(
            WeatherFetchBatch.objects.filter(
                id__in=batch_ids,
                status__in=[
                    WeatherFetchBatch.Status.FAILED,
                    WeatherFetchBatch.Status.PENDING,
                    WeatherFetchBatch.Status.RUNNING,
                ],
            ).values_list("id", flat=True)
        )
        WeatherFetchBatch.objects.filter(id__in=reopened_batch_ids).update(
            status=WeatherFetchBatch.Status.PENDING,
            task_id=None,
            retry_at=current,
            reason_code="fetch_reopened",
            full_reason="The failed weather batch was explicitly reopened.",
            updated_at=current,
        )
        WeatherFetch.objects.filter(
            id__in=fetch_ids,
            status__in=[
                WeatherFetch.Status.FAILED,
                WeatherFetch.Status.PENDING,
                WeatherFetch.Status.RUNNING,
            ],
        ).update(
            status=WeatherFetch.Status.PENDING,
            retry_at=current,
            reason_code="fetch_reopened",
            full_reason="The failed weather batch was explicitly reopened.",
            updated_at=current,
        )
        WeatherFetchPart.objects.filter(
            fetch_id__in=fetch_ids,
            status__in=[
                WeatherFetchPart.Status.FAILED,
                WeatherFetchPart.Status.PENDING,
                WeatherFetchPart.Status.RUNNING,
            ],
        ).update(
            status=WeatherFetchPart.Status.PENDING,
            retry_at=current,
            reason_code="fetch_reopened",
            full_reason="The failed weather batch was explicitly reopened.",
            updated_at=current,
        )
    for reopened_batch in WeatherFetchBatch.objects.filter(id__in=reopened_batch_ids):
        _schedule_batch(batch=reopened_batch, run_after=current)
    batch = WeatherFetchBatch.objects.get(id=parsed_batch_id)
    batch.refresh_from_db()
    return batch


def _store_batch(
    *,
    batch_id: uuid.UUID,
    result: ProviderResult,
    now: datetime,
) -> None:
    responses = normalized_provider_responses(result=result)
    ready_fetch_ids: list[uuid.UUID] = []
    with transaction.atomic():
        batch = (
            WeatherFetchBatch.objects.select_for_update()
            .select_related("request")
            .get(id=batch_id)
        )
        parts = list(
            batch.parts.select_for_update()
            .select_related("fetch")
            .order_by("fetch__cell_key", "start_date", "end_date")
        )
        if not parts:
            fetches = list(batch.fetches.select_for_update().order_by("cell_key"))
            if len(fetches) != len(responses):
                raise WeatherOnDemandError("The provider answer did not match the fetch batch.")
            for fetch, response in zip(fetches, responses, strict=True):
                stored = store_weather_response(
                    response=response,
                    assessment_date=fetch.assessment_date,
                    previous_snapshot=fetch.previous_snapshot,
                    start=result.spec.start_date,
                    end=result.spec.end_date,
                )
                if stored.snapshot is None:
                    raise WeatherOnDemandError(
                        f"The provider answer did not complete the weather snapshot for {fetch.cell_key}."
                    )
                fetch.status = WeatherFetch.Status.COMPLETED
                fetch.snapshot = stored.snapshot
                fetch.fetched_at = stored.snapshot.latest_retrieval
                fetch.completed_at = now
                fetch.retry_at = None
                fetch.reason_code = "ready"
                fetch.full_reason = ""
                fetch.save(
                    update_fields=[
                        "status",
                        "snapshot",
                        "fetched_at",
                        "completed_at",
                        "retry_at",
                        "reason_code",
                        "full_reason",
                        "updated_at",
                    ]
                )
                ready_fetch_ids.append(fetch.id)
        elif len(parts) != len(responses):
            raise WeatherOnDemandError("The provider answer did not match the fetch batch.")
        else:
            responses_by_cell = {
                response.location.cell_key: response for response in responses
            }
            for part in parts:
                response = responses_by_cell.get(part.fetch.cell_key)
                if response is None:
                    raise WeatherOnDemandError(
                        f"The provider answer omitted {part.fetch.cell_key}."
                    )
                if (
                    response.requested_start != part.start_date
                    or response.requested_end != part.end_date
                ):
                    raise WeatherOnDemandError(
                        f"The provider answer range did not match part {part.id}."
                    )
                if len(parts) == 1 and part.fetch.previous_snapshot_id is None and part.fetch.pipeline_version == 1:
                    stored_result = store_weather_response(
                        response=response,
                        assessment_date=part.fetch.assessment_date,
                        previous_snapshot=None,
                        start=part.start_date,
                        end=part.end_date,
                    )
                    rows = stored_result.daily
                else:
                    rows = store_weather_daily_rows(
                        response=response,
                        start=part.start_date,
                        end=part.end_date,
                    )
                part.daily_ids = [str(row.id) for row in rows]
                part.source_ids = list(dict.fromkeys(row.source_id for row in rows))
                part.source_attempt_ids = list(
                    dict.fromkeys(str(row.attempt_id) for row in rows)
                )
                part.status = WeatherFetchPart.Status.COMPLETED
                part.retry_at = None
                part.completed_at = now
                part.reason_code = "part_stored"
                part.full_reason = ""
                part.save(
                    update_fields=[
                        "daily_ids",
                        "source_ids",
                        "source_attempt_ids",
                        "status",
                        "retry_at",
                        "completed_at",
                        "reason_code",
                        "full_reason",
                        "updated_at",
                    ]
                )

            fetches = {
                fetch.id: fetch
                for fetch in WeatherFetch.objects.select_for_update().filter(
                    id__in={part.fetch_id for part in parts}
                )
            }
            for fetch in fetches.values():
                all_parts = list(
                    WeatherFetchPart.objects.filter(fetch=fetch).order_by("start_date", "end_date")
                )
                if not all_parts or any(
                    part.status != WeatherFetchPart.Status.COMPLETED for part in all_parts
                ):
                    continue
                daily_ids = [
                    row_id
                    for part in all_parts
                    for row_id in (part.daily_ids or [])
                ]
                first_row = (
                    WeatherDaily.objects.filter(id__in=daily_ids, cell_key=fetch.cell_key)
                    .order_by("date", "id")
                    .first()
                )
                if first_row is None:
                    raise WeatherOnDemandError(
                        f"Weather parts for {fetch.cell_key} have no stored daily rows."
                    )
                stored = build_weather_snapshot(
                    pipeline_version=fetch.pipeline_version,
                    cell_key=fetch.cell_key,
                    assessment_date=fetch.assessment_date,
                    reference_elevation_m=first_row.reference_elevation_m,
                    new_daily_row_ids=daily_ids,
                    previous_snapshot=fetch.previous_snapshot,
                )
                if stored.snapshot is None:
                    fetch.status = WeatherFetch.Status.PENDING
                    fetch.retry_at = None
                    fetch.reason_code = "snapshot_incomplete"
                    fetch.full_reason = (
                        "Stored weather parts do not yet cover the full snapshot."
                    )
                    fetch.save(
                        update_fields=[
                            "status",
                            "retry_at",
                            "reason_code",
                            "full_reason",
                            "updated_at",
                        ]
                    )
                    continue
                fetch.status = WeatherFetch.Status.COMPLETED
                fetch.snapshot = stored.snapshot
                fetch.fetched_at = stored.snapshot.latest_retrieval
                fetch.completed_at = now
                fetch.retry_at = None
                fetch.reason_code = "ready"
                fetch.full_reason = ""
                fetch.save(
                    update_fields=[
                        "status",
                        "snapshot",
                        "fetched_at",
                        "completed_at",
                        "retry_at",
                        "reason_code",
                        "full_reason",
                        "updated_at",
                    ]
                )
                ready_fetch_ids.append(fetch.id)
        batch.status = WeatherFetchBatch.Status.COMPLETED
        batch.retry_at = None
        batch.completed_at = now
        batch.reason_code = "ready"
        batch.full_reason = ""
        batch.save(
            update_fields=[
                "status",
                "retry_at",
                "completed_at",
                "reason_code",
                "full_reason",
                "updated_at",
            ]
        )
        for fetch_id in ready_fetch_ids:
            transaction.on_commit(
                lambda fetch_id=fetch_id: _dispatch_estimate_callback(fetch_id=fetch_id)
            )


def process_weather_fetch_batch(
    *,
    batch_id: uuid.UUID | str,
    transport: Callable[..., Any] | None = None,
    clock: Callable[[], datetime] | None = None,
    provider: WeatherProvider | None = None,
) -> bool:
    """Run one claimed batch and atomically store every cell snapshot."""
    parsed_batch_id = uuid.UUID(str(batch_id))
    now = _clock_now(clock)
    batch = _claim_batch(batch_id=parsed_batch_id, now=now)
    if batch is None:
        return False
    request = batch.request
    spec = request_spec_from_request(request=request)
    fetches = list(
        WeatherFetch.objects.filter(
            id__in=batch.parts.values_list("fetch_id", flat=True)
        ).select_related("snapshot")
        if batch.parts.exists()
        else batch.fetches.select_related("snapshot").order_by("cell_key")
    )
    has_no_snapshot = all(fetch.snapshot_id is None for fetch in fetches)
    client = provider or WeatherProvider(transport=transport, clock=clock)
    try:
        result = client.fetch(
            spec=spec,
            provenance={"weather_fetch_batch_id": str(batch.id)},
            allow_completed_refetch=request.status == WeatherRequest.Status.COMPLETED and has_no_snapshot,
        )
        _store_batch(batch_id=parsed_batch_id, result=result, now=_clock_now(clock))
        return True
    except PendingRequestError as exc:
        retry_at = exc.retry_at or (_clock_now(clock) + RETRY_DELAY)
        _batch_pending(
            batch_id=parsed_batch_id,
            reason_code=_pending_reason(batch=batch, error=exc),
            full_reason=str(exc),
            retry_at=retry_at,
            now=_clock_now(clock),
        )
        return False
    except (
        PermanentProviderError,
        ResponseValidationError,
        WeatherDailyConflictError,
        WeatherOnDemandError,
    ) as exc:
        _batch_failed(
            batch_id=parsed_batch_id,
            reason_code=(
                "storage_conflict"
                if isinstance(exc, (WeatherDailyConflictError, WeatherOnDemandError))
                else "provider_refused"
            ),
            full_reason=str(exc),
            now=_clock_now(clock),
        )
        return False
    except Exception as exc:
        if not _is_transient_storage_error(error=exc):
            _batch_failed(
                batch_id=parsed_batch_id,
                reason_code="storage_failure",
                full_reason=str(exc),
                now=_clock_now(clock),
            )
            return False
        retry_at = _clock_now(clock) + RETRY_DELAY
        _batch_pending(
            batch_id=parsed_batch_id,
            reason_code=_retry_reason(error=exc),
            full_reason=str(exc),
            retry_at=retry_at,
            now=_clock_now(clock),
        )
        return False


def _cell_result(
    *,
    cell_key: str,
    assessment_date: date,
) -> CellWeatherResult:
    current = _snapshot_for_date(cell_key=cell_key, assessment_date=assessment_date)
    fetch = WeatherFetch.objects.filter(
        cell_key=cell_key,
        assessment_date=assessment_date,
        pipeline_version=PIPELINE_VERSION,
    ).first()
    if current is not None:
        source = current.source_ids[0] if current.source_ids else None
        from weather_summaries.models import WeatherDaily

        known_missing = current.days.filter(
            daily__status=WeatherDaily.Status.CHECKED_KNOWN_MISSING
        ).exists()
        return CellWeatherResult(
            cell_key=cell_key,
            state="current",
            assessment_date=current.assessment_date,
            fetched_at=current.latest_retrieval,
            source=source,
            snapshot_id=str(current.id),
            reason_code="known_missing" if known_missing else "ready",
            full_reason=(
                "The provider returned a checked known gap for one or more daily values."
                if known_missing
                else ""
            ),
        )
    previous = _previous_snapshot(cell_key=cell_key, assessment_date=assessment_date)
    if previous is not None:
        source = previous.source_ids[0] if previous.source_ids else None
        reason_code = fetch.reason_code if fetch is not None else "fetch_pending"
        full_reason = fetch.full_reason if fetch is not None else "The current assessment is still pending."
        return CellWeatherResult(
            cell_key=cell_key,
            state="previous",
            assessment_date=previous.assessment_date,
            fetched_at=previous.latest_retrieval,
            source=source,
            snapshot_id=str(previous.id),
            reason_code=reason_code,
            full_reason=full_reason,
        )
    reason_code = fetch.reason_code if fetch is not None else "fetch_pending"
    full_reason = fetch.full_reason if fetch is not None else "The first weather fetch has not completed."
    return CellWeatherResult(
        cell_key=cell_key,
        state="not_available_yet",
        assessment_date=None,
        fetched_at=None,
        source=None,
        snapshot_id=None,
        reason_code=reason_code,
        full_reason=full_reason,
    )


def request_weather(
    *,
    cells: Sequence[WeatherCell],
    visitor_id: str | bytes | None = None,
    assessment_date: date | None = None,
    clock: Callable[[], datetime] | None = None,
    transport: Callable[..., Any] | None = None,
    provider: WeatherProvider | None = None,
    wait_seconds: float = DEFAULT_WAIT_SECONDS,
    monotonic: Callable[[], float] | None = None,
    model: str = DEFAULT_MODEL,
    forest_build_version: str = "",
    options: Mapping[str, str] | None = None,
) -> WeatherLookupResult:
    """Plan, queue and briefly wait for weather cells requested by a visitor."""
    if not cells:
        raise ValueError("At least one weather cell is required.")
    target_date = assessment_date or italian_assessment_date(clock=clock)
    if not isinstance(target_date, date) or isinstance(target_date, datetime):
        raise TypeError("assessment_date must be a date.")
    visitor_hash = opaque_visitor_hash(visitor_id=visitor_id)
    now = _clock_now(clock)
    batches = _plan_batches(
        cells=cells,
        assessment_date=target_date,
        visitor_hash=visitor_hash,
        now=now,
        model=model,
        forest_build_version=forest_build_version,
        options=options,
    )
    inline = transport is not None or provider is not None
    for batch in batches:
        if inline:
            _start_injected_batch(
                batch_id=batch.id,
                transport=transport,
                clock=clock,
                provider=provider,
            )
        else:
            _schedule_batch(batch=batch)
    monotonic_clock = monotonic or time.monotonic
    deadline = monotonic_clock() + max(0.0, wait_seconds)
    while monotonic_clock() < deadline:
        results = tuple(
            _cell_result(cell_key=cell.key, assessment_date=target_date)
            for cell in sorted(cells, key=lambda item: item.key)
        )
        if all(item.state == "current" for item in results):
            return WeatherLookupResult(assessment_date=target_date, cells=results)
        time.sleep(0.05)
    results = tuple(
        _cell_result(cell_key=cell.key, assessment_date=target_date)
        for cell in sorted(cells, key=lambda item: item.key)
    )
    return WeatherLookupResult(assessment_date=target_date, cells=results)


def fetch_weather_on_demand(**kwargs: Any) -> WeatherLookupResult:
    """Return weather through the public on-demand service."""
    return request_weather(**kwargs)


def _recover_estimate_callbacks(*, now: datetime) -> None:
    """Retry ready fetch callbacks without repeating provider work."""
    if _ESTIMATE_CALLBACK is None:
        return
    fetches = WeatherFetch.objects.filter(
        status=WeatherFetch.Status.COMPLETED,
        snapshot__isnull=False,
        pipeline_version=PIPELINE_VERSION,
    ).filter(
        estimate_callback_status__in=["pending", "running"],
    )
    for fetch in fetches:
        if (
            fetch.estimate_callback_status == "running"
            and fetch.estimate_callback_started_at is not None
            and fetch.estimate_callback_started_at + RETRY_DELAY > now
        ):
            continue
        if fetch.estimate_callback_status == "running":
            WeatherFetch.objects.filter(id=fetch.id).update(
                estimate_callback_status="pending",
                estimate_callback_started_at=None,
                updated_at=now,
            )
        if (
            fetch.estimate_callback_retry_at is not None
            and fetch.estimate_callback_retry_at > now
        ):
            continue
        _dispatch_estimate_callback(fetch_id=fetch.id)


def recover_weather_fetches(
    *,
    now: datetime | None = None,
    stale_after: timedelta = timedelta(minutes=2),
) -> int:
    """Return abandoned running batches to pending queue work."""
    current = _clock_now(lambda: now) if now is not None else _clock_now()
    cutoff = current - stale_after
    recovered = 0
    candidates = WeatherFetchBatch.objects.filter(
        status=WeatherFetchBatch.Status.RUNNING,
        started_at__lt=cutoff,
    ).select_related("request").order_by("started_at")
    for candidate in candidates:
        with transaction.atomic():
            batch = (
                WeatherFetchBatch.objects.select_for_update()
                .select_related("request")
                .get(id=candidate.id)
            )
            if batch.status != WeatherFetchBatch.Status.RUNNING or (
                batch.started_at is not None and batch.started_at >= cutoff
            ):
                continue
            retry_at = max(
                current + RETRY_DELAY,
                batch.retry_at or current + RETRY_DELAY,
                batch.request.retry_at or current + RETRY_DELAY,
            )
            batch.status = WeatherFetchBatch.Status.PENDING
            batch.task_id = None
            batch.retry_at = retry_at
            batch.reason_code = "worker_interrupted"
            batch.full_reason = "The worker stopped before weather storage completed."
            batch.save(
                update_fields=[
                    "status",
                    "task_id",
                    "retry_at",
                    "reason_code",
                    "full_reason",
                    "updated_at",
                ]
            )
            batch.fetches.filter(status=WeatherFetch.Status.RUNNING).update(
                status=WeatherFetch.Status.PENDING,
                retry_at=retry_at,
                reason_code="worker_interrupted",
                full_reason=batch.full_reason,
                updated_at=current,
            )
            WeatherFetch.objects.filter(
                id__in=batch.parts.values_list("fetch_id", flat=True),
                status=WeatherFetch.Status.RUNNING,
            ).update(
                status=WeatherFetch.Status.PENDING,
                retry_at=retry_at,
                reason_code="worker_interrupted",
                full_reason=batch.full_reason,
                updated_at=current,
            )
            batch.parts.filter(status=WeatherFetchPart.Status.RUNNING).update(
                status=WeatherFetchPart.Status.PENDING,
                retry_at=retry_at,
                reason_code="worker_interrupted",
                full_reason=batch.full_reason,
                updated_at=current,
            )
        _schedule_batch(batch=batch, run_after=retry_at)
        recovered += 1
    for batch in WeatherFetchBatch.objects.filter(
        status=WeatherFetchBatch.Status.PENDING,
    ).order_by("first_requested_at"):
        if batch.task_id is not None and _queue_task_is_active(
            task_id=batch.task_id,
            logical_keys=weather_task_lock_keys(batch_id=batch.id),
        ):
            continue
        if batch.task_id is not None:
            with transaction.atomic():
                current_batch = WeatherFetchBatch.objects.select_for_update().get(id=batch.id)
                if current_batch.task_id == batch.task_id:
                    current_batch.task_id = None
                    current_batch.reason_code = "worker_claim_lost"
                    current_batch.full_reason = (
                        "The worker stopped after claiming the weather task."
                    )
                    current_batch.save(
                        update_fields=["task_id", "reason_code", "full_reason", "updated_at"]
                    )
                    batch = current_batch
                else:
                    batch = current_batch
        if batch.retry_at is not None and batch.retry_at > current:
            continue
        _schedule_batch(batch=batch, run_after=max(current, batch.retry_at or current))
    cleanup_cutoff = current - stale_after
    for candidate in WeatherCleanupJob.objects.filter(
        status=WeatherCleanupJob.Status.RUNNING,
        updated_at__lt=cleanup_cutoff,
    ).order_by("updated_at"):
        with transaction.atomic():
            job = WeatherCleanupJob.objects.select_for_update().get(id=candidate.id)
            if job.status != WeatherCleanupJob.Status.RUNNING or job.updated_at >= cleanup_cutoff:
                continue
            retry_at = max(current + RETRY_DELAY, job.retry_at or current + RETRY_DELAY)
            job.status = WeatherCleanupJob.Status.PENDING
            job.task_id = None
            job.retry_at = retry_at
            job.full_reason = "The worker stopped before weather cleanup completed."
            job.save(
                update_fields=[
                    "status",
                    "task_id",
                    "retry_at",
                    "full_reason",
                    "updated_at",
                ]
            )
        _schedule_cleanup(job=job, run_after=retry_at)
        recovered += 1
    for job in WeatherCleanupJob.objects.filter(
        status=WeatherCleanupJob.Status.PENDING,
    ).order_by("cleanup_date"):
        if job.task_id is not None and _queue_task_is_active(
            task_id=job.task_id,
            logical_keys=weather_cleanup_task_lock_keys(job_id=job.id),
        ):
            continue
        if job.task_id is not None:
            with transaction.atomic():
                current_job = WeatherCleanupJob.objects.select_for_update().get(id=job.id)
                if current_job.task_id == job.task_id:
                    current_job.task_id = None
                    current_job.full_reason = (
                        "The worker stopped after claiming the weather cleanup task."
                    )
                    current_job.save(update_fields=["task_id", "full_reason", "updated_at"])
                    job = current_job
                else:
                    job = current_job
        if job.retry_at is not None and job.retry_at > current:
            continue
        _schedule_cleanup(job=job, run_after=max(current, job.retry_at or current))
    _recover_estimate_callbacks(now=current)
    return recovered


def cleanup_weather(
    *,
    cleanup_date: date,
    protected_snapshot_ids: Iterable[str] = (),
) -> dict[str, int | str]:
    """Delete unreferenced old weather rows without provider access."""
    protected = {str(value) for value in protected_snapshot_ids}
    if _CLEANUP_CALLBACK is not None:
        protected.update(
            str(value)
            for value in (_CLEANUP_CALLBACK(cleanup_date=cleanup_date) or ())
        )
    with transaction.atomic():
        snapshots = list(
            WeatherSnapshot.objects.order_by("cell_key", "-assessment_date", "-created_at")
        )
        keep: set[str] = set(protected)
        kept_per_cell: dict[str, int] = defaultdict(int)
        for snapshot in snapshots:
            if kept_per_cell[snapshot.cell_key] < 2:
                keep.add(str(snapshot.id))
                kept_per_cell[snapshot.cell_key] += 1
        latest_fetch_by_cell: dict[str, WeatherFetch] = {}
        for fetch in WeatherFetch.objects.order_by("cell_key", "-assessment_date", "-updated_at"):
            latest_fetch_by_cell.setdefault(fetch.cell_key, fetch)
        keep.update(
            str(value)
            for fetch in latest_fetch_by_cell.values()
            for value in (fetch.snapshot_id, fetch.previous_snapshot_id)
            if value is not None
        )
        active_fetches = WeatherFetch.objects.filter(
            status__in=[WeatherFetch.Status.PENDING, WeatherFetch.Status.RUNNING]
        )
        keep.update(
            str(value)
            for value in active_fetches.values_list("snapshot_id", flat=True)
            if value is not None
        )
        keep.update(
            str(value)
            for value in active_fetches.values_list("previous_snapshot_id", flat=True)
            if value is not None
        )
        if _ESTIMATE_CALLBACK is not None:
            keep.update(
                str(value)
                for value in WeatherFetch.objects.filter(
                    status=WeatherFetch.Status.COMPLETED,
                ).exclude(estimate_callback_status="completed").values_list(
                    "snapshot_id", flat=True
                )
                if value is not None
            )
        protected_daily_ids = {
            str(row_id)
            for part_ids in WeatherFetchPart.objects.filter(
                fetch__status__in=[WeatherFetch.Status.PENDING, WeatherFetch.Status.RUNNING],
            ).values_list("daily_ids", flat=True)
            for row_id in (part_ids or [])
        }
        if apps.is_installed("estimate_updates"):
            from estimate_updates.models import EstimateTask

            keep.update(
                str(value)
                for value in EstimateTask.objects.values_list("snapshot_id", flat=True)
            )
        terminal_fetches = WeatherFetch.objects.filter(
            status__in=[WeatherFetch.Status.COMPLETED, WeatherFetch.Status.FAILED]
        )
        terminal_fetches.filter(snapshot_id__isnull=False).exclude(
            snapshot_id__in=keep
        ).update(snapshot=None, updated_at=timezone.now())
        terminal_fetches.filter(previous_snapshot_id__isnull=False).exclude(
            previous_snapshot_id__in=keep
        ).update(previous_snapshot=None, updated_at=timezone.now())
        deletable = [
            snapshot.id
            for snapshot in snapshots
            if str(snapshot.id) not in keep
            and snapshot.assessment_date < cleanup_date
        ]
        snapshots_to_delete = WeatherSnapshot.objects.filter(id__in=deletable)
        deleted_snapshots = snapshots_to_delete.count()
        snapshots_to_delete.delete()
        cutoff = cleanup_date - timedelta(days=HISTORY_DAYS)
        from weather_summaries.models import WeatherDaily

        deleted_daily_count = WeatherDaily.objects.filter(
            date__lt=cutoff,
            snapshot_days__isnull=True,
        ).exclude(id__in=protected_daily_ids).delete()[0]
        from weather_requests.models import WeatherRequestAttempt

        attempt_cutoff = datetime.combine(
            cleanup_date - timedelta(days=31),
            datetime.min.time(),
            tzinfo=UTC,
        )
        deleted_attempt_count = WeatherRequestAttempt.objects.filter(
            reserved_at__lt=attempt_cutoff,
        ).delete()[0]
        WeatherVisitorReservation.objects.filter(
            reserved_at__lt=timezone.now() - VISITOR_WINDOW,
        ).delete()
    return {
        "cleanup_date": cleanup_date.isoformat(),
        "deleted_snapshot_count": deleted_snapshots,
        "deleted_daily_count": deleted_daily_count,
        "deleted_attempt_count": deleted_attempt_count,
    }


def enqueue_cleanup(
    *,
    cleanup_date: date | None = None,
    protected_snapshot_ids: Iterable[str] = (),
) -> WeatherCleanupJob:
    """Create one date-keyed cleanup task and queue it after commit."""
    target = cleanup_date or italian_assessment_date()
    logical_key = f"weather-cleanup:{target.isoformat()}"
    requested_protected = [str(value) for value in protected_snapshot_ids]
    with transaction.atomic():
        job, _created = WeatherCleanupJob.objects.get_or_create(
            cleanup_date=target,
            defaults={
                "logical_key": logical_key,
                "protected_snapshot_ids": requested_protected,
            },
        )
        if requested_protected and job.status != WeatherCleanupJob.Status.COMPLETED:
            job.protected_snapshot_ids = list(
                dict.fromkeys([*job.protected_snapshot_ids, *requested_protected])
            )
            job.save(update_fields=["protected_snapshot_ids", "updated_at"])
        if job.status != WeatherCleanupJob.Status.COMPLETED and job.task_id is None:
            transaction.on_commit(
                lambda job_id=job.id, retry_at=job.retry_at: _enqueue_cleanup(
                    job_id=job_id,
                    run_after=retry_at,
                )
            )
    job.refresh_from_db()
    return job


def _enqueue_cleanup(
    *,
    job_id: uuid.UUID,
    run_after: datetime | None = None,
) -> uuid.UUID | None:
    from .tasks import weather_cleanup_task

    try:
        task = weather_cleanup_task.using(run_after=run_after) if run_after else weather_cleanup_task
        with transaction.atomic():
            job = WeatherCleanupJob.objects.select_for_update().get(id=job_id)
            if _queue_task_is_active(task_id=job.task_id):
                return job.task_id
            task_result = task.enqueue(job_id=str(job_id))
            task_id = uuid.UUID(str(task_result.id))
            job.task_id = task_id
            job.save(update_fields=["task_id", "updated_at"])
            return task_id
    except Exception as exc:
        WeatherCleanupJob.objects.filter(id=job_id).update(
            task_id=None,
            full_reason=str(exc),
            updated_at=timezone.now(),
        )
        return None


def _schedule_cleanup(*, job: WeatherCleanupJob, run_after: datetime | None = None) -> None:
    """Queue cleanup after its row is committed, once it is due."""
    if run_after is None and job.retry_at is not None and job.retry_at > timezone.now():
        run_after = job.retry_at
    if _queue_task_is_active(task_id=job.task_id):
        return
    transaction.on_commit(
        lambda: _enqueue_cleanup(job_id=job.id, run_after=run_after)
    )


def run_cleanup_job(*, job_id: uuid.UUID | str) -> dict[str, int | str]:
    """Run one queued cleanup job without network access."""
    with transaction.atomic():
        job = WeatherCleanupJob.objects.select_for_update().get(id=job_id)
        if job.status == WeatherCleanupJob.Status.COMPLETED:
            return {
                "cleanup_date": job.cleanup_date.isoformat(),
                "deleted_snapshot_count": job.deleted_snapshot_count,
                "deleted_daily_count": job.deleted_daily_count,
            }
        job.status = WeatherCleanupJob.Status.RUNNING
        job.save(update_fields=["status", "updated_at"])
    try:
        result = cleanup_weather(
            cleanup_date=job.cleanup_date,
            protected_snapshot_ids=job.protected_snapshot_ids,
        )
    except Exception as exc:
        WeatherCleanupJob.objects.filter(id=job.id).update(
            status=WeatherCleanupJob.Status.PENDING,
            task_id=None,
            retry_at=timezone.now() + RETRY_DELAY,
            full_reason=str(exc),
            updated_at=timezone.now(),
        )
        job.refresh_from_db()
        _schedule_cleanup(job=job, run_after=job.retry_at)
        raise
    WeatherCleanupJob.objects.filter(id=job.id).update(
        status=WeatherCleanupJob.Status.COMPLETED,
        deleted_snapshot_count=int(result["deleted_snapshot_count"]),
        deleted_daily_count=int(result["deleted_daily_count"]),
        retry_at=None,
        completed_at=timezone.now(),
        full_reason="",
        updated_at=timezone.now(),
    )
    return result


def weather_status(*, assessment_date: date | None = None) -> dict[str, Any]:
    """Return durable fetch, quota and cleanup status without network access."""
    target = assessment_date or italian_assessment_date()
    fetches = WeatherFetch.objects.all()
    per_day: dict[str, dict[str, int]] = {}
    for row in fetches.values("assessment_date", "status").annotate(count=Count("id")):
        key = row["assessment_date"].isoformat()
        per_day.setdefault(key, {})[row["status"]] = row["count"]
    from weather_requests.models import WeatherRequestAttempt

    attempts = WeatherRequestAttempt.objects.all()
    counted_calls = attempts.aggregate(total=Sum("reservation_weight"))["total"]
    refusals = list(
        attempts.filter(outcome=WeatherRequestAttempt.Outcome.REFUSED)
        .order_by("-reserved_at")
        .values("id", "request_id", "http_status", "full_message", "reserved_at")[:100]
    )
    for item in refusals:
        item["id"] = str(item["id"])
        item["request_id"] = str(item["request_id"])
        item["reserved_at"] = item["reserved_at"].isoformat()
    last_cleanup = WeatherCleanupJob.objects.order_by("-cleanup_date").first()
    return {
        "assessment_date": target.isoformat(),
        "fetches_per_day": per_day,
        "counted_calls": str(counted_calls or "0"),
        "attempt_count": attempts.count(),
        "refused_requests": refusals,
        "pending_cells": list(
            fetches.filter(status=WeatherFetch.Status.PENDING).values_list("cell_key", flat=True)
        ),
        "last_cleanup": (
            {
                "cleanup_date": last_cleanup.cleanup_date.isoformat(),
                "status": last_cleanup.status,
            }
            if last_cleanup
            else None
        ),
    }


__all__ = [
    "CellWeatherResult",
    "DEFAULT_WAIT_SECONDS",
    "WeatherLookupResult",
    "WeatherOnDemandError",
    "cleanup_weather",
    "configure_cleanup_callback",
    "configure_estimate_callback",
    "enqueue_cleanup",
    "fetch_weather_on_demand",
    "italian_assessment_date",
    "opaque_visitor_hash",
    "notify_snapshot_ready",
    "process_weather_fetch_batch",
    "recover_weather_fetches",
    "request_weather",
    "reopen_weather_fetch",
    "run_cleanup_job",
    "set_estimate_callback",
    "set_cleanup_callback",
    "weather_status",
]
