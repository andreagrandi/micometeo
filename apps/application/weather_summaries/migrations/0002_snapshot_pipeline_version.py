from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("weather_summaries", "0001_initial")]
    operations = [
        migrations.AddField(model_name="weathersnapshot", name="pipeline_version",
                            field=models.PositiveSmallIntegerField(default=1)),
        migrations.RemoveConstraint(model_name="weathersnapshot", name="weather_snapshot_cell_assessment_unique"),
        migrations.AddConstraint(model_name="weathersnapshot", constraint=models.UniqueConstraint(
            fields=("cell_key", "assessment_date", "pipeline_version"), name="weather_snapshot_cell_assessment_unique")),
    ]
