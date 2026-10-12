from __future__ import annotations

import uuid

from django.contrib.gis.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import F, Q

from national_grid.models import GridBuild, GridBuildCell, GridChunk


class TerrainBuild(models.Model):
    """Record one terrain calculation for one completed national grid."""

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    version = models.CharField(max_length=120, unique=True)
    grid_build = models.ForeignKey(GridBuild, on_delete=models.PROTECT, related_name="terrain_builds")
    algorithm_version = models.CharField(max_length=50, default="national-terrain-v2")
    fingerprint = models.CharField(max_length=64)
    grid_fingerprint = models.CharField(max_length=64)
    source_manifest_fingerprint = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    source_metadata = models.JSONField(default=dict)
    planned_chunk_count = models.PositiveIntegerField(default=0)
    completed_chunk_count = models.PositiveIntegerField(default=0)
    result_count = models.PositiveIntegerField(default=0)
    source_gap_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(completed_chunk_count__lte=F("planned_chunk_count")),
                name="terrain_build_completed_chunks_bounded",
            ),
        ]


    def save(self, *args, **kwargs):
        """Keep a terrain fingerprint fixed after the build is created."""
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            previous = type(self).objects.only("fingerprint").get(pk=self.pk)
            if previous.fingerprint != self.fingerprint:
                raise ValueError("A terrain build fingerprint cannot change.")
        super().save(*args, **kwargs)


class TerrainChunk(models.Model):
    """Track one terrain result for one national grid chunk."""

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        RUNNING = "running", "Running"
        FAILED = "failed", "Failed"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    build = models.ForeignKey(TerrainBuild, on_delete=models.CASCADE, related_name="chunks")
    grid_chunk = models.ForeignKey(GridChunk, on_delete=models.PROTECT, related_name="terrain_chunks")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    result_count = models.PositiveIntegerField(default=0)
    source_gap_count = models.PositiveIntegerField(default=0)
    downloaded_tile_count = models.PositiveIntegerField(default=0)
    reused_tile_count = models.PositiveIntegerField(default=0)
    downloaded_bytes = models.PositiveBigIntegerField(default=0)
    reused_bytes = models.PositiveBigIntegerField(default=0)
    source_bytes = models.PositiveBigIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["build", "grid_chunk"], name="terrain_chunk_build_grid_chunk_unique"
            ),
        ]


class TerrainSourceTile(models.Model):
    """Keep one source tile manifest entry for one terrain build."""

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        CONFIRMED_MISSING = "confirmed_missing", "Confirmed missing"
        FAILED = "failed", "Failed"

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    build = models.ForeignKey(TerrainBuild, on_delete=models.CASCADE, related_name="source_tiles")
    tile_name = models.CharField(max_length=80)
    status = models.CharField(max_length=30, choices=Status.choices)
    url = models.URLField(max_length=500)
    release = models.CharField(max_length=160)
    last_modified = models.CharField(max_length=120, blank=True, default="")
    retrieved_at = models.DateTimeField(null=True, blank=True)
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    crs = models.CharField(max_length=64, blank=True, default="")
    native_pixel_m = models.FloatField(null=True, blank=True)
    vertical_datum = models.CharField(max_length=80, blank=True, default="")
    credit = models.TextField()
    error_detail = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["build", "tile_name"], name="terrain_source_tile_build_name_unique"
            ),
            models.CheckConstraint(
                condition=Q(size_bytes__isnull=True) | Q(size_bytes__gte=0),
                name="terrain_source_tile_size_nonnegative",
            ),
        ]


class TerrainChunkSource(models.Model):
    """Link a processed chunk to each source tile it used or found missing."""

    id = models.BigAutoField(primary_key=True)
    chunk = models.ForeignKey(TerrainChunk, on_delete=models.CASCADE, related_name="source_links")
    tile = models.ForeignKey(TerrainSourceTile, on_delete=models.PROTECT, related_name="chunk_links")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["chunk", "tile"], name="terrain_chunk_source_chunk_tile_unique"
            ),
        ]


class TerrainCell(models.Model):
    """Store terrain values joined to one national grid membership."""

    id = models.BigAutoField(primary_key=True)
    build = models.ForeignKey(TerrainBuild, on_delete=models.CASCADE, related_name="cells")
    grid_build_cell = models.ForeignKey(
        GridBuildCell,
        on_delete=models.PROTECT,
        related_name="terrain_cells",
    )
    chunk = models.ForeignKey(TerrainChunk, on_delete=models.PROTECT, related_name="cells")
    altitude_m = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-500.0), MaxValueValidator(10000.0)],
    )
    slope_deg = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(90.0)],
    )
    aspect_deg = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(360.0)],
    )
    altitude_valid_fraction = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    slope_valid_fraction = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    aspect_valid_fraction = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    altitude_quality = models.CharField(max_length=20, blank=True, default="")
    slope_quality = models.CharField(max_length=20, blank=True, default="")
    aspect_quality = models.CharField(max_length=20, blank=True, default="")
    source_gap = models.BooleanField(default=False)
    source_gap_detail = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["build", "grid_build_cell"], name="terrain_cell_build_grid_cell_unique"
            ),
            models.CheckConstraint(
                condition=Q(aspect_deg__isnull=True)
                | Q(aspect_deg__gte=0.0, aspect_deg__lt=360.0),
                name="terrain_cell_aspect_range",
            ),
            models.CheckConstraint(
                condition=Q(altitude_m__isnull=True)
                | Q(altitude_m__gte=-500.0, altitude_m__lte=10000.0),
                name="terrain_cell_altitude_range",
            ),
            models.CheckConstraint(
                condition=Q(slope_deg__isnull=True)
                | Q(slope_deg__gte=0.0, slope_deg__lte=90.0),
                name="terrain_cell_slope_range",
            ),
            models.CheckConstraint(
                condition=Q(altitude_valid_fraction__gte=0.0)
                & Q(altitude_valid_fraction__lte=1.0),
                name="terrain_cell_altitude_fraction_range",
            ),
            models.CheckConstraint(
                condition=Q(slope_valid_fraction__gte=0.0)
                & Q(slope_valid_fraction__lte=1.0),
                name="terrain_cell_slope_fraction_range",
            ),
            models.CheckConstraint(
                condition=Q(aspect_valid_fraction__gte=0.0)
                & Q(aspect_valid_fraction__lte=1.0),
                name="terrain_cell_aspect_fraction_range",
            ),
        ]
