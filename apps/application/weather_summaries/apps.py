from django.apps import AppConfig


class WeatherSummariesConfig(AppConfig):
    """Register the weather summaries application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "weather_summaries"
