from django.apps import AppConfig


class WeatherRequestsConfig(AppConfig):
    """Register the durable weather request application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "weather_requests"
