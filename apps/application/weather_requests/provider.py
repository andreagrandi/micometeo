"""One-at-a-time Open-Meteo access with durable quota reservations."""

from __future__ import annotations

import inspect
import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from numbers import Real
from typing import Any, Callable, Mapping
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import WeatherRequest, WeatherRequestAttempt
from .eligibility import weather_cell
from .planning import RequestSpec
from .quota import QuotaCheck, ReservationResult, finish_attempt, quota_limits, reserve_attempt

DEFAULT_TIMEOUT_SECONDS = 60.0
MAX_RETRY_SECONDS = 3_600
MAX_RETURNED_COORDINATE_DISTANCE_KM = 25.0
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
UNIT_BY_VARIABLE = {
    "precipitation": "mm",
    "temperature_2m": "°C",
    "soil_moisture_0_to_7cm": "m³/m³",
    "soil_temperature_0_to_7cm": "°C",
    "et0_fao_evapotranspiration": "mm",
}


class ProviderError(RuntimeError):
    """Base error for one provider attempt."""


class CompletedRequestError(ProviderError):
    """Report that completed data must be read through the daily snapshot cache."""


class PendingRequestError(ProviderError):
    """Report a request that is waiting for its recorded retry time."""

    def __init__(self, message: str, *, retry_at: datetime | None = None) -> None:
        super().__init__(message)
        self.retry_at = retry_at


class ResponseValidationError(ProviderError):
    """Report a provider answer that does not match its requested contract."""


class PermanentProviderError(ProviderError):
    """Report a provider refusal that should not be retried automatically."""


@dataclass(frozen=True)
class ProviderResult:
    """Expose validated metadata and raw hourly data for the current process."""

    logical_request: WeatherRequest
    spec: RequestSpec
    attempt_ids: tuple[UUID, ...]
    raw_hourly: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]
    quota: QuotaCheck

    @property
    def request(self) -> WeatherRequest:
        """Return the durable logical request record."""
        return self.logical_request

    @property
    def attempt_id(self) -> UUID:
        """Return the only attempt used by this one-at-a-time operation."""
        if len(self.attempt_ids) != 1:
            raise ValueError("A provider result does not have exactly one attempt.")
        return self.attempt_ids[0]


@dataclass(frozen=True)
class _Response:
    status: int
    headers: Mapping[str, str]
    body: bytes


def _clock_now(clock: Callable[[], datetime] | None) -> datetime:
    value = clock() if clock is not None else timezone.now()
    if timezone.is_naive(value):
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _full_exception_message(error: BaseException) -> str:
    text = str(error).strip()
    return f"{type(error).__name__}: {text}" if text else type(error).__name__


def _response_headers(response: Any) -> dict[str, str]:
    headers = getattr(response, "headers", {}) or {}
    if hasattr(headers, "items"):
        return {str(key).lower(): str(value) for key, value in headers.items()}
    return {}


def _read_response(response: Any) -> _Response:
    status = int(getattr(response, "status", getattr(response, "status_code", 200)))
    body = response.read()
    if isinstance(body, str):
        body = body.encode("utf-8")
    return _Response(status=status, headers=_response_headers(response), body=bytes(body))


def _default_transport(*, url: str, timeout: float) -> _Response:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "sporameteo-weather-requests/1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return _read_response(response)


def _transport_call(
    *,
    transport: Callable[..., Any],
    url: str,
    timeout: float,
) -> _Response:
    try:
        parameters = inspect.signature(transport).parameters
    except (TypeError, ValueError):
        parameters = {}
    url_parameter = parameters.get("url")
    timeout_parameter = parameters.get("timeout")
    accepts_keywords = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    if accepts_keywords or (
        url_parameter is not None
        and url_parameter.kind is not inspect.Parameter.POSITIONAL_ONLY
    ):
        arguments: dict[str, Any] = {"url": url}
        if accepts_keywords or (
            timeout_parameter is not None
            and timeout_parameter.kind is not inspect.Parameter.POSITIONAL_ONLY
        ):
            arguments["timeout"] = timeout
        response = transport(**arguments)
    elif (
        timeout_parameter is not None
        and timeout_parameter.kind is inspect.Parameter.KEYWORD_ONLY
    ):
        response = transport(url, timeout=timeout)
    else:
        response = transport(url, timeout)
    if isinstance(response, _Response):
        return response
    if hasattr(response, "read"):
        return _read_response(response)
    if isinstance(response, tuple) and len(response) == 3:
        status, headers, body = response
        if isinstance(body, str):
            body = body.encode("utf-8")
        return _Response(
            status=int(status),
            headers={str(key).lower(): str(value) for key, value in dict(headers).items()},
            body=bytes(body),
        )
    if isinstance(response, (dict, list)):
        return _Response(status=200, headers={}, body=json.dumps(response).encode("utf-8"))
    raise TypeError("The weather transport must return a response or JSON mapping.")


def _http_error_response(error: urllib.error.HTTPError) -> _Response:
    try:
        body = error.read()
    except OSError:
        body = b""
    if isinstance(body, str):
        body = body.encode("utf-8")
    return _Response(
        status=int(error.code),
        headers=_response_headers(error),
        body=bytes(body),
    )


def _message(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def _retry_after(*, headers: Mapping[str, str], now: datetime, attempt_number: int) -> datetime:
    value = headers.get("retry-after", "").strip()
    delay: float | None = None
    if value:
        try:
            delay = max(0.0, float(value))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                delay = max(0.0, (parsed.astimezone(UTC) - now).total_seconds())
            except (TypeError, ValueError, OverflowError):
                delay = None
    if delay is None:
        delay = min(float(MAX_RETRY_SECONDS), float(2 ** max(0, attempt_number - 1)))
    return now + timedelta(seconds=min(delay, MAX_RETRY_SECONDS))


def _parse_json(*, body: bytes) -> Any:
    try:
        return json.loads(body)
    except (TypeError, ValueError) as exc:
        raise ResponseValidationError("The provider response was not valid UTF-8 JSON.") from exc


def _as_location_list(*, payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        values = [payload]
    else:
        raise ResponseValidationError("The provider response did not contain locations.")
    if not all(isinstance(value, dict) for value in values):
        raise ResponseValidationError("The provider response contained an invalid location.")
    return values


def _timestamp(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return int(parsed.timestamp())
    raise ValueError


def _expected_timestamps(*, spec: RequestSpec) -> list[int]:
    current = spec.utc_start
    result: list[int] = []
    while current <= spec.utc_end:
        result.append(int(current.timestamp()))
        current += timedelta(hours=1)
    return result


def _claim_attempt(
    *,
    attempt: WeatherRequestAttempt,
    request_id: Any,
    reservation_weight: Any,
    started_at: datetime,
) -> WeatherRequestAttempt:
    """Claim one untouched reservation with a conditional database update."""
    claimed = WeatherRequestAttempt.objects.filter(
        pk=attempt.pk,
        request_id=request_id,
        reservation_weight=reservation_weight,
        outcome=WeatherRequestAttempt.Outcome.RESERVATION,
        started_at__isnull=True,
    ).update(started_at=started_at)
    if claimed != 1:
        raise ProviderError("The reserved attempt is no longer available for execution.")
    return WeatherRequestAttempt.objects.get(pk=attempt.pk)


def _validate_hourly_values(
    *,
    index: int,
    variable: str,
    values: Any,
    expected_count: int,
) -> None:
    """Validate numeric hourly values before an attempt can complete."""
    if not isinstance(values, list) or len(values) != expected_count:
        raise ResponseValidationError(f"Provider variable {variable} did not match exact hours.")
    for position, value in enumerate(values):
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
            raise ResponseValidationError(
                f"Provider location {index} variable {variable} has an invalid value at hour {position}."
            )
        number = float(value)
        if variable in {"precipitation", "et0_fao_evapotranspiration"} and number < 0:
            raise ResponseValidationError(
                f"Provider location {index} variable {variable} has a negative value at hour {position}."
            )
        if variable == "soil_moisture_0_to_7cm" and not 0 <= number <= 1:
            raise ResponseValidationError(
                f"Provider location {index} variable {variable} is outside zero to one at hour {position}."
            )


def _coordinate_distance_km(
    *,
    requested_latitude: float,
    requested_longitude: float,
    returned_latitude: float,
    returned_longitude: float,
) -> float:
    """Return the great-circle distance between requested and grid coordinates."""
    radius_km = 6_371.0088
    requested_latitude_radians = math.radians(requested_latitude)
    returned_latitude_radians = math.radians(returned_latitude)
    latitude_delta = returned_latitude_radians - requested_latitude_radians
    longitude_delta = math.radians(returned_longitude - requested_longitude)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(requested_latitude_radians)
        * math.cos(returned_latitude_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    return radius_km * 2 * math.asin(math.sqrt(min(1.0, max(0.0, haversine))))


def _validate_location_coordinates(
    *,
    index: int,
    expected: Any,
    location: Mapping[str, Any],
) -> tuple[float, float]:
    """Validate finite geographic coordinates within the 25 km model-grid guard."""
    try:
        raw_latitude = location["latitude"]
        raw_longitude = location["longitude"]
        if (
            isinstance(raw_latitude, bool)
            or not isinstance(raw_latitude, Real)
            or isinstance(raw_longitude, bool)
            or not isinstance(raw_longitude, Real)
        ):
            raise ValueError
        latitude = float(raw_latitude)
        longitude = float(raw_longitude)
    except (KeyError, TypeError, ValueError) as exc:
        raise ResponseValidationError(f"Location {index} has no coordinates.") from exc
    if (
        not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        raise ResponseValidationError(f"Provider location {index} returned invalid coordinates.")
    distance_km = _coordinate_distance_km(
        requested_latitude=expected.latitude,
        requested_longitude=expected.longitude,
        returned_latitude=latitude,
        returned_longitude=longitude,
    )
    if distance_km > MAX_RETURNED_COORDINATE_DISTANCE_KM:
        raise ResponseValidationError(
            f"Provider location {index} returned coordinates {distance_km:.1f} km from its request."
        )
    location_id = location.get("location_id")
    if location_id is not None:
        try:
            if isinstance(location_id, bool) or int(location_id) != index:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ResponseValidationError(
                f"Provider location {index} returned mismatched location_id {location_id!r}."
            ) from exc
    return latitude, longitude


def _validate_locations(*, spec: RequestSpec, payload: Any) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
    locations = _as_location_list(payload=payload)
    if len(locations) != len(spec.locations):
        raise ResponseValidationError(
            f"Provider returned {len(locations)} locations for {len(spec.locations)} requested."
        )
    expected_times = _expected_timestamps(spec=spec)
    raw_hourly: list[dict[str, Any]] = []
    metadata_locations: list[dict[str, Any]] = []
    for index, (location, expected) in enumerate(zip(locations, spec.locations, strict=True)):
        latitude, longitude = _validate_location_coordinates(
            index=index,
            expected=expected,
            location=location,
        )
        returned_model = location.get("model")
        if returned_model is not None and str(returned_model) != spec.model:
            raise ResponseValidationError(
                f"Provider location {index} returned model {returned_model!r}, expected {spec.model!r}."
            )
        timezone_name = str(location.get("timezone", ""))
        if timezone_name != spec.timezone:
            raise ResponseValidationError(
                f"Provider location {index} returned timezone {timezone_name!r}, expected GMT."
            )
        hourly = location.get("hourly")
        if not isinstance(hourly, dict):
            raise ResponseValidationError(f"Provider location {index} has no hourly data.")
        times = hourly.get("time")
        if not isinstance(times, list):
            raise ResponseValidationError(f"Provider location {index} has no hourly timestamps.")
        try:
            actual_times = [_timestamp(value) for value in times]
        except ValueError as exc:
            raise ResponseValidationError(f"Provider location {index} has invalid timestamps.") from exc
        if actual_times != expected_times:
            raise ResponseValidationError(f"Provider location {index} did not return exact requested hours.")
        units = location.get("hourly_units")
        if not isinstance(units, dict):
            raise ResponseValidationError(f"Provider location {index} has no hourly units.")
        for variable in spec.variables:
            if variable not in hourly:
                raise ResponseValidationError(f"Provider location {index} omitted {variable}.")
            if variable not in units:
                raise ResponseValidationError(f"Provider location {index} omitted units for {variable}.")
            expected_unit = UNIT_BY_VARIABLE.get(variable)
            if expected_unit and str(units[variable]) != expected_unit:
                raise ResponseValidationError(
                    f"Provider returned {units[variable]!r} for {variable}, expected {expected_unit!r}."
                )
            values = hourly[variable]
            _validate_hourly_values(
                index=index,
                variable=variable,
                values=values,
                expected_count=len(expected_times),
            )
        elevation = location.get("elevation")
        if elevation is not None and (
            isinstance(elevation, bool)
            or not isinstance(elevation, Real)
            or not math.isfinite(float(elevation))
        ):
            raise ResponseValidationError(f"Provider location {index} returned invalid elevation.")
        metadata_locations.append(
            {
                "position": index,
                "location_id": location.get("location_id"),
                "requested_latitude": expected.latitude,
                "requested_longitude": expected.longitude,
                "latitude": latitude,
                "longitude": longitude,
                "elevation": elevation,
                "timezone": timezone_name,
                "timezone_abbreviation": location.get("timezone_abbreviation"),
                "utc_offset_seconds": location.get("utc_offset_seconds"),
                "units": dict(units),
            }
        )
        raw_hourly.append(hourly)
    top_units = locations[0].get("hourly_units", {}) if locations else {}
    return tuple(raw_hourly), {
        "source": "Open-Meteo Forecast API",
        "provider": "Open-Meteo",
        "model": spec.model,
        "endpoint": spec.endpoint,
        "retrieved_at": None,
        "timezone": spec.timezone,
        "timeformat": spec.timeformat,
        "requested_start": spec.utc_start.isoformat(),
        "requested_end": spec.utc_end.isoformat(),
        "returned_hours": len(expected_times),
        "units": dict(top_units),
        "locations": metadata_locations,
    }


def get_or_create_request(
    *,
    spec: RequestSpec,
    provenance: Mapping[str, Any] | None = None,
) -> WeatherRequest:
    """Create one logical request and its ordered cell members."""
    defaults = {
        "canonical_spec": dict(spec.canonical),
        "forest_build_version": spec.forest_build_version,
        "provenance": {
            "source": "Open-Meteo Forecast API",
            "request_digest": spec.digest,
            **(dict(provenance or {})),
        },
    }
    with transaction.atomic():
        request = WeatherRequest.objects.select_for_update().filter(request_digest=spec.digest).first()
        if request is None:
            try:
                with transaction.atomic():
                    request = WeatherRequest.objects.create(
                        request_digest=spec.digest,
                        **defaults,
                    )
            except IntegrityError:
                request = WeatherRequest.objects.select_for_update().get(request_digest=spec.digest)
        if request.members.count() == 0:
            from .models import WeatherRequestMember

            WeatherRequestMember.objects.bulk_create(
                [
                    WeatherRequestMember(
                        request=request,
                        position=index,
                        weather_cell_key=location.key,
                        latitude=location.latitude,
                        longitude=location.longitude,
                    )
                    for index, location in enumerate(spec.locations)
                ]
            )
    request.refresh_from_db()
    return request


def request_spec_from_request(*, request: WeatherRequest) -> RequestSpec:
    """Rebuild the canonical plan stored with a logical request."""
    query = dict(request.canonical_spec.get("query", {}))
    members = tuple(request.members.order_by("position").all())
    if not members:
        raise ProviderError("The logical request has no ordered members.")
    reserved_keys = {
        "latitude",
        "longitude",
        "hourly",
        "models",
        "start_date",
        "end_date",
        "timezone",
        "timeformat",
        "start_hour",
        "end_hour",
    }

    def query_hour(*, value: object) -> int:
        """Read an hour from the current ISO form or an older numeric form."""
        text = str(value)
        if "T" in text:
            return int(text[11:13])
        return int(text)

    return RequestSpec(
        endpoint=str(request.canonical_spec["endpoint"]),
        locations=tuple(
            weather_cell(latitude=member.latitude, longitude=member.longitude)
            for member in members
        ),
        model=str(query["models"]),
        variables=tuple(str(query["hourly"]).split(",")),
        start_date=date.fromisoformat(str(request.canonical_spec["local_date_start"])),
        end_date=date.fromisoformat(str(request.canonical_spec["local_date_end"])),
        timezone=str(query["timezone"]),
        timeformat=str(query["timeformat"]),
        start_hour=query_hour(value=query["start_hour"]),
        end_hour=query_hour(value=query["end_hour"]),
        options={key: str(value) for key, value in query.items() if key not in reserved_keys},
        forest_build_version=request.forest_build_version,
    )


class WeatherProvider:
    """Execute exactly one request attempt with injected time and transport."""

    def __init__(
        self,
        *,
        transport: Callable[..., Any] | None = None,
        clock: Callable[[], datetime] | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.transport = transport or _default_transport
        self.clock = clock
        self.timeout_seconds = timeout_seconds

    def fetch(
        self,
        *,
        spec: RequestSpec,
        provenance: Mapping[str, Any] | None = None,
        allow_completed_refetch: bool = False,
        reserved_attempt: WeatherRequestAttempt | None = None,
    ) -> ProviderResult:
        """Reserve quota, perform one URL request and validate its complete answer.

        A completed request can be retried only when the caller has confirmed that its
        hourly result was lost before the downstream daily snapshot was committed.
        """
        if (
            reserved_attempt is not None
            and reserved_attempt.reservation_weight != spec.reservation_weight
        ):
            raise ProviderError(
                "The reserved attempt weight does not match the request specification."
            )
        now = _clock_now(self.clock)
        request = get_or_create_request(spec=spec, provenance=provenance)
        if request.status == WeatherRequest.Status.COMPLETED and not allow_completed_refetch:
            raise CompletedRequestError(
                "This request is completed. Read the daily snapshot cache instead of refetching hourly data."
            )
        if request.status == WeatherRequest.Status.COMPLETED and allow_completed_refetch:
            request.status = WeatherRequest.Status.PENDING
            request.retry_at = None
            request.save(update_fields=["status", "retry_at", "updated_at"])
        if request.status == WeatherRequest.Status.FAILED:
            raise PermanentProviderError(request.latest_provider_message or "The request permanently failed.")
        if request.retry_at is not None and request.retry_at > now:
            raise PendingRequestError(
                request.latest_provider_message or "The request is waiting for a retry.",
                retry_at=request.retry_at,
            )
        if reserved_attempt is None:
            reservation = reserve_attempt(
                request=request,
                reservation_weight=spec.reservation_weight,
                now=now,
            )
        else:
            if reserved_attempt.request_id != request.id:
                raise ProviderError("The reserved attempt belongs to another logical request.")
            if reserved_attempt.outcome != WeatherRequestAttempt.Outcome.RESERVATION:
                raise ProviderError("The reserved attempt has already been completed.")
            reservation = ReservationResult(
                attempt=reserved_attempt,
                quota=QuotaCheck(
                    allowed=True,
                    reservation_weight=reserved_attempt.reservation_weight,
                    now=reserved_attempt.reserved_at,
                    usage={},
                    limits=quota_limits(),
                ),
            )
        if reservation.attempt is None:
            raise PendingRequestError(
                reservation.quota.reason,
                retry_at=reservation.quota.retry_at,
            )
        attempt = reservation.attempt
        started = _clock_now(self.clock)
        attempt = _claim_attempt(
            attempt=attempt,
            request_id=request.id,
            reservation_weight=spec.reservation_weight,
            started_at=started,
        )
        url = spec.endpoint + ("&" if "?" in spec.endpoint else "?") + spec.query_string
        try:
            try:
                response = _transport_call(
                    transport=self.transport,
                    url=url,
                    timeout=self.timeout_seconds,
                )
            except urllib.error.HTTPError as error:
                response = _http_error_response(error)
            except OSError as error:
                retry_at = _retry_after(
                    headers={},
                    now=_clock_now(self.clock),
                    attempt_number=attempt.attempt_number,
                )
                message = _full_exception_message(error)
                finish_attempt(
                    attempt=attempt,
                    outcome=WeatherRequestAttempt.Outcome.RETRY,
                    ended_at=_clock_now(self.clock),
                    message=message,
                    retry_at=retry_at,
                )
                request.status = WeatherRequest.Status.PENDING
                request.retry_at = retry_at
                request.latest_provider_message = message
                request.save(update_fields=["status", "retry_at", "latest_provider_message", "updated_at"])
                raise PendingRequestError(message, retry_at=retry_at) from error
            body_message = _message(response.body)
            if response.status != 200:
                if response.status in TRANSIENT_STATUS_CODES:
                    retry_at = _retry_after(
                        headers=response.headers,
                        now=_clock_now(self.clock),
                        attempt_number=attempt.attempt_number,
                    )
                    outcome = (
                        WeatherRequestAttempt.Outcome.REFUSED
                        if response.status == 429
                        else WeatherRequestAttempt.Outcome.RETRY
                    )
                    finish_attempt(
                        attempt=attempt,
                        outcome=outcome,
                        ended_at=_clock_now(self.clock),
                        message=body_message,
                        http_status=response.status,
                        retry_at=retry_at,
                    )
                    request.status = WeatherRequest.Status.PENDING
                    request.retry_at = retry_at
                    request.latest_provider_message = body_message
                    request.save(
                        update_fields=["status", "retry_at", "latest_provider_message", "updated_at"]
                    )
                    raise PendingRequestError(body_message, retry_at=retry_at)
                finish_attempt(
                    attempt=attempt,
                    outcome=WeatherRequestAttempt.Outcome.FAILED,
                    ended_at=_clock_now(self.clock),
                    message=body_message,
                    http_status=response.status,
                )
                request.status = WeatherRequest.Status.FAILED
                request.failed_at = _clock_now(self.clock)
                request.latest_provider_message = body_message
                request.save(
                    update_fields=["status", "failed_at", "latest_provider_message", "updated_at"]
                )
                raise PermanentProviderError(body_message)
            payload = _parse_json(body=response.body)
            if isinstance(payload, dict) and payload.get("error"):
                reason = body_message
                finish_attempt(
                    attempt=attempt,
                    outcome=WeatherRequestAttempt.Outcome.FAILED,
                    ended_at=_clock_now(self.clock),
                    message=reason,
                    http_status=response.status,
                )
                request.status = WeatherRequest.Status.FAILED
                request.failed_at = _clock_now(self.clock)
                request.latest_provider_message = reason
                request.save(
                    update_fields=["status", "failed_at", "latest_provider_message", "updated_at"]
                )
                raise PermanentProviderError(reason)
            raw_hourly, metadata = _validate_locations(spec=spec, payload=payload)
            retrieved_at = _clock_now(self.clock)
            metadata["retrieved_at"] = retrieved_at.isoformat()
            metadata["request_id"] = str(request.id)
            metadata["attempt_id"] = str(attempt.id)
            finish_attempt(
                attempt=attempt,
                outcome=WeatherRequestAttempt.Outcome.SUCCESS,
                ended_at=retrieved_at,
                message="",
                http_status=response.status,
            )
            request.status = WeatherRequest.Status.COMPLETED
            request.retry_at = None
            request.latest_provider_message = ""
            request.completed_at = retrieved_at
            request.completion_metadata = metadata
            request.save(
                update_fields=[
                    "status",
                    "retry_at",
                    "latest_provider_message",
                    "completed_at",
                    "completion_metadata",
                    "updated_at",
                ]
            )
            return ProviderResult(
                logical_request=request,
                spec=spec,
                attempt_ids=(attempt.id,),
                raw_hourly=raw_hourly,
                metadata=metadata,
                quota=reservation.quota,
            )
        except (PendingRequestError, PermanentProviderError):
            raise

        except ResponseValidationError as error:
            message = _full_exception_message(error)
            finish_attempt(
                attempt=attempt,
                outcome=WeatherRequestAttempt.Outcome.FAILED,
                ended_at=_clock_now(self.clock),
                message=message,
                http_status=200,
            )
            request.status = WeatherRequest.Status.FAILED
            request.failed_at = _clock_now(self.clock)
            request.latest_provider_message = message
            request.save(
                update_fields=["status", "failed_at", "latest_provider_message", "updated_at"]
            )
            raise
        except Exception as error:
            message = _full_exception_message(error)
            finish_attempt(
                attempt=attempt,
                outcome=WeatherRequestAttempt.Outcome.CRASHED,
                ended_at=_clock_now(self.clock),
                message=message,
            )
            request.status = WeatherRequest.Status.PENDING
            request.latest_provider_message = message
            request.retry_at = _clock_now(self.clock)
            request.save(
                update_fields=["status", "latest_provider_message", "retry_at", "updated_at"]
            )
            raise

    def fetch_reserved(
        self,
        *,
        spec: RequestSpec,
        attempt: WeatherRequestAttempt,
        provenance: Mapping[str, Any] | None = None,
        allow_completed_refetch: bool = False,
    ) -> ProviderResult:
        """Perform exactly one HTTP attempt for a reservation made by the caller."""
        return self.fetch(
            spec=spec,
            provenance=provenance,
            allow_completed_refetch=allow_completed_refetch,
            reserved_attempt=attempt,
        )


def fetch_weather(
    *,
    spec: RequestSpec,
    transport: Callable[..., Any] | None = None,
    clock: Callable[[], datetime] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    provenance: Mapping[str, Any] | None = None,
    allow_completed_refetch: bool = False,
    reserved_attempt: WeatherRequestAttempt | None = None,
) -> ProviderResult:
    """Execute one provider attempt through the durable service."""
    return WeatherProvider(
        transport=transport,
        clock=clock,
        timeout_seconds=timeout_seconds,
    ).fetch(
        spec=spec,
        provenance=provenance,
        allow_completed_refetch=allow_completed_refetch,
        reserved_attempt=reserved_attempt,
    )


def fetch_reserved_weather(
    *,
    spec: RequestSpec,
    attempt: WeatherRequestAttempt,
    transport: Callable[..., Any] | None = None,
    clock: Callable[[], datetime] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    provenance: Mapping[str, Any] | None = None,
    allow_completed_refetch: bool = False,
) -> ProviderResult:
    """Perform exactly one HTTP attempt for an existing quota reservation."""
    return WeatherProvider(
        transport=transport,
        clock=clock,
        timeout_seconds=timeout_seconds,
    ).fetch_reserved(
        spec=spec,
        attempt=attempt,
        provenance=provenance,
        allow_completed_refetch=allow_completed_refetch,
    )


request_weather = fetch_weather
