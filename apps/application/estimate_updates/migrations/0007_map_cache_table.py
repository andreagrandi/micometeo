from django.core.management import call_command
from django.db import migrations

MAP_CACHE_TABLE = "sporameteo_map_cache"


def create_map_cache_table(apps, schema_editor) -> None:
    """Create the table behind the shared map cache when it is missing."""
    call_command(
        "createcachetable",
        MAP_CACHE_TABLE,
        database=schema_editor.connection.alias,
        verbosity=0,
    )


def drop_map_cache_table(apps, schema_editor) -> None:
    """Remove the table behind the shared map cache."""
    quoted = schema_editor.connection.ops.quote_name(MAP_CACHE_TABLE)
    schema_editor.execute(f"DROP TABLE IF EXISTS {quoted}")


class Migration(migrations.Migration):

    dependencies = [
        ("estimate_updates", "0006_forecast_runs"),
    ]

    operations = [
        migrations.RunPython(create_map_cache_table, drop_map_cache_table),
    ]
