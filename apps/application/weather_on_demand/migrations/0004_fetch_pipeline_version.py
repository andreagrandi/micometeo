from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("weather_on_demand", "0003_weathervisitorreservation")]
    operations = [
        migrations.AddField(model_name="weatherfetch", name="pipeline_version",
                            field=models.PositiveSmallIntegerField(default=1)),
        migrations.RemoveConstraint(model_name="weatherfetch", name="weather_fetch_cell_assessment_unique"),
        migrations.AddConstraint(model_name="weatherfetch", constraint=models.UniqueConstraint(
            fields=("cell_key", "assessment_date", "pipeline_version"), name="weather_fetch_cell_assessment_unique")),
    ]
