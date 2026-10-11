import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class RepresentativeInput(models.Model):
    """Store the small, deterministic input used by the representative task."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    value = models.PositiveIntegerField(default=1)
    delay_seconds = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(5.0)],
    )
    fail_first_attempt = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(delay_seconds__gte=0, delay_seconds__lte=5),
                name="representative_input_delay_bounded",
            ),
        ]


class BackgroundJob(models.Model):
    """Identify one logical run and the persisted input it processes."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    logical_key = models.CharField(max_length=255, unique=True)
    job_name = models.CharField(max_length=100)
    input = models.ForeignKey(
        RepresentativeInput,
        on_delete=models.PROTECT,
        related_name="background_jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)


class BackgroundJobAttempt(models.Model):
    """Record one immutable attempt and its database task identifier."""

    class State(models.TextChoices):
        WAITING = "waiting", "Waiting"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    job = models.ForeignKey(
        BackgroundJob,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    attempt_number = models.PositiveIntegerField()
    task_id = models.UUIDField(null=True, blank=True, unique=True)
    state = models.CharField(
        max_length=20,
        choices=State.choices,
        default=State.WAITING,
    )
    retry_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retries",
    )
    queued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["job", "attempt_number"],
                name="background_job_attempt_number_unique",
            ),
            models.UniqueConstraint(
                fields=["job"],
                condition=Q(state__in=["waiting", "running"]),
                name="background_job_one_active_attempt",
            ),
        ]
        ordering = ["attempt_number"]


class RepresentativeResult(models.Model):
    """Store the deterministic result for one completed logical run."""

    job = models.OneToOneField(
        BackgroundJob,
        on_delete=models.CASCADE,
        related_name="result",
    )
    result_value = models.PositiveIntegerField()
    completed_at = models.DateTimeField(auto_now_add=True)
