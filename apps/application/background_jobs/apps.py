from django.apps import AppConfig


class BackgroundJobsConfig(AppConfig):
    """Register the background jobs application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "background_jobs"
