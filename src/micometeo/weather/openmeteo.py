"""Open-Meteo requests with a file cache, retries and request counts.

Hourly values come in GMT. The code that groups them into Italian days is in features.py.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
LICENCE = "CC BY 4.0"
USER_AGENT = "micometeo-experiments/0.1 (research prototype)"
TIMEOUT_SECONDS = 60
HOURLY_VARIABLES = (
    "precipitation",
    "temperature_2m",
    "soil_moisture_0_to_7cm",
    "soil_temperature_0_to_7cm",
    "et0_fao_evapotranspiration",
)
FORECAST_DATASET = "best_match_past_days"
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


def quota_weight(*, variables: int, days: int) -> float:
    """Return how many calls the free plan counts for one request."""
    return max(1.0, variables / 10) * max(1.0, days / 14)


@dataclass
class Metrics:
    """Counts of what the requests cost."""

    requests: int = 0
    cache_hits: int = 0
    request_seconds: float = 0.0
    quota_calls: float = 0.0


def get_json(*, url: str) -> dict[str, Any]:
    """Download one URL and return the decoded JSON."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as reply:
        return json.loads(reply.read())


def cache_name(*, latitude: float, longitude: float, start: date, end: date) -> str:
    return f"{latitude:.4f}_{longitude:.4f}_{start.isoformat()}_{end.isoformat()}.json"


class OpenMeteo:
    """Fetch hourly values, reading from the cache folder first when one is given."""

    def __init__(
        self,
        *,
        cache_dir: Path | None,
        pause_seconds: float,
        attempts: int = 3,
    ) -> None:
        self.cache_dir = cache_dir
        self.pause_seconds = pause_seconds
        self.attempts = attempts
        self.metrics = Metrics()

    def _request(self, *, url: str) -> dict[str, Any]:
        started = time.monotonic()
        try:
            for attempt in range(self.attempts):
                try:
                    answer = get_json(url=url)
                    break
                except urllib.error.HTTPError as error:
                    if error.code not in RETRY_STATUS_CODES or attempt == self.attempts - 1:
                        raise
                except OSError:
                    if attempt == self.attempts - 1:
                        raise
                time.sleep(2 * (attempt + 1))
        finally:
            self.metrics.requests += 1
            self.metrics.request_seconds += time.monotonic() - started
        if answer.get("error"):
            raise RuntimeError(f"Open-Meteo refused the request: {answer.get('reason')}")
        time.sleep(self.pause_seconds)
        return answer

    def _fetch(
        self,
        *,
        dataset: str,
        base_url: str,
        query: dict[str, Any],
        latitude: float,
        longitude: float,
        start: date,
        end: date,
    ) -> dict[str, Any]:
        path = None
        if self.cache_dir is not None:
            name = cache_name(latitude=latitude, longitude=longitude, start=start, end=end)
            path = self.cache_dir / dataset / name
            if path.exists():
                self.metrics.cache_hits += 1
                return json.loads(path.read_text(encoding="utf-8"))
        days = (end - start).days + 1
        self.metrics.quota_calls += quota_weight(variables=len(HOURLY_VARIABLES), days=days)
        answer = self._request(url=base_url + "?" + urllib.parse.urlencode(query))
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(answer), encoding="utf-8")
        return answer

    def archive_hourly(
        self, *, model: str, latitude: float, longitude: float, start: date, end: date
    ) -> dict[str, Any]:
        """Return the hourly part of an archive answer for UTC dates start to end."""
        query = {
            "latitude": round(latitude, 4),
            "longitude": round(longitude, 4),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "hourly": ",".join(HOURLY_VARIABLES),
            "models": model,
            "timezone": "GMT",
        }
        answer = self._fetch(
            dataset=model,
            base_url=ARCHIVE_URL,
            query=query,
            latitude=latitude,
            longitude=longitude,
            start=start,
            end=end,
        )
        return answer["hourly"]

    def forecast_hourly(
        self, *, latitude: float, longitude: float, past_days: int, today: date
    ) -> dict[str, Any]:
        """Return the hourly part of a Forecast API answer for the past days and today."""
        query = {
            "latitude": round(latitude, 4),
            "longitude": round(longitude, 4),
            "hourly": ",".join(HOURLY_VARIABLES),
            "past_days": past_days,
            "forecast_days": 1,
            "timezone": "GMT",
        }
        answer = self._fetch(
            dataset=FORECAST_DATASET,
            base_url=FORECAST_URL,
            query=query,
            latitude=latitude,
            longitude=longitude,
            start=today - timedelta(days=past_days),
            end=today,
        )
        return answer["hourly"]
