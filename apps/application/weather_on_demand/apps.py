from django.apps import AppConfig


class WeatherOnDemandConfig(AppConfig):
    """Configure durable weather fetch records."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "weather_on_demand"
