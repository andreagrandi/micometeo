from django.db import migrations

OLD_TABLE = "micometeo_map_cache"
NEW_TABLE = "sporameteo_map_cache"


def rename_table(*, schema_editor, old: str, new: str) -> None:
    """Rename the map cache table when the old name is still in use."""
    ops = schema_editor.connection.ops
    tables = schema_editor.connection.introspection.table_names()
    if old in tables and new not in tables:
        schema_editor.execute(
            f"ALTER TABLE {ops.quote_name(old)} RENAME TO {ops.quote_name(new)}"
        )


def forwards(apps, schema_editor) -> None:
    """Move the map cache to the table name used after the SporaMeteo rename."""
    rename_table(schema_editor=schema_editor, old=OLD_TABLE, new=NEW_TABLE)


def backwards(apps, schema_editor) -> None:
    """Move the map cache back to the Micometeo table name."""
    rename_table(schema_editor=schema_editor, old=NEW_TABLE, new=OLD_TABLE)


class Migration(migrations.Migration):

    dependencies = [
        ("estimate_updates", "0007_map_cache_table"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
