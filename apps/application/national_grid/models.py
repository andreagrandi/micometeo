import uuid

from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Q

from sporameteo.finds.grid import CELL_SIZE_M, parse_cell_id


def validate_cell_corner(value: int) -> None:
    """Validate the fixed 500 metre alignment used by the stored grid."""
    if value % CELL_SIZE_M:
        raise ValidationError(f"Grid corners must be multiples of {CELL_SIZE_M} metres.")


class GridBuild(models.Model):
    """Record one immutable set of national grid inputs and its progress."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    version = models.CharField(max_length=120, unique=True)
    fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    cell_size_m = models.PositiveIntegerField(default=500)
    chunk_size_m = models.PositiveIntegerField(default=25_000)
    grid_crs = models.CharField(max_length=32, default="EPSG:3035")
    source_crs = models.CharField(max_length=32, default="EPSG:32632")
    algorithm_version = models.CharField(max_length=50, default="national-grid-v1")
    source_metadata = models.JSONField(default=dict)
    planned_chunk_count = models.PositiveIntegerField(default=0)
    completed_chunk_count = models.PositiveIntegerField(default=0)
    cell_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(cell_size_m__gt=0), name="grid_build_cell_size_positive"),
            models.CheckConstraint(
                condition=Q(chunk_size_m__gt=0), name="grid_build_chunk_size_positive"
            ),
            models.CheckConstraint(
                condition=Q(completed_chunk_count__lte=models.F("planned_chunk_count")),
                name="grid_build_completed_chunks_bounded",
            ),
        ]

    def save(self, *args, **kwargs):
        """Keep the input fingerprint fixed after the build is created."""
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            previous = type(self).objects.only("fingerprint").get(pk=self.pk)
            if previous.fingerprint != self.fingerprint:
                raise ValueError("A grid build fingerprint cannot change.")
        super().save(*args, **kwargs)


class Municipality(models.Model):
    """Store one ISTAT municipality border, shared by every build."""

    istat_code = models.CharField(max_length=6, primary_key=True)
    name = models.CharField(max_length=120)
    region_code = models.CharField(max_length=2)
    geometry = models.MultiPolygonField(srid=3035, spatial_index=True)


class GridCell(models.Model):
    """Store one stable 500 metre square shared by every build."""

    cell_id = models.CharField(max_length=80, primary_key=True)
    corner_e = models.IntegerField(validators=[validate_cell_corner])
    corner_n = models.IntegerField(validators=[validate_cell_corner])
    geometry = models.PolygonField(srid=3035, spatial_index=True)
    municipality = models.ForeignKey(
        Municipality,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cells",
    )

    def clean(self) -> None:
        """Check that the stable ID and stored lower-left corner agree."""
        try:
            address = parse_cell_id(self.cell_id, expected_size_m=CELL_SIZE_M)
        except ValueError as exc:
            raise ValidationError({"cell_id": str(exc)}) from exc
        if (address.corner_e, address.corner_n) != (self.corner_e, self.corner_n):
            raise ValidationError("The cell ID and corners must describe the same square.")


class GridRegion(models.Model):
    """Store one ISTAT region geometry for one build."""

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    build = models.ForeignKey(GridBuild, on_delete=models.CASCADE, related_name="regions")
    istat_code = models.CharField(max_length=20)
    name = models.CharField(max_length=120)
    geometry = models.MultiPolygonField(srid=3035, spatial_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["build", "istat_code"], name="grid_region_build_code_unique"
            ),
            models.UniqueConstraint(fields=["build", "name"], name="grid_region_build_name_unique"),
        ]


class GridChunk(models.Model):
    """Track one aligned build chunk and its resumable state."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    build = models.ForeignKey(GridBuild, on_delete=models.CASCADE, related_name="chunks")
    west_e = models.IntegerField(validators=[validate_cell_corner])
    south_n = models.IntegerField(validators=[validate_cell_corner])
    east_e = models.IntegerField(validators=[validate_cell_corner])
    north_n = models.IntegerField(validators=[validate_cell_corner])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    cell_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["build", "west_e", "south_n"], name="grid_chunk_build_origin_unique"
            ),
            models.CheckConstraint(condition=Q(east_e__gt=models.F("west_e")), name="grid_chunk_width_positive"),
            models.CheckConstraint(condition=Q(north_n__gt=models.F("south_n")), name="grid_chunk_height_positive"),
        ]


class GridBuildCell(models.Model):
    """Store a cell's Italian land and owning region in one build."""

    id = models.BigAutoField(primary_key=True)
    build = models.ForeignKey(GridBuild, on_delete=models.CASCADE, related_name="memberships")
    cell = models.ForeignKey(GridCell, on_delete=models.PROTECT, related_name="build_memberships")
    chunk = models.ForeignKey(GridChunk, on_delete=models.PROTECT, related_name="memberships")
    owner_region = models.ForeignKey(
        GridRegion,
        on_delete=models.PROTECT,
        related_name="owned_cells",
    )
    land_geometry = models.MultiPolygonField(srid=3035, spatial_index=True)
    land_share = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["build", "cell"], name="grid_build_cell_unique"),
            models.CheckConstraint(
                condition=Q(land_share__gt=0, land_share__lte=1),
                name="grid_build_cell_land_share_bounded",
            ),
        ]
