from __future__ import annotations

import uuid

from django.db import models
from django.db.models import Q

from national_forest.models import ForestBuild, ForestCell
from national_grid.models import GridBuild
from national_terrain.models import TerrainBuild
from weather_summaries.models import WeatherSnapshot


class EstimateUpdate(models.Model):
    """Identify one complete eight-date estimate publication."""

    id = models.BigAutoField(primary_key=True)
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    cell_key = models.CharField(max_length=120)
    assessment_date = models.DateField()
    calculated_at = models.DateTimeField()
    snapshot = models.ForeignKey(
        WeatherSnapshot,
        on_delete=models.PROTECT,
        related_name="estimate_updates",
    )
    forest_build = models.ForeignKey(
        ForestBuild,
        on_delete=models.PROTECT,
        related_name="estimate_updates",
    )
    terrain_build = models.ForeignKey(
        TerrainBuild,
        on_delete=models.PROTECT,
        related_name="estimate_updates",
    )
    method_version = models.CharField(max_length=120)
    row_count = models.PositiveIntegerField()
    input_fingerprint = models.CharField(max_length=64, unique=True)
    tree_fingerprint = models.CharField(max_length=64, default="", blank=True)
    tree_inputs = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "cell_key",
                    "assessment_date",
                    "snapshot",
                    "forest_build",
                    "terrain_build",
                    "method_version",
                    "tree_fingerprint",
                ],
                name="estimate_update_input_tuple_unique",
            ),
            models.CheckConstraint(
                condition=Q(row_count__gte=0),
                name="estimate_update_row_count_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["cell_key", "assessment_date"],
                name="estimate_update_cell_date_idx",
            ),
        ]

    @property
    def update_id(self) -> uuid.UUID:
        """Return the public UUID used by map and detail reads."""
        return self.public_id

    @property
    def uuid(self) -> uuid.UUID:
        """Return the public UUID under the short model-facing name."""
        return self.public_id

    @property
    def input_key(self) -> str:
        """Return the immutable input tuple fingerprint."""
        return self.input_fingerprint

    @property
    def input_tuple(self) -> tuple[str, str, int, int, int, str, str]:
        """Return the immutable identities used by this publication."""
        return (
            self.cell_key,
            self.assessment_date.isoformat(),
            self.snapshot_id,
            self.forest_build_id,
            self.terrain_build_id,
            self.method_version,
            self.tree_fingerprint,
        )


class EstimateTask(models.Model):
    """Track one durable estimate calculation independently from weather."""

    class State(models.TextChoices):
        WAITING = "waiting", "Waiting"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    snapshot = models.ForeignKey(
        WeatherSnapshot,
        on_delete=models.PROTECT,
        related_name="estimate_tasks",
    )
    cell_key = models.CharField(max_length=120)
    assessment_date = models.DateField()
    forest_build_version = models.CharField(max_length=120)
    terrain_build_version = models.CharField(max_length=120)
    calculation_version = models.CharField(max_length=64, default="", blank=True)
    published_update = models.ForeignKey(
        EstimateUpdate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks",
    )
    input_fingerprint = models.CharField(max_length=64, unique=True)
    state = models.CharField(max_length=20, choices=State.choices, default=State.WAITING)
    task_id = models.UUIDField(null=True, blank=True, unique=True)
    queue_token = models.UUIDField(null=True, blank=True, unique=True)
    attempt_count = models.PositiveIntegerField(default=0)
    failure_reason = models.TextField(blank=True, default="")
    queued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "cell_key", "assessment_date", "forest_build_version", "terrain_build_version", "calculation_version"],
                name="estimate_task_input_tuple_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["state", "assessment_date"], name="estimate_task_state_date_idx"),
        ]


class EstimateResult(models.Model):
    """Store eight compact values for one forest square in one update."""

    update = models.ForeignKey(
        EstimateUpdate,
        on_delete=models.CASCADE,
        related_name="results",
        db_index=False,
    )
    forest_cell = models.ForeignKey(
        ForestCell,
        on_delete=models.PROTECT,
        related_name="estimate_results",
        db_index=False,
    )
    values = models.BinaryField(max_length=8)
    pk = models.CompositePrimaryKey("update_id", "forest_cell_id")

    @property
    def percentages(self) -> bytes:
        """Return the compact eight-day result bytes."""
        return bytes(self.values)

    @property
    def estimate_update(self) -> EstimateUpdate:
        """Return the update associated with this result row."""
        return self.update


class HostTreeCache(models.Model):
    """Cache only requested squares against an immutable source fingerprint."""

    source_version = models.CharField(max_length=64)
    cell_id = models.CharField(max_length=80)
    values = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_version", "cell_id"], name="host_tree_source_cell_unique",
            ),
        ]
