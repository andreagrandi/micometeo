from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("place_search", "0001_initial")]

    operations = [
        migrations.AddIndex(
            model_name="placesearchcache",
            index=models.Index(fields=["expires_at"], name="place_search_cache_expiry_idx"),
        ),
    ]
