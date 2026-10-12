from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q


class WeatherRequest(models.Model):
    """Store one canonical provider request and its durable result state."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    request_digest = models.CharField(max_length=64, unique=True)
    canonical_spec = models.JSONField(default=dict)
    forest_build_version = models.CharField(max_length=120)
    provenance = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    retry_at = models.DateTimeField(null=True, blank=True)
    latest_provider_message = models.TextField(blank=True, default="")
    first_requested_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    completion_metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["status", "retry_at"]),
            models.Index(fields=["forest_build_version", "status"]),
        ]

    @property
    def digest(self) -> str:
        """Return the stable digest used as the request cache identity."""
        return self.request_digest

    @property
    def request_key(self) -> str:
        """Return the stable digest used as the request cache identity."""
        return self.request_digest

    @property
    def provider_latest_message(self) -> str:
        """Return the latest complete provider refusal or failure message."""
        return self.latest_provider_message

    @property
    def full_provider_latest_message(self) -> str:
        """Return the latest complete provider refusal or failure message."""
        return self.latest_provider_message


class WeatherRequestMember(models.Model):
    """Store one ordered weather cell in a provider request."""

    id = models.BigAutoField(primary_key=True)
    request = models.ForeignKey(
        WeatherRequest,
        on_delete=models.CASCADE,
        related_name="members",
    )
    position = models.PositiveIntegerField()
    weather_cell_key = models.CharField(max_length=80)
    latitude = models.DecimalField(max_digits=8, decimal_places=2)
    longitude = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["request", "position"],
                name="weather_request_member_position_unique",
            ),
            models.UniqueConstraint(
                fields=["request", "weather_cell_key"],
                name="weather_request_member_key_unique",
            ),
        ]

    @property
    def key(self) -> str:
        """Return the canonical weather cell key."""
        return self.weather_cell_key


class WeatherQuotaLock(models.Model):
    """Provide one row that serializes quota checks and reservations."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name="weather_quota_lock_singleton"),
        ]


class WeatherRequestAttempt(models.Model):
    """Record one quota reservation and exactly one network attempt."""

    class Outcome(models.TextChoices):
        RESERVATION = "reservation", "Reserved before network I/O"
        SUCCESS = "success", "Success"
        RETRY = "retry", "Retry later"
        REFUSED = "refused", "Provider refused"
        FAILED = "failed", "Permanent failure"
        CRASHED = "crashed", "Worker stopped after reservation"

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    request = models.ForeignKey(
        WeatherRequest,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    attempt_number = models.PositiveIntegerField()
    reserved_at = models.DateTimeField()
    reservation_weight = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        validators=[],
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(
        max_length=20,
        choices=Outcome.choices,
        default=Outcome.RESERVATION,
    )
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    full_message = models.TextField(blank=True, default="")
    retry_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["request", "attempt_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["request", "attempt_number"],
                name="weather_request_attempt_number_unique",
            ),
            models.CheckConstraint(
                condition=Q(reservation_weight__gt=Decimal("0")),
                name="weather_request_attempt_weight_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["reserved_at"]),
            models.Index(fields=["outcome", "reserved_at"]),
        ]

    def save(self, *args, **kwargs):
        """Keep the reservation identity fixed after its first insert."""
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            original = type(self).objects.only(
                "request_id",
                "attempt_number",
                "reserved_at",
                "reservation_weight",
            ).get(pk=self.pk)
            for field in ("request_id", "attempt_number", "reserved_at", "reservation_weight"):
                if getattr(original, field) != getattr(self, field):
                    raise ValueError("A weather request reservation cannot change after insertion.")
        super().save(*args, **kwargs)

    @property
    def attempt_time(self):
        """Return the timestamp at which this quota reservation was made."""
        return self.reserved_at

    @property
    def time(self):
        """Return the timestamp at which this quota reservation was made."""
        return self.reserved_at

    @property
    def reservation_time(self):
        """Return the timestamp at which quota was reserved."""
        return self.reserved_at

    @property
    def decimal_weight(self) -> Decimal:
        """Return the exact decimal weight reserved for this attempt."""
        return self.reservation_weight

    @property
    def weight(self) -> Decimal:
        """Return the exact decimal weight reserved for this attempt."""
        return self.reservation_weight

    @property
    def message(self) -> str:
        """Return the full provider message recorded for this attempt."""
        return self.full_message

    @property
    def state(self) -> str:
        """Return the attempt outcome under the queue-facing name."""
        return self.outcome
