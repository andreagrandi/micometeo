"""Django settings for the local Micometeo application."""

import importlib.util
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def _rasterio_gdal_library_path() -> str | None:
    """Find Rasterio's GDAL library, which does not load a second Arrow build."""
    module_spec = importlib.util.find_spec("rasterio")
    if module_spec is None or module_spec.origin is None:
        return None
    library_dir = Path(module_spec.origin).parent / ".dylibs"
    candidates = sorted(library_dir.glob("libgdal*.dylib"))
    return str(candidates[0]) if candidates else None


def _env_bool(*, name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(*, name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = os.getenv(
    "MICOMETEO_DJANGO_SECRET_KEY",
    "django-insecure-local-development-placeholder",
)
DEBUG = _env_bool(name="MICOMETEO_DEBUG", default=False)
ALLOWED_HOSTS = _env_list(name="MICOMETEO_ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])
CSRF_TRUSTED_ORIGINS = _env_list(
    name="MICOMETEO_CSRF_TRUSTED_ORIGINS",
    default=["http://127.0.0.1:8010", "http://localhost:8010"],
)

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.gis",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_tasks_db",
    "background_jobs",
    "national_grid",
    "national_terrain",
    "national_forest",
    "weather_requests",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": os.getenv("MICOMETEO_DB_NAME", "micometeo"),
        "USER": os.getenv("MICOMETEO_DB_USER", "micometeo"),
        "PASSWORD": os.getenv("MICOMETEO_DB_PASSWORD", "replace-with-a-local-password"),
        "HOST": os.getenv("MICOMETEO_DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("MICOMETEO_DB_PORT", "5542"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"connect_timeout": 5},
    }
}

TASKS = {
    "default": {
        "BACKEND": "django_tasks_db.backend.DatabaseBackend",
    },
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

GDAL_LIBRARY_PATH = (
    os.getenv("MICOMETEO_GDAL_LIBRARY_PATH")
    or _rasterio_gdal_library_path()
    or os.getenv("GDAL_LIBRARY_PATH")
)
GEOS_LIBRARY_PATH = os.getenv("GEOS_LIBRARY_PATH")
