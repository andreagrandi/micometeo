from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PlaceSearchCache",
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
                ("normalized_query", models.CharField(max_length=120)),
                ("language", models.CharField(default="it", max_length=12)),
                ("endpoint", models.URLField(max_length=500)),
                ("results", models.JSONField(default=list)),
                ("fetched_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["normalized_query", "language"],
                        name="place_search_cache_lookup_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("normalized_query", "language", "endpoint"),
                        name="place_search_cache_query_language_endpoint_unique",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PlaceSearchThrottle",
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
                ("last_request_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
