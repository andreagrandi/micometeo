"""Django application configuration for selected-square details."""

from django.apps import AppConfig


class AreaApiConfig(AppConfig):
    """Register the selected-square API package."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "area_api"
