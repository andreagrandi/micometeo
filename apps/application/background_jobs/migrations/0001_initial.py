import uuid

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="RepresentativeInput",
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
                ("value", models.PositiveIntegerField(default=1)),
                (
                    "delay_seconds",
                    models.FloatField(
                        default=0.0,
                        validators=[
                            django.core.validators.MinValueValidator(0.0),
                            django.core.validators.MaxValueValidator(5.0),
                        ],
                    ),
                ),
                ("fail_first_attempt", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["created_at", "id"],
                "constraints": [
                    models.CheckConstraint(
                        condition=Q(delay_seconds__gte=0, delay_seconds__lte=5),
                        name="representative_input_delay_bounded",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="BackgroundJob",
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
                ("logical_key", models.CharField(max_length=255, unique=True)),
                ("job_name", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "input",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="background_jobs",
                        to="background_jobs.representativeinput",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="BackgroundJobAttempt",
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
                (
                    "attempt_number",
                    models.PositiveIntegerField(),
                ),
                ("task_id", models.UUIDField(blank=True, null=True, unique=True)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("waiting", "Waiting"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="waiting",
                        max_length=20,
                    ),
                ),
                ("queued_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("failure_reason", models.TextField(blank=True, default="")),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attempts",
                        to="background_jobs.backgroundjob",
                    ),
                ),
                (
                    "retry_of",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="retries",
                        to="background_jobs.backgroundjobattempt",
                    ),
                ),
            ],
            options={
                "ordering": ["attempt_number"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("job", "attempt_number"),
                        name="background_job_attempt_number_unique",
                    ),
                    models.UniqueConstraint(
                        condition=Q(state__in=["waiting", "running"]),
                        fields=("job",),
                        name="background_job_one_active_attempt",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="RepresentativeResult",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("result_value", models.PositiveIntegerField()),
                ("completed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "job",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="result",
                        to="background_jobs.backgroundjob",
                    ),
                ),
            ],
        ),
    ]
