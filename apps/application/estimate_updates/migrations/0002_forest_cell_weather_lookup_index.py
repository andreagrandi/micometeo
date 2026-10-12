from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("estimate_updates", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                'CREATE INDEX IF NOT EXISTS "estimate_forest_cell_weather_lookup_idx" '
                'ON "national_forest_forestcell" '
                '("build_id", "weather_latitude", "weather_longitude") '
                'INCLUDE ("id", "grid_build_cell_id", "forest_share") '
                'WHERE "is_forest" AND "weather_latitude" IS NOT NULL '
                'AND "weather_longitude" IS NOT NULL'
            ),
            reverse_sql=(
                'DROP INDEX IF EXISTS "estimate_forest_cell_weather_lookup_idx"'
            ),
        ),
    ]
