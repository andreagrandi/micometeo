from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("estimate_updates", "0003_estimatetask_queue_token")]

    operations = [
        migrations.AddField(
            model_name="estimatetask", name="calculation_version",
            field=models.CharField(max_length=64, default="", blank=True),
        ),
        migrations.RemoveConstraint(
            model_name="estimatetask", name="estimate_task_input_tuple_unique",
        ),
        migrations.AddConstraint(
            model_name="estimatetask",
            constraint=models.UniqueConstraint(
                fields=["snapshot", "cell_key", "assessment_date", "forest_build_version", "terrain_build_version", "calculation_version"],
                name="estimate_task_input_tuple_unique",
            ),
        ),
        migrations.AddField(
            model_name="estimateupdate", name="tree_inputs", field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="estimateupdate", name="tree_fingerprint",
            field=models.CharField(max_length=64, default="", blank=True),
        ),
        migrations.RemoveConstraint(
            model_name="estimateupdate", name="estimate_update_input_tuple_unique",
        ),
        migrations.AddConstraint(
            model_name="estimateupdate",
            constraint=models.UniqueConstraint(
                fields=["cell_key", "assessment_date", "snapshot", "forest_build", "terrain_build",
                        "method_version", "tree_fingerprint"],
                name="estimate_update_input_tuple_unique",
            ),
        ),
        migrations.CreateModel(
            name="HostTreeCache",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_version", models.CharField(max_length=64)),
                ("cell_id", models.CharField(max_length=80)),
                ("values", models.JSONField()),
            ],
            options={"constraints": [models.UniqueConstraint(
                fields=["source_version", "cell_id"], name="host_tree_source_cell_unique",
            )]},
        ),
    ]
