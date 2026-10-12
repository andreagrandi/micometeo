from django.apps import AppConfig


class WebUiConfig(AppConfig):
    """Configure the public web pages."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "web_ui"
