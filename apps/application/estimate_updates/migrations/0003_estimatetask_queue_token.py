from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("estimate_updates", "0002_forest_cell_weather_lookup_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="estimatetask",
            name="queue_token",
            field=models.UUIDField(blank=True, null=True, unique=True),
        ),
    ]
