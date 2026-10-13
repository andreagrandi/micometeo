"""Django application configuration for place search."""

from django.apps import AppConfig


class PlaceSearchConfig(AppConfig):
    """Register the place search application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "place_search"
