"""Identify weather histories without changing saved evidence."""

import os

from sporameteo.weather.openmeteo import ARCHIVE_URL

PIPELINE_VERSION = 2
HISTORY_DAYS = 30
FORECAST_DAYS = 7
WINDOW_DAYS = HISTORY_DAYS + 1 + FORECAST_DAYS
# Raising this number is the explicit correction of stored history. Rows from
# older versions stay in the database but are no longer reused.
WEATHER_HISTORY_VERSION = 1


def history_endpoint() -> str:
    """Return the configured source of completed days."""
    return os.environ.get("SPORAMETEO_WEATHER_HISTORY_ENDPOINT", ARCHIVE_URL)
