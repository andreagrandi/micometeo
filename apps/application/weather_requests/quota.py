"""Durable rolling-window reservations for the Open-Meteo free allowance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_UP
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Max, Sum
from django.utils import timezone

from .models import WeatherQuotaLock, WeatherRequest, WeatherRequestAttempt

WINDOWS: tuple[tuple[str, timedelta], ...] = (
    ("minute", timedelta(seconds=60)),
    ("hour", timedelta(seconds=3_600)),
    ("day", timedelta(seconds=86_400)),
    ("month", timedelta(days=31)),
)
LIMITS: dict[str, Decimal] = {
    "minute": Decimal("540"),
    "hour": Decimal("4500"),
    "day": Decimal("9000"),
    "month": Decimal("270000"),
}
WEIGHT_QUANTUM = Decimal("0.000001")


def _as_utc(value: datetime | None) -> datetime:
    result = value or timezone.now()
    if timezone.is_naive(result):
        return result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _weight(value: Decimal | float | int | str) -> Decimal:
    result = Decimal(str(value)).quantize(WEIGHT_QUANTUM, rounding=ROUND_UP)
    if result <= 0:
        raise ValueError("A quota reservation must be positive.")
    return result


@dataclass(frozen=True)
class QuotaCheck:
    """Describe whether one reservation fits every rolling allowance."""

    allowed: bool
    reservation_weight: Decimal
    now: datetime
    usage: dict[str, Decimal]
    limits: dict[str, Decimal]
    retry_at: datetime | None = None
    reason: str = ""

    def __bool__(self) -> bool:
        return self.allowed

    @property
    def pending(self) -> bool:
        """Return whether the caller must wait before reserving."""
        return not self.allowed

    @property
    def earliest_retry(self) -> datetime | None:
        """Return the first time at which all limits may permit the reservation."""
        return self.retry_at

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-safe quota details."""
        return {
            "allowed": self.allowed,
            "reservation_weight": str(self.reservation_weight),
            "now": self.now.isoformat(),
            "usage": {name: str(value) for name, value in self.usage.items()},
            "limits": {name: str(value) for name, value in self.limits.items()},
            "retry_at": self.retry_at.isoformat() if self.retry_at else None,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ReservationResult:
    """Return an attempt reservation or the pending quota decision."""

    attempt: WeatherRequestAttempt | None
    quota: QuotaCheck

    @property
    def reserved(self) -> bool:
        """Return whether a network attempt may start."""
        return self.attempt is not None

    def __bool__(self) -> bool:
        return self.reserved


def quota_limits() -> dict[str, Decimal]:
    """Return the conservative allowance limits."""
    return dict(LIMITS)


def _ensure_lock() -> WeatherQuotaLock:
    try:
        return WeatherQuotaLock.objects.select_for_update().get(pk=1)
    except WeatherQuotaLock.DoesNotExist:
        try:
            with transaction.atomic():
                WeatherQuotaLock.objects.create(pk=1)
        except IntegrityError:
            pass
        return WeatherQuotaLock.objects.select_for_update().get(pk=1)


def _attempt_usage(*, now: datetime, window: timedelta) -> Decimal:
    total = (
        WeatherRequestAttempt.objects.filter(
            reserved_at__gt=now - window,
            reserved_at__lte=now,
        ).aggregate(total=Sum("reservation_weight"))["total"]
    )
    return Decimal(str(total or "0")).quantize(WEIGHT_QUANTUM)


def _retry_candidate(*, now: datetime, reservation_weight: Decimal, violated: list[str]) -> datetime | None:
    if not violated:
        return None
    attempts = list(
        WeatherRequestAttempt.objects.values_list("reserved_at", "reservation_weight")
    )
    candidates: set[datetime] = {now}
    for name, window in WINDOWS:
        if name not in violated:
            continue
        candidates.update(
            _as_utc(timestamp) + window
            for timestamp, _weight_value in attempts
            if _as_utc(timestamp) + window > now
        )
    for candidate in sorted(candidates):
        usage = {
            name: _usage_at(candidate=candidate, window=window)
            for name, window in WINDOWS
        }
        if all(usage[name] + reservation_weight <= LIMITS[name] for name in violated):
            return candidate
    return max(candidates) if candidates else None


def _usage_at(*, candidate: datetime, window: timedelta) -> Decimal:
    return _attempt_usage(now=candidate, window=window)


def _check_locked(*, reservation_weight: Decimal, now: datetime) -> QuotaCheck:
    usage = {
        name: _attempt_usage(now=now, window=window)
        for name, window in WINDOWS
    }
    violated = [
        name
        for name in LIMITS
        if usage[name] + reservation_weight > LIMITS[name]
    ]
    retry_at = _retry_candidate(
        now=now,
        reservation_weight=reservation_weight,
        violated=violated,
    )
    reason = ""
    if violated:
        reason = "Quota limit reached: " + ", ".join(violated)
    return QuotaCheck(
        allowed=not violated,
        reservation_weight=reservation_weight,
        now=now,
        usage=usage,
        limits=quota_limits(),
        retry_at=retry_at,
        reason=reason,
    )


def check_quota(
    *,
    reservation_weight: Decimal | float | int | str,
    now: datetime | None = None,
) -> QuotaCheck:
    """Check all rolling limits under the same lock used for reservations."""
    weight = _weight(reservation_weight)
    checked_at = _as_utc(now)
    with transaction.atomic():
        _ensure_lock()
        return _check_locked(reservation_weight=weight, now=checked_at)


def reserve_attempt(
    *,
    request: WeatherRequest | UUID | str,
    reservation_weight: Decimal | float | int | str,
    now: datetime | None = None,
) -> ReservationResult:
    """Atomically reserve quota and create the attempt before network I/O."""
    weight = _weight(reservation_weight)
    reserved_at = _as_utc(now)
    with transaction.atomic():
        _ensure_lock()
        quota = _check_locked(reservation_weight=weight, now=reserved_at)
        if isinstance(request, WeatherRequest):
            locked_request = WeatherRequest.objects.select_for_update().get(pk=request.pk)
        else:
            locked_request = WeatherRequest.objects.select_for_update().get(pk=request)
        if locked_request.first_requested_at is None:
            locked_request.first_requested_at = reserved_at
        if not quota.allowed:
            locked_request.status = WeatherRequest.Status.PENDING
            locked_request.retry_at = quota.retry_at
            locked_request.latest_provider_message = quota.reason
            locked_request.last_attempt_at = reserved_at
            locked_request.save(
                update_fields=[
                    "status",
                    "retry_at",
                    "latest_provider_message",
                    "last_attempt_at",
                    "first_requested_at",
                    "updated_at",
                ]
            )
            return ReservationResult(attempt=None, quota=quota)
        latest = locked_request.attempts.aggregate(latest=Max("attempt_number"))["latest"] or 0
        attempt = WeatherRequestAttempt.objects.create(
            request=locked_request,
            attempt_number=latest + 1,
            reserved_at=reserved_at,
            reservation_weight=weight,
            outcome=WeatherRequestAttempt.Outcome.RESERVATION,
        )
        locked_request.status = WeatherRequest.Status.PENDING
        locked_request.retry_at = None
        locked_request.last_attempt_at = reserved_at
        locked_request.save(
            update_fields=[
                "status",
                "retry_at",
                "last_attempt_at",
                "first_requested_at",
                "updated_at",
            ]
        )
        return ReservationResult(attempt=attempt, quota=quota)


def finish_attempt(
    *,
    attempt: WeatherRequestAttempt,
    outcome: str,
    ended_at: datetime | None = None,
    message: str = "",
    http_status: int | None = None,
    retry_at: datetime | None = None,
    duration_seconds: Decimal | float | None = None,
) -> WeatherRequestAttempt:
    """Fill the result fields of one already reserved network attempt."""
    finished_at = _as_utc(ended_at)
    values: dict[str, Any] = {
        "started_at": attempt.started_at or attempt.reserved_at,
        "ended_at": finished_at,
        "outcome": outcome,
        "full_message": message,
        "http_status": http_status,
        "retry_at": retry_at,
    }
    if duration_seconds is None:
        started = _as_utc(attempt.started_at or attempt.reserved_at)
        values["duration_seconds"] = Decimal(str((finished_at - started).total_seconds())).quantize(
            Decimal("0.001"), rounding=ROUND_UP
        )
    else:
        values["duration_seconds"] = Decimal(str(duration_seconds)).quantize(
            Decimal("0.001"), rounding=ROUND_UP
        )
    type(attempt).objects.filter(pk=attempt.pk).update(**values)
    for key, value in values.items():
        setattr(attempt, key, value)
    return attempt
