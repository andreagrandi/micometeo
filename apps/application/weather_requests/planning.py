"""Build canonical Open-Meteo request specifications for Italian dates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_UP
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from micometeo.weather.openmeteo import FORECAST_URL, HOURLY_VARIABLES, quota_weight

from .eligibility import WeatherCell

ROME = ZoneInfo("Europe/Rome")
PROVIDER_TIMEZONE = "GMT"
PROVIDER_TIME_FORMAT = "unixtime"
DEFAULT_MODEL = "best_match"
MAX_LOCATIONS = 100
MAX_VARIABLES = 10
FIRST_LOOKBACK_DAYS = 21
LAST_FORECAST_DAYS = 7
OVERLAP_DAYS = 3
MAX_HISTORY_PART_DAYS = 13
DEFAULT_PROVIDER_OPTIONS = {
    "temperature_unit": "celsius",
    "precipitation_unit": "mm",
    "cell_selection": "land",
}
RESERVED_QUERY_KEYS = frozenset(
    {
        "latitude",
        "longitude",
        "hourly",
        "models",
        "timezone",
        "timeformat",
        "start_hour",
        "end_hour",
        "start_date",
        "end_date",
        "past_days",
        "forecast_days",
        "past_hours",
        "forecast_hours",
        "temperature_unit",
        "precipitation_unit",
        "wind_speed_unit",
        "pressure_unit",
        "length_unit",
        "energy_unit",
        "cell_selection",
    }
)


class RequestPlanningError(ValueError):
    """Report an invalid request plan."""


def _date_range(*, start: date, end: date) -> tuple[date, ...]:
    if end < start:
        return ()
    return tuple(start + timedelta(days=index) for index in range((end - start).days + 1))


def required_dates(*, assessment_date: date) -> tuple[date, ...]:
    """Return the 21 previous, current and seven following Italian dates."""
    return _date_range(
        start=assessment_date - timedelta(days=FIRST_LOOKBACK_DAYS),
        end=assessment_date + timedelta(days=LAST_FORECAST_DAYS),
    )


def local_midnight_utc(*, day: date) -> datetime:
    """Return one Italian midnight as an aware UTC datetime."""
    return datetime.combine(day, time.min, tzinfo=ROME).astimezone(UTC)


def requested_utc_bounds(*, start_date: date, end_date: date) -> tuple[datetime, datetime]:
    """Return inclusive hourly bounds for local dates and preceding-hour rain."""
    return local_midnight_utc(day=start_date), local_midnight_utc(day=end_date + timedelta(days=1))


def requested_hour_count(*, start_date: date, end_date: date) -> int:
    """Count hourly timestamps from the first local midnight through closing midnight."""
    start, end = requested_utc_bounds(start_date=start_date, end_date=end_date)
    return int((end - start).total_seconds() // 3600) + 1


def nominal_weight(*, variables: int, days: int, places: int) -> Decimal:
    """Return the provider's nominal weighted call count."""
    if variables <= 0 or days <= 0 or places <= 0:
        raise RequestPlanningError("Variables, dates and places must be positive.")
    value = max(Decimal("1"), Decimal(variables) / Decimal("10"))
    value *= max(Decimal("1"), Decimal(days) / Decimal("14"))
    return (value * Decimal(places)).quantize(Decimal("0.000001"), rounding=ROUND_UP)


def reservation_weight(*, variables: int, start_date: date, end_date: date, places: int) -> Decimal:
    """Return the conservative weighted reservation for hourly timestamps."""
    if variables <= 0 or places <= 0:
        raise RequestPlanningError("Variables and places must be positive.")
    hourly_days = (
        Decimal(requested_hour_count(start_date=start_date, end_date=end_date)) / Decimal("24")
    ).to_integral_value(rounding=ROUND_CEILING)
    value = max(Decimal("1"), Decimal(variables) / Decimal("10")) * max(
        Decimal("1"), hourly_days / Decimal("14")
    )
    return (value * Decimal(places)).quantize(Decimal("0.000001"), rounding=ROUND_UP)


@dataclass(frozen=True)
class RequestSpec:
    """Canonical query details shared by accounting and the provider."""

    endpoint: str
    locations: tuple[WeatherCell, ...]
    model: str
    variables: tuple[str, ...]
    start_date: date
    end_date: date
    timezone: str = PROVIDER_TIMEZONE
    timeformat: str = PROVIDER_TIME_FORMAT
    start_hour: int = 0
    end_hour: int = 23
    options: Mapping[str, str] = field(default_factory=dict)
    forest_build_version: str = ""
    query: Mapping[str, str] = field(init=False)
    canonical: Mapping[str, Any] = field(init=False, repr=False)
    digest: str = field(init=False)
    nominal_weight: Decimal = field(init=False)
    reservation_weight: Decimal = field(init=False)
    utc_start: datetime = field(init=False)
    utc_end: datetime = field(init=False)

    def __post_init__(self) -> None:
        if not self.locations:
            raise RequestPlanningError("A provider request needs at least one location.")
        if len(self.locations) > MAX_LOCATIONS:
            raise RequestPlanningError(f"A request may contain at most {MAX_LOCATIONS} locations.")
        ordered_locations = tuple(sorted(self.locations, key=lambda cell: cell.key))
        if len({cell.key for cell in ordered_locations}) != len(ordered_locations):
            raise RequestPlanningError("A provider request may contain each weather cell only once.")
        object.__setattr__(self, "locations", ordered_locations)
        if not self.variables or len(self.variables) > MAX_VARIABLES:
            raise RequestPlanningError(f"A request may contain at most {MAX_VARIABLES} variables.")
        if tuple(self.variables) != tuple(dict.fromkeys(self.variables)):
            raise RequestPlanningError("Hourly variables must be unique and ordered.")
        unsupported = set(self.variables).difference(HOURLY_VARIABLES)
        if unsupported:
            raise RequestPlanningError(f"Unsupported hourly variables: {sorted(unsupported)}")
        if self.end_date < self.start_date:
            raise RequestPlanningError("The request end date must not precede its start date.")
        if not 0 <= self.start_hour <= 23 or not 0 <= self.end_hour <= 23:
            raise RequestPlanningError("Provider hours must be between zero and 23.")
        utc_start, utc_end = requested_utc_bounds(
            start_date=self.start_date,
            end_date=self.end_date,
        )
        object.__setattr__(self, "utc_start", utc_start)
        object.__setattr__(self, "utc_end", utc_end)
        ordered_options = _validate_provider_options(options=self.options)
        query: dict[str, str] = {
            "latitude": ",".join(f"{cell.latitude:.2f}" for cell in self.locations),
            "longitude": ",".join(f"{cell.longitude:.2f}" for cell in self.locations),
            "hourly": ",".join(self.variables),
            "models": self.model,
            "timezone": self.timezone,
            "timeformat": self.timeformat,
            "start_hour": utc_start.strftime("%Y-%m-%dT%H:%M"),
            "end_hour": utc_end.strftime("%Y-%m-%dT%H:%M"),
            **ordered_options,
        }
        canonical = {
            "endpoint": self.endpoint,
            "query": query,
            "forest_build_version": self.forest_build_version,
            "local_date_start": self.start_date.isoformat(),
            "local_date_end": self.end_date.isoformat(),
            "utc_start": utc_start.isoformat(),
            "utc_end": utc_end.isoformat(),
        }
        encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        object.__setattr__(self, "query", MappingProxyType(query))
        object.__setattr__(self, "canonical", MappingProxyType(canonical))
        object.__setattr__(self, "digest", hashlib.sha256(encoded.encode("utf-8")).hexdigest())
        days = (self.end_date - self.start_date).days + 1
        object.__setattr__(
            self,
            "nominal_weight",
            nominal_weight(variables=len(self.variables), days=days, places=len(self.locations)),
        )
        object.__setattr__(
            self,
            "reservation_weight",
            reservation_weight(
                variables=len(self.variables),
                start_date=self.start_date,
                end_date=self.end_date,
                places=len(self.locations),
            ),
        )

    @property
    def query_string(self) -> str:
        """Return the encoded provider query with every identity parameter."""
        return urlencode(dict(self.query))

    @property
    def days(self) -> int:
        """Return the number of inclusive Italian dates in this plan."""
        return (self.end_date - self.start_date).days + 1

    @property
    def variables_count(self) -> int:
        """Return the number of hourly variables."""
        return len(self.variables)

    @property
    def locations_count(self) -> int:
        """Return the number of weather places."""
        return len(self.locations)

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-safe request metadata."""
        return {
            "endpoint": self.endpoint,
            "query": dict(self.query),
            "forest_build_version": self.forest_build_version,
            "local_date_start": self.start_date.isoformat(),
            "local_date_end": self.end_date.isoformat(),
            "utc_start": self.utc_start.isoformat(),
            "utc_end": self.utc_end.isoformat(),
            "digest": self.digest,
            "nominal_weight": str(self.nominal_weight),
            "reservation_weight": str(self.reservation_weight),
        }


def _normalise_stored_dates(stored_dates: Iterable[date] | None) -> set[date]:
    if stored_dates is None:
        return set()
    return {value if isinstance(value, date) else date.fromisoformat(str(value)) for value in stored_dates}


def _request_span(
    *,
    missing: Sequence[date],
    first_request: bool,
) -> tuple[date, date]:
    start = min(missing)
    end = max(missing)
    if first_request:
        return start, end
    return (
        start - timedelta(days=OVERLAP_DAYS),
        end,
    )


def _provider_options(*, options: Mapping[str, str] | None) -> dict[str, str]:
    """Return the canonical provider options for one request."""
    return {
        **DEFAULT_PROVIDER_OPTIONS,
        **{str(key): str(value) for key, value in (options or {}).items()},
    }


def _validate_provider_options(*, options: Mapping[str, str]) -> dict[str, str]:
    """Reject options that can change the canonical request contract."""
    ordered = dict(sorted((str(key), str(value)) for key, value in options.items()))
    collisions = sorted(
        key
        for key in ordered
        if key in RESERVED_QUERY_KEYS
        and ordered[key] != DEFAULT_PROVIDER_OPTIONS.get(key)
    )
    if collisions:
        names = ", ".join(collisions)
        raise RequestPlanningError(f"Options cannot override reserved query keys: {names}.")
    return ordered


def _build_request_spec_for_span(
    *,
    locations: Sequence[WeatherCell],
    start_date: date,
    end_date: date,
    model: str,
    variables: Sequence[str],
    endpoint: str,
    options: Mapping[str, str] | None,
    forest_build_version: str,
) -> RequestSpec:
    """Build one canonical request for an already selected local date span."""
    utc_start, utc_end = requested_utc_bounds(start_date=start_date, end_date=end_date)
    return RequestSpec(
        endpoint=endpoint,
        locations=tuple(locations),
        model=model,
        variables=tuple(variables),
        start_date=start_date,
        end_date=end_date,
        timezone=PROVIDER_TIMEZONE,
        timeformat=PROVIDER_TIME_FORMAT,
        start_hour=utc_start.hour,
        end_hour=utc_end.hour,
        options=_provider_options(options=options),
        forest_build_version=forest_build_version,
    )


def build_request_spec(
    *,
    locations: Sequence[WeatherCell],
    assessment_date: date,
    stored_dates: Iterable[date] | None = None,
    model: str = DEFAULT_MODEL,
    variables: Sequence[str] = HOURLY_VARIABLES,
    endpoint: str = FORECAST_URL,
    options: Mapping[str, str] | None = None,
    forest_build_version: str = "",
) -> RequestSpec | None:
    """Build one request for missing dates and a three-day overlap."""
    stored = _normalise_stored_dates(stored_dates)
    required = required_dates(assessment_date=assessment_date)
    missing = [day for day in required if day not in stored]
    if not missing:
        return None
    start, end = _request_span(
        missing=missing,
        first_request=not stored,
    )
    if stored and (end - start).days + 1 > 14:
        raise RequestPlanningError(
            "The missing stored history needs multiple requests; use plan_cell_request_specs."
        )
    return _build_request_spec_for_span(
        locations=locations,
        start_date=start,
        end_date=end,
        model=model,
        variables=variables,
        endpoint=endpoint,
        options=options,
        forest_build_version=forest_build_version,
    )


plan_request = build_request_spec
build_request_plan = build_request_spec


def _contiguous_ranges(*, dates: Sequence[date]) -> tuple[tuple[date, date], ...]:
    """Return inclusive ranges from dates that are already sorted."""
    if not dates:
        return ()
    ranges: list[tuple[date, date]] = []
    start = previous = dates[0]
    for current in dates[1:]:
        if current != previous + timedelta(days=1):
            ranges.append((start, previous))
            start = current
        previous = current
    ranges.append((start, previous))
    return tuple(ranges)


def _history_request_specs(
    *,
    locations: Sequence[WeatherCell],
    missing_dates: Sequence[date],
    model: str,
    variables: Sequence[str],
    endpoint: str,
    options: Mapping[str, str] | None,
    forest_build_version: str,
) -> tuple[RequestSpec, ...]:
    """Build bounded historical requests with one reserved call per place."""
    result: list[RequestSpec] = []
    for range_start, range_end in _contiguous_ranges(dates=missing_dates):
        current = range_start
        while current <= range_end:
            candidate_end = min(
                range_end,
                current + timedelta(days=MAX_HISTORY_PART_DAYS - 1),
            )
            while True:
                spec = _build_request_spec_for_span(
                    locations=locations,
                    start_date=current,
                    end_date=candidate_end,
                    model=model,
                    variables=variables,
                    endpoint=endpoint,
                    options=options,
                    forest_build_version=forest_build_version,
                )
                if spec.reservation_weight <= len(locations):
                    break
                if candidate_end <= current:
                    raise RequestPlanningError(
                        "A historical request cannot fit one conservative call per place."
                    )
                candidate_end -= timedelta(days=1)
            result.append(spec)
            current = candidate_end + timedelta(days=1)
    return tuple(result)


def plan_cell_request_specs(
    *,
    locations: Sequence[WeatherCell],
    assessment_date: date,
    has_previous_snapshot: bool,
    completed_dates: Iterable[date] | None = None,
    model: str = DEFAULT_MODEL,
    variables: Sequence[str] = HOURLY_VARIABLES,
    endpoint: str = FORECAST_URL,
    options: Mapping[str, str] | None = None,
    forest_build_version: str = "",
) -> tuple[RequestSpec, ...]:
    """Plan safe first or refresh requests for one ordered cell set."""
    if not locations:
        return ()
    required = required_dates(assessment_date=assessment_date)
    if not has_previous_snapshot:
        return (
            _build_request_spec_for_span(
                locations=locations,
                start_date=required[0],
                end_date=required[-1],
                model=model,
                variables=variables,
                endpoint=endpoint,
                options=options,
                forest_build_version=forest_build_version,
            ),
        )
    completed = _normalise_stored_dates(completed_dates).intersection(required)
    normal_start = assessment_date - timedelta(days=OVERLAP_DAYS)
    history_end = normal_start - timedelta(days=1)
    missing_history = tuple(
        day for day in required if day <= history_end and day not in completed
    )
    history_specs = _history_request_specs(
        locations=locations,
        missing_dates=missing_history,
        model=model,
        variables=variables,
        endpoint=endpoint,
        options=options,
        forest_build_version=forest_build_version,
    )
    normal_spec = _build_request_spec_for_span(
        locations=locations,
        start_date=normal_start,
        end_date=required[-1],
        model=model,
        variables=variables,
        endpoint=endpoint,
        options=options,
        forest_build_version=forest_build_version,
    )
    return (*history_specs, normal_spec)


def plan_requests(
    *,
    locations: Sequence[WeatherCell],
    assessment_date: date,
    stored_dates: Iterable[date] | None = None,
    model: str = DEFAULT_MODEL,
    variables: Sequence[str] = HOURLY_VARIABLES,
    endpoint: str = FORECAST_URL,
    options: Mapping[str, str] | None = None,
    forest_build_version: str = "",
) -> tuple[RequestSpec, ...]:
    """Plan one or more requests, batching locations in groups of one hundred."""
    if not locations:
        return ()
    ordered_locations = tuple(sorted(locations, key=lambda cell: cell.key))
    chunks = [
        ordered_locations[index : index + MAX_LOCATIONS]
        for index in range(0, len(ordered_locations), MAX_LOCATIONS)
    ]
    specs: list[RequestSpec] = []
    for chunk in chunks:
        spec = build_request_spec(
            locations=chunk,
            assessment_date=assessment_date,
            stored_dates=stored_dates,
            model=model,
            variables=variables,
            endpoint=endpoint,
            options=options,
            forest_build_version=forest_build_version,
        )
        if spec is not None:
            specs.append(spec)
    return tuple(specs)


def canonical_request_digest(*, spec: RequestSpec) -> str:
    """Return the digest of every provider query and request option."""
    return spec.digest


def request_compatibility_key(*, spec: RequestSpec) -> tuple[Any, ...]:
    """Return fields that must match before locations can share one request."""
    return (
        spec.endpoint,
        spec.model,
        spec.variables,
        spec.start_date,
        spec.end_date,
        spec.timezone,
        spec.timeformat,
        spec.start_hour,
        spec.end_hour,
        tuple(sorted(spec.options.items())),
        spec.forest_build_version,
    )


def combine_request_specs(
    *,
    specs: Sequence[RequestSpec],
    locations: Sequence[WeatherCell] | None = None,
) -> RequestSpec:
    """Build one request from compatible plans and at most one hundred cells."""
    if not specs:
        raise RequestPlanningError("At least one request plan is required.")
    first = specs[0]
    key = request_compatibility_key(spec=first)
    if any(request_compatibility_key(spec=spec) != key for spec in specs[1:]):
        raise RequestPlanningError("Only plans with identical date and provider options may be combined.")
    chosen = tuple(locations) if locations is not None else tuple(
        cell for spec in specs for cell in spec.locations
    )
    if len(chosen) > MAX_LOCATIONS:
        raise RequestPlanningError(f"A request may contain at most {MAX_LOCATIONS} locations.")
    return RequestSpec(
        endpoint=first.endpoint,
        locations=chosen,
        model=first.model,
        variables=first.variables,
        start_date=first.start_date,
        end_date=first.end_date,
        timezone=first.timezone,
        timeformat=first.timeformat,
        start_hour=first.start_hour,
        end_hour=first.end_hour,
        options=first.options,
        forest_build_version=first.forest_build_version,
    )


def quota_weight_for_spec(*, spec: RequestSpec) -> float:
    """Return the research client's nominal float weight for compatibility."""
    return quota_weight(variables=spec.variables_count, days=spec.days) * spec.locations_count


quota_reservation_weight = reservation_weight
