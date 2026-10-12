import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("national_forest", "0003_forestbuild_source_chunk_size_m_and_more"),
        ("national_terrain", "0002_terrain_build_algorithm_v2"),
        ("weather_summaries", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EstimateUpdate",
            fields=[
                (
                    "id",
                    models.BigAutoField(primary_key=True, serialize=False),
                ),
                (
                    "public_id",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("cell_key", models.CharField(max_length=120)),
                ("assessment_date", models.DateField()),
                ("calculated_at", models.DateTimeField()),
                ("method_version", models.CharField(max_length=120)),
                ("row_count", models.PositiveIntegerField()),
                ("input_fingerprint", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "forest_build",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="estimate_updates",
                        to="national_forest.forestbuild",
                    ),
                ),
                (
                    "snapshot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="estimate_updates",
                        to="weather_summaries.weathersnapshot",
                    ),
                ),
                (
                    "terrain_build",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="estimate_updates",
                        to="national_terrain.terrainbuild",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["cell_key", "assessment_date"],
                        name="estimate_update_cell_date_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("row_count__gte", 0)),
                        name="estimate_update_row_count_nonnegative",
                    ),
                    models.UniqueConstraint(
                        fields=(
                            "cell_key",
                            "assessment_date",
                            "snapshot",
                            "forest_build",
                            "terrain_build",
                            "method_version",
                        ),
                        name="estimate_update_input_tuple_unique",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="EstimateTask",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("cell_key", models.CharField(max_length=120)),
                ("assessment_date", models.DateField()),
                ("forest_build_version", models.CharField(max_length=120)),
                ("terrain_build_version", models.CharField(max_length=120)),
                (
                    "published_update",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="tasks",
                        to="estimate_updates.estimateupdate",
                    ),
                ),
                ("input_fingerprint", models.CharField(max_length=64, unique=True)),
                ("state", models.CharField(choices=[("waiting", "Waiting"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed")], default="waiting", max_length=20)),
                ("task_id", models.UUIDField(blank=True, null=True, unique=True)),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("failure_reason", models.TextField(blank=True, default="")),
                ("queued_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "snapshot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="estimate_tasks",
                        to="weather_summaries.weathersnapshot",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["state", "assessment_date"],
                        name="estimate_task_state_date_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=(
                            "snapshot",
                            "cell_key",
                            "assessment_date",
                            "forest_build_version",
                            "terrain_build_version",
                        ),
                        name="estimate_task_input_tuple_unique",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="EstimateResult",
            fields=[
                (
                    "update",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="results",
                        to="estimate_updates.estimateupdate",
                    ),
                ),
                (
                    "forest_cell",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="estimate_results",
                        to="national_forest.forestcell",
                    ),
                ),
                ("values", models.BinaryField(max_length=8)),
                (
                    "pk",
                    models.CompositePrimaryKey(
                        "update_id",
                        "forest_cell_id",
                        blank=True,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
            ],
        ),
    ]
