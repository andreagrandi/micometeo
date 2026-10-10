"""Example experiment: one week of daily weather for Pistoia from Open-Meteo."""

import csv
import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from micometeo.context import RunContext

API_URL = "https://archive-api.open-meteo.com/v1/archive"
USER_AGENT = "micometeo-experiments/0.1 (research prototype)"
TIMEOUT_SECONDS = 30


def build_query(*, settings: dict[str, Any]) -> dict[str, Any]:
    """Build the query settings for the Open-Meteo request."""
    return {
        "latitude": settings["latitude"],
        "longitude": settings["longitude"],
        "start_date": settings["start_date"],
        "end_date": settings["end_date"],
        "daily": "precipitation_sum,temperature_2m_mean",
        "timezone": settings["timezone"],
    }


def rows_from_response(*, response: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn the daily part of the API response into rows."""
    daily = response["daily"]
    return [
        {
            "date": date,
            "precipitation_mm": precipitation,
            "mean_temperature_c": temperature,
        }
        for date, precipitation, temperature in zip(
            daily["time"],
            daily["precipitation_sum"],
            daily["temperature_2m_mean"],
            strict=True,
        )
    ]


def write_summary(*, rows: list[dict[str, Any]], path: Path) -> None:
    """Write the rows to a small CSV file."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["date", "precipitation_mm", "mean_temperature_c"]
        )
        writer.writeheader()
        writer.writerows(rows)


def run(context: RunContext) -> None:
    """Download the weather, record the source and write the summary."""
    query = build_query(settings=context.config)
    url = f"{API_URL}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as reply:
        body = reply.read()
    downloaded_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    raw_path = context.raw_dir / "pistoia_daily_weather.json"
    raw_path.write_bytes(body)
    context.add_source(
        name="Open-Meteo Historical Weather API",
        url=API_URL,
        licence="CC BY 4.0",
        version="v1",
        downloaded_at=downloaded_at,
        query=query,
    )
    context.add_input(raw_path)

    rows = rows_from_response(response=json.loads(body))
    summary_path = context.output_dir / "pistoia_summary.csv"
    write_summary(rows=rows, path=summary_path)
    context.add_output(summary_path)
