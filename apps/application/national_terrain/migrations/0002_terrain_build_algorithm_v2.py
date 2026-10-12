from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("national_terrain", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="terrainbuild",
            name="algorithm_version",
            field=models.CharField(default="national-terrain-v2", max_length=50),
        ),
    ]
