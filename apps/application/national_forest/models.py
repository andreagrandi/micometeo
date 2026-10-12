from __future__ import annotations

import uuid

from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import F, Q

from national_grid.models import GridBuild, GridBuildCell, GridChunk


def validate_source_edge(value: int) -> None:
    """Require source bounds to use the ten metre native pixel alignment."""
    if value % 10:
        raise ValidationError("Forest source bounds must be multiples of 10 metres.")


class ForestBuild(models.Model):
    """Record one immutable forest calculation joined to a completed grid."""

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        RUNNING = "running", "Running"
        FAILED = "failed", "Failed"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    version = models.CharField(max_length=120, unique=True)
    grid_build = models.ForeignKey(
        GridBuild,
        on_delete=models.PROTECT,
        related_name="forest_builds",
    )
    fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    algorithm_version = models.CharField(max_length=80, default="national-forest-v1")
    source_release = models.CharField(max_length=120, default="HRL Forest Type 2018")
    source_metadata = models.JSONField(default=dict)
    service_url = models.URLField(
        max_length=500,
        default=(
            "https://image.discomap.eea.europa.eu/arcgis/rest/services/"
            "GioLandPublic/HRL_ForestType_2018/ImageServer"
        ),
    )
    catalogue_url = models.URLField(
        max_length=500,
        default=(
            "https://sdi.eea.europa.eu/catalogue/srv/api/records/"
            "59b0620c-7bb4-4c82-b3ce-f16715573137"
        ),
    )
    source_resolution_m = models.PositiveIntegerField(default=10)
    source_crs = models.CharField(max_length=32, default="EPSG:3035")
    resampling = models.CharField(max_length=40, default="nearest")
    licence = models.TextField(
        default="Copernicus Land Monitoring Service data, free and open access under EU Regulation 1159/2013."
    )
    credit = models.TextField(
        default="© European Union, Copernicus Land Monitoring Service 2018, European Environment Agency"
    )
    planned_chunk_count = models.PositiveIntegerField(default=0)
    source_chunk_size_m = models.PositiveIntegerField(null=True, blank=True)
    completed_chunk_count = models.PositiveIntegerField(default=0)
    failed_chunk_count = models.PositiveIntegerField(default=0)
    cell_count = models.PositiveIntegerField(default=0)
    forest_cell_count = models.PositiveIntegerField(default=0)
    weather_cell_count = models.PositiveIntegerField(default=0)
    source_gap_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    layer_path = models.CharField(max_length=1000, blank=True, default="")
    layer_sha256 = models.CharField(max_length=64, blank=True, default="")
    layer_gzip_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    layer_raw_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(completed_chunk_count__lte=F("planned_chunk_count")),
                name="forest_build_completed_chunks_bounded",
            ),
            models.CheckConstraint(
                condition=Q(source_resolution_m__gt=0),
                name="forest_build_resolution_positive",
            ),
        ]

    @property
    def source_license(self) -> str:
        """Return the source licence using the American spelling used by APIs."""
        return self.licence

    @property
    def source_service_url(self) -> str:
        """Return the ArcGIS service URL."""
        return self.service_url

    @property
    def source_catalogue_url(self) -> str:
        """Return the EEA catalogue record URL."""
        return self.catalogue_url

    def clean(self) -> None:
        """Require the joined grid build to have finished before processing."""
        super().clean()
        if self.grid_build_id and self.grid_build.status != GridBuild.Status.COMPLETED:
            raise ValidationError("A forest build requires a completed national grid build.")

    def save(self, *args, **kwargs):
        """Keep the input fingerprint fixed after the build is created."""
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            previous = type(self).objects.only("fingerprint").get(pk=self.pk)
            if previous.fingerprint != self.fingerprint:
                raise ValueError("A forest build fingerprint cannot change.")
        super().save(*args, **kwargs)


class ForestChunk(models.Model):
    """Track one aligned Copernicus request and its resumable state."""

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        RUNNING = "running", "Running"
        FAILED = "failed", "Failed"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    build = models.ForeignKey(ForestBuild, on_delete=models.CASCADE, related_name="chunks")
    grid_chunk = models.ForeignKey(
        GridChunk,
        on_delete=models.PROTECT,
        related_name="forest_chunks",
    )
    west_e = models.IntegerField(validators=[validate_source_edge])
    south_n = models.IntegerField(validators=[validate_source_edge])
    east_e = models.IntegerField(validators=[validate_source_edge])
    north_n = models.IntegerField(validators=[validate_source_edge])
    request_key = models.CharField(max_length=64, default="")
    request_sha256 = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    cell_count = models.PositiveIntegerField(default=0)
    source_bytes = models.PositiveBigIntegerField(default=0)
    source_sha256 = models.CharField(max_length=64, blank=True, default="")
    source_retrieved_at = models.CharField(max_length=80, blank=True, default="")
    source_crs_wkt = models.TextField(blank=True, default="")
    source_path = models.CharField(max_length=1000, blank=True, default="")
    source_metadata = models.JSONField(default=dict)
    attempt_count = models.PositiveIntegerField(default=0)
    failure_reason = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["build", "west_e", "south_n", "east_e", "north_n"],
                name="forest_chunk_build_bounds_unique",
            ),
            models.CheckConstraint(
                condition=Q(east_e__gt=F("west_e")),
                name="forest_chunk_width_positive",
            ),
            models.CheckConstraint(
                condition=Q(north_n__gt=F("south_n")),
                name="forest_chunk_height_positive",
            ),
        ]

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """Return the request box in EPSG:3035 metres."""
        return (self.west_e, self.south_n, self.east_e, self.north_n)

    def clean(self) -> None:
        """Check dimensions and alignment before a request is stored."""
        super().clean()
        if self.east_e <= self.west_e or self.north_n <= self.south_n:
            raise ValidationError("A forest chunk must have positive width and height.")
        if any(value % 10 for value in self.bounds):
            raise ValidationError("Forest chunk bounds must be multiples of 10 metres.")
        if self.grid_chunk_id:
            grid_bounds = (
                self.grid_chunk.west_e,
                self.grid_chunk.south_n,
                self.grid_chunk.east_e,
                self.grid_chunk.north_n,
            )
            if not (
                grid_bounds[0] <= self.west_e <= self.east_e <= grid_bounds[2]
                and grid_bounds[1] <= self.south_n <= self.north_n <= grid_bounds[3]
            ):
                raise ValidationError("Forest chunk bounds must lie inside its grid chunk.")


class ForestCell(models.Model):
    """Store one forest summary joined to one grid membership."""

    class LeafType(models.TextChoices):
        NO_FOREST = "no forest", "No forest"
        BROADLEAF = "broadleaf", "Broadleaf"
        CONIFER = "conifer", "Conifer"
        MIXED = "mixed", "Mixed"

    LEAF_TYPE_CHOICES = (
        (LeafType.NO_FOREST, LeafType.NO_FOREST.label),
        (LeafType.BROADLEAF, LeafType.BROADLEAF.label),
        (LeafType.CONIFER, LeafType.CONIFER.label),
        (LeafType.MIXED, LeafType.MIXED.label),
    )

    id = models.BigAutoField(primary_key=True)
    build = models.ForeignKey(ForestBuild, on_delete=models.CASCADE, related_name="cells")
    grid_build_cell = models.ForeignKey(
        GridBuildCell,
        on_delete=models.PROTECT,
        related_name="forest_cells",
    )
    chunk = models.ForeignKey(ForestChunk, on_delete=models.PROTECT, related_name="cells")
    total_pixel_count = models.PositiveIntegerField(default=0)
    valid_pixel_count = models.PositiveIntegerField(default=0)
    forest_pixel_count = models.PositiveIntegerField(default=0)
    broadleaf_pixel_count = models.PositiveIntegerField(default=0)
    conifer_pixel_count = models.PositiveIntegerField(default=0)
    unclassifiable_pixel_count = models.PositiveIntegerField(default=0)
    outside_pixel_count = models.PositiveIntegerField(default=0)
    valid_coverage = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    coverage_quality = models.CharField(max_length=20, default="unavailable")
    forest_share = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    broadleaf_share = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
    )
    leaf_type = models.CharField(
        max_length=20,
        choices=LEAF_TYPE_CHOICES,
        null=True,
        blank=True,
    )
    is_forest = models.BooleanField(null=True, blank=True)
    missing_reason = models.CharField(max_length=100, blank=True, default="")
    weather_latitude = models.FloatField(null=True, blank=True)
    weather_longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["build", "grid_build_cell"],
                name="forest_cell_build_grid_cell_unique",
            ),
            models.CheckConstraint(
                condition=Q(forest_pixel_count__lte=F("valid_pixel_count")),
                name="forest_cell_forest_pixels_bounded",
            ),
            models.CheckConstraint(
                condition=Q(valid_pixel_count__lte=F("total_pixel_count")),
                name="forest_cell_valid_pixels_bounded",
            ),
            models.CheckConstraint(
                condition=Q(broadleaf_pixel_count__lte=F("forest_pixel_count")),
                name="forest_cell_broadleaf_pixels_bounded",
            ),
            models.CheckConstraint(
                condition=Q(conifer_pixel_count__lte=F("forest_pixel_count")),
                name="forest_cell_conifer_pixels_bounded",
            ),
            models.CheckConstraint(
                condition=Q(coverage_quality__in=["high", "low", "unavailable"]),
                name="forest_cell_coverage_quality_allowed",
            ),
            models.CheckConstraint(
                condition=Q(forest_share__isnull=True)
                | Q(forest_share__gte=0.0, forest_share__lte=1.0),
                name="forest_cell_forest_share_bounded",
            ),
            models.CheckConstraint(
                condition=Q(broadleaf_share__isnull=True)
                | Q(broadleaf_share__gte=0.0, broadleaf_share__lte=1.0),
                name="forest_cell_broadleaf_share_bounded",
            ),
            models.CheckConstraint(
                condition=Q(leaf_type__isnull=True)
                | Q(leaf_type__in=["no forest", "broadleaf", "conifer", "mixed"]),
                name="forest_cell_leaf_type_allowed",
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_forest=True, weather_latitude__isnull=False, weather_longitude__isnull=False)
                    | Q(is_forest=False, weather_latitude__isnull=True, weather_longitude__isnull=True)
                    | Q(is_forest__isnull=True, weather_latitude__isnull=True, weather_longitude__isnull=True)
                ),
                name="forest_cell_weather_only_for_forest",
            ),
        ]

    @property
    def total_pixels(self) -> int:
        """Return the total source pixel count."""
        return self.total_pixel_count

    @property
    def valid_pixels(self) -> int:
        """Return the valid source pixel count."""
        return self.valid_pixel_count

    @property
    def valid_coverage_fraction(self) -> float:
        """Return the valid source share of the square."""
        return self.valid_coverage

    @property
    def coverage_reliability(self) -> str:
        """Return the quality label for valid source coverage."""
        return self.coverage_quality

    def clean(self) -> None:
        """Check source counts and keep weather values on forest cells only."""
        super().clean()
        counts = {
            "valid_pixel_count": self.valid_pixel_count,
            "forest_pixel_count": self.forest_pixel_count,
            "broadleaf_pixel_count": self.broadleaf_pixel_count,
            "conifer_pixel_count": self.conifer_pixel_count,
            "unclassifiable_pixel_count": self.unclassifiable_pixel_count,
            "outside_pixel_count": self.outside_pixel_count,
        }
        if self.valid_pixel_count + self.unclassifiable_pixel_count + self.outside_pixel_count != self.total_pixel_count:
            raise ValidationError("Forest pixel counts must add up to the total count.")
        if self.broadleaf_pixel_count + self.conifer_pixel_count != self.forest_pixel_count:
            raise ValidationError("Broadleaf and conifer counts must add up to forest count.")
        if any(value < 0 for value in counts.values()):
            raise ValidationError("Forest pixel counts cannot be negative.")
        if self.is_forest is True:
            if self.weather_latitude is None or self.weather_longitude is None:
                raise ValidationError("Forest cells need both weather coordinates.")
        elif self.weather_latitude is not None or self.weather_longitude is not None:
            raise ValidationError("Only forest cells may have weather coordinates.")
        if self.leaf_type not in {None, "no forest", "broadleaf", "conifer", "mixed"}:
            raise ValidationError("Forest leaf type is not supported.")
        if self.forest_share is not None and not 0 <= self.forest_share <= 1:
            raise ValidationError("Forest share must be between zero and one.")
        if self.broadleaf_share is not None and not 0 <= self.broadleaf_share <= 1:
            raise ValidationError("Broadleaf share must be between zero and one.")
