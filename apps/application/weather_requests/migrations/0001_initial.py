from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="WeatherQuotaLock",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("id", 1)),
                        name="weather_quota_lock_singleton",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="WeatherRequest",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("request_digest", models.CharField(max_length=64, unique=True)),
                ("canonical_spec", models.JSONField(default=dict)),
                ("forest_build_version", models.CharField(max_length=120)),
                ("provenance", models.JSONField(default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("retry_at", models.DateTimeField(blank=True, null=True)),
                ("latest_provider_message", models.TextField(blank=True, default="")),
                ("first_requested_at", models.DateTimeField(blank=True, null=True)),
                ("last_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("failed_at", models.DateTimeField(blank=True, null=True)),
                ("completion_metadata", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["created_at", "id"],
                "indexes": [
                    models.Index(fields=["status", "retry_at"], name="weather_re_status_32d5d1_idx"),
                    models.Index(
                        fields=["forest_build_version", "status"],
                        name="weather_re_forest__e22f93_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="WeatherRequestAttempt",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("attempt_number", models.PositiveIntegerField()),
                ("reserved_at", models.DateTimeField()),
                (
                    "reservation_weight",
                    models.DecimalField(decimal_places=6, max_digits=18, validators=[]),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("reservation", "Reserved before network I/O"),
                            ("success", "Success"),
                            ("retry", "Retry later"),
                            ("refused", "Provider refused"),
                            ("failed", "Permanent failure"),
                            ("crashed", "Worker stopped after reservation"),
                        ],
                        default="reservation",
                        max_length=20,
                    ),
                ),
                ("http_status", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("full_message", models.TextField(blank=True, default="")),
                ("retry_at", models.DateTimeField(blank=True, null=True)),
                (
                    "duration_seconds",
                    models.DecimalField(
                        blank=True,
                        decimal_places=3,
                        max_digits=14,
                        null=True,
                    ),
                ),
                (
                    "request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attempts",
                        to="weather_requests.weatherrequest",
                    ),
                ),
            ],
            options={
                "ordering": ["request", "attempt_number"],
                "indexes": [
                    models.Index(fields=["reserved_at"], name="weather_re_reserved_610c3e_idx"),
                    models.Index(
                        fields=["outcome", "reserved_at"],
                        name="weather_re_outcome_52a052_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("request", "attempt_number"),
                        name="weather_request_attempt_number_unique",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("reservation_weight__gt", 0)),
                        name="weather_request_attempt_weight_positive",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="WeatherRequestMember",
            fields=[
                (
                    "id",
                    models.BigAutoField(primary_key=True, serialize=False),
                ),
                ("position", models.PositiveIntegerField()),
                ("weather_cell_key", models.CharField(max_length=80)),
                ("latitude", models.DecimalField(decimal_places=2, max_digits=8)),
                ("longitude", models.DecimalField(decimal_places=2, max_digits=8)),
                (
                    "request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="members",
                        to="weather_requests.weatherrequest",
                    ),
                ),
            ],
            options={
                "ordering": ["position"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("request", "position"),
                        name="weather_request_member_position_unique",
                    ),
                    models.UniqueConstraint(
                        fields=("request", "weather_cell_key"),
                        name="weather_request_member_key_unique",
                    ),
                ],
            },
        ),
    ]
