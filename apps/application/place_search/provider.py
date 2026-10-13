"""Photon provider access with cache and database request throttling."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from datetime import timedelta, timezone as datetime_timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import PlaceSearchCache, PlaceSearchThrottle


class PlaceSearchError(Exception):
    """Report a provider failure that the API can describe to the browser."""

    code = "provider_unavailable"
    retry_after: int | None = None


class PlaceSearchTimeout(PlaceSearchError):
    """Report a provider timeout."""

    code = "provider_timeout"


class PlaceSearchThrottled(PlaceSearchError):
    """Report a local or provider throttle response."""

    code = "throttled"

    def __init__(self, *, retry_after: int) -> None:
        super().__init__("The place search is temporarily throttled.")
        self.retry_after = max(1, retry_after)


class PlaceSearchUnavailable(PlaceSearchError):
    """Report an unavailable provider response."""


@dataclass(frozen=True)
class PlaceResult:
    """Represent one Italian place result returned by Photon."""

    name: str
    context: str
    latitude: float
    longitude: float
    bounds: dict[str, float] | None = None
    osm_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return the public JSON shape for one place."""
        result: dict[str, object] = {
            "name": self.name,
            "context": self.context,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }
        if self.bounds is not None:
            result["bounds"] = self.bounds
        if self.osm_id is not None:
            result["osm_id"] = self.osm_id
        return result


def normalize_query(value: str) -> str:
    """Normalize Unicode, whitespace and case for stable cache keys."""
    normalized = unicodedata.normalize("NFKC", value or "")
    return " ".join(normalized.split()).casefold()


def _setting(name: str, default: object) -> object:
    return getattr(settings, name, default)


def _endpoint() -> str:
    return str(_setting("MICOMETEO_PLACE_SEARCH_URL", "https://photon.komoot.io/api")).rstrip("?")


def _language(value: str | None) -> str:
    language = (value or "it").split("-", maxsplit=1)[0].lower()
    return language if language in {"it", "en"} else "it"


def _provider_language(language: str) -> str:
    return "default" if language == "it" else language


def _throttle() -> None:
    interval = float(_setting("MICOMETEO_PLACE_SEARCH_REQUEST_INTERVAL", 1.0))
    now = timezone.now()
    with transaction.atomic():
        row, _ = PlaceSearchThrottle.objects.select_for_update().get_or_create(id=1)
        if row.last_request_at is not None:
            if row.last_request_at > now:
                remaining = (row.last_request_at - now).total_seconds()
                raise PlaceSearchThrottled(retry_after=max(1, int(remaining) + 1))
            elapsed = (now - row.last_request_at).total_seconds()
            if elapsed < interval:
                raise PlaceSearchThrottled(retry_after=max(1, int(interval - elapsed) + 1))
        row.last_request_at = now
        row.save(update_fields=["last_request_at", "updated_at"])


def _set_throttle_cooldown(*, seconds: int) -> None:
    cooldown = max(1, seconds)
    with transaction.atomic():
        row, _ = PlaceSearchThrottle.objects.select_for_update().get_or_create(id=1)
        row.last_request_at = timezone.now() + timedelta(seconds=cooldown)
        row.save(update_fields=["last_request_at", "updated_at"])


def _retry_after(value: str | None) -> int:
    try:
        return max(1, int(value or "1"))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value or "")
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=datetime_timezone.utc)
            seconds = retry_at.timestamp() - timezone.now().timestamp()
            return max(1, int(seconds) + 1)
        except (TypeError, ValueError, OverflowError):
            return 1


def _request(*, query: str, language: str) -> dict[str, object]:
    parameters = {
        "q": query,
        "limit": int(_setting("MICOMETEO_PLACE_SEARCH_LIMIT", 8)),
        "countrycode": "IT",
        "lang": _provider_language(language),
        "layer": ["city", "locality", "district"],
    }
    encoded = urlencode(parameters, doseq=True)
    request = Request(
        url=f"{_endpoint()}?{encoded}",
        headers={
            "Accept": "application/json",
            "User-Agent": str(
                _setting("MICOMETEO_PLACE_SEARCH_USER_AGENT", "Micometeo/1.0 place search")
            ),
        },
        method="GET",
    )
    try:
        with urlopen(url=request, timeout=float(_setting("MICOMETEO_PLACE_SEARCH_TIMEOUT", 4.0))) as response:
            status = getattr(response, "status", None) or response.getcode()
            if status == 429:
                raise PlaceSearchThrottled(retry_after=_retry_after(response.headers.get("Retry-After")))
            if status >= 400:
                raise PlaceSearchUnavailable(f"Photon returned HTTP {status}.")
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == 429:
            raise PlaceSearchThrottled(retry_after=_retry_after(error.headers.get("Retry-After"))) from error
        raise PlaceSearchUnavailable(f"Photon returned HTTP {error.code}.") from error
    except TimeoutError as error:
        raise PlaceSearchTimeout("Photon did not answer before the timeout.") from error
    except URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise PlaceSearchTimeout("Photon did not answer before the timeout.") from error
        raise PlaceSearchUnavailable("Photon could not be reached.") from error
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        raise PlaceSearchUnavailable("Photon returned an invalid response.") from error
    if not isinstance(data, dict):
        raise PlaceSearchUnavailable("Photon returned an invalid response.")
    return data


def _context(properties: dict[str, object]) -> str:
    values = [
        properties.get("city") or properties.get("municipality") or properties.get("locality"),
        properties.get("county") or properties.get("district"),
        properties.get("state") or properties.get("region"),
    ]
    return ", ".join(str(value) for value in values if value and str(value).lower() != str(properties.get("name", "")).lower())


def _feature_result(feature: object) -> PlaceResult | None:
    if not isinstance(feature, dict):
        return None
    properties = feature.get("properties")
    geometry = feature.get("geometry")
    if not isinstance(properties, dict) or not isinstance(geometry, dict):
        return None
    if str(properties.get("countrycode", "")).lower() not in {"it", "ita"}:
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    try:
        longitude, latitude = float(coordinates[0]), float(coordinates[1])
    except (TypeError, ValueError):
        return None
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        return None
    name = str(properties.get("name") or properties.get("city") or "").strip()
    if not name:
        return None
    bounds = feature.get("bbox")
    parsed_bounds = None
    if isinstance(bounds, list) and len(bounds) >= 4:
        try:
            parsed_bounds = {
                "west": float(bounds[0]),
                "south": float(bounds[1]),
                "east": float(bounds[2]),
                "north": float(bounds[3]),
            }
        except (TypeError, ValueError):
            parsed_bounds = None
    osm_id = properties.get("osm_id")
    return PlaceResult(
        name=name,
        context=_context(properties),
        latitude=latitude,
        longitude=longitude,
        bounds=parsed_bounds,
        osm_id=str(osm_id) if osm_id is not None else None,
    )


def _parse_results(data: dict[str, object]) -> list[dict[str, object]]:
    features = data.get("features")
    if not isinstance(features, list):
        return []
    results = []
    for feature in features:
        parsed = _feature_result(feature)
        if parsed is not None:
            results.append(parsed.as_dict())
    return results[: int(_setting("MICOMETEO_PLACE_SEARCH_LIMIT", 8))]


def _result_matches_query(*, result: object, query: str) -> bool:
    if not isinstance(result, dict):
        return False
    name = normalize_query(str(result.get("name") or ""))
    if name.startswith(query):
        return True
    return any(word.startswith(query) for word in name.split())


def _result_key(result: dict[str, object]) -> tuple[str, str, str, str]:
    return (
        normalize_query(str(result.get("name") or "")),
        str(result.get("latitude") or ""),
        str(result.get("longitude") or ""),
        normalize_query(str(result.get("context") or "")),
    )


def cached_place_results(
    *, query: str, language: str | None = None
) -> tuple[list[dict[str, object]], bool]:
    """Return an exact cache hit or a read-only prefix preview."""
    normalized = normalize_query(query)
    minimum = int(_setting("MICOMETEO_PLACE_SEARCH_MIN_LENGTH", 2))
    if len(normalized) < minimum:
        return [], False
    selected_language = _language(language)
    endpoint = _endpoint()
    now = timezone.now()
    exact = PlaceSearchCache.objects.filter(
        normalized_query=normalized,
        language=selected_language,
        endpoint=endpoint,
        expires_at__gt=now,
    ).first()
    if exact is not None:
        return list(exact.results), True

    prefixes = [normalized[:length] for length in range(minimum, len(normalized))]
    related = PlaceSearchCache.objects.filter(
        Q(normalized_query__startswith=normalized) | Q(normalized_query__in=prefixes),
        language=selected_language,
        endpoint=endpoint,
        expires_at__gt=now,
    ).order_by("-fetched_at", "-id")[:50]
    results: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()
    limit = int(_setting("MICOMETEO_PLACE_SEARCH_LIMIT", 8))
    for cache_row in related:
        for result in cache_row.results:
            if not _result_matches_query(result=result, query=normalized):
                continue
            if not isinstance(result, dict):
                continue
            key = _result_key(result)
            if key in seen:
                continue
            seen.add(key)
            results.append(result)
            if len(results) >= limit:
                return results, False
    return results, False


def search_places(*, query: str, language: str | None = None) -> tuple[list[dict[str, object]], bool]:
    """Return cached or fresh Italian Photon results for one query."""
    normalized = normalize_query(query)
    if len(normalized) < int(_setting("MICOMETEO_PLACE_SEARCH_MIN_LENGTH", 2)):
        return [], True
    selected_language = _language(language)
    endpoint = _endpoint()
    now = timezone.now()
    cached = PlaceSearchCache.objects.filter(
        normalized_query=normalized,
        language=selected_language,
        endpoint=endpoint,
        expires_at__gt=now,
    ).first()
    if cached is not None:
        return list(cached.results), True
    _throttle()
    try:
        data = _request(query=query.strip(), language=selected_language)
    except PlaceSearchThrottled as error:
        _set_throttle_cooldown(seconds=error.retry_after or 1)
        raise
    results = _parse_results(data)
    ttl_setting = "MICOMETEO_PLACE_SEARCH_CACHE_SECONDS" if results else "MICOMETEO_PLACE_SEARCH_EMPTY_CACHE_SECONDS"
    default_ttl = 2_592_000 if results else 900
    ttl = max(1, int(_setting(ttl_setting, default_ttl)))
    PlaceSearchCache.objects.update_or_create(
        normalized_query=normalized,
        language=selected_language,
        endpoint=endpoint,
        defaults={
            "results": results,
            "fetched_at": now,
            "expires_at": now + timedelta(seconds=ttl),
        },
    )
    expired_ids = list(
        PlaceSearchCache.objects.filter(expires_at__lte=now)
        .order_by("expires_at")
        .values_list("id", flat=True)[:100]
    )
    if expired_ids:
        PlaceSearchCache.objects.filter(id__in=expired_ids, expires_at__lte=now).delete()
    return results, False


def request_interval() -> float:
    """Expose the configured local request interval for API headers."""
    return max(0.0, float(_setting("MICOMETEO_PLACE_SEARCH_REQUEST_INTERVAL", 1.0)))
