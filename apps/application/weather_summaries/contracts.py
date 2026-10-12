"""Immutable contracts shared by weather providers and summary storage."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
import math
from numbers import Real
from typing import Any
from uuid import UUID


UTC_HOURLY_VARIABLES = (
    "precipitation",
    "temperature",
    "soil_moisture",
    "soil_temperature",
    "et0",
)
REQUIRED_VARIABLES = ("precipitation", "temperature")
OPTIONAL_VARIABLES = (
    "soil_moisture",
    "soil_temperature",
    "et0",
)
VARIABLE_UNITS = {
    "precipitation": "mm",
    "temperature": "deg_c",
    "soil_moisture": "m3_m3",
    "soil_temperature": "deg_c",
    "et0": "mm",
}
_ALIASES = {
    "rain": "precipitation",
    "rain_mm": "precipitation",
    "precipitation": "precipitation",
    "temperature_2m": "temperature",
    "temperature": "temperature",
    "soil_moisture_0_to_7cm": "soil_moisture",
    "soil_moisture": "soil_moisture",
    "soil_temperature_0_to_7cm": "soil_temperature",
    "soil_temperature": "soil_temperature",
    "et0_fao_evapotranspiration": "et0",
    "et0": "et0",
}


def _utc_datetime(*, value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be an aware UTC datetime")
    return value.astimezone(UTC)


def _finite_coordinate(*, value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
    return float(value)


def canonical_variable_name(*, name: str) -> str:
    """Return the stored variable name for a provider variable name."""
    try:
        return _ALIASES[name]
    except KeyError as exc:
        raise ValueError(f"unsupported weather variable: {name}") from exc


@dataclass(frozen=True)
class NormalizedLocationResponse:
    """Describe requested and returned metadata for one weather cell."""

    cell_key: str
    requested_latitude: float
    requested_longitude: float
    returned_latitude: float
    returned_longitude: float
    elevation_m: float | None
    timezone: str = "Europe/Rome"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.cell_key:
            raise ValueError("cell_key must not be empty")
        for name in (
            "requested_latitude",
            "requested_longitude",
            "returned_latitude",
            "returned_longitude",
        ):
            object.__setattr__(self, name, _finite_coordinate(value=getattr(self, name), name=name))
        if not -90 <= self.requested_latitude <= 90 or not -90 <= self.returned_latitude <= 90:
            raise ValueError("latitude must be from -90 to 90")
        if not -180 <= self.requested_longitude <= 180 or not -180 <= self.returned_longitude <= 180:
            raise ValueError("longitude must be from -180 to 180")
        if self.elevation_m is not None:
            object.__setattr__(
                self,
                "elevation_m",
                _finite_coordinate(value=self.elevation_m, name="elevation_m"),
            )
        if not self.timezone:
            raise ValueError("timezone must not be empty")
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def requested_coordinates(self) -> tuple[float, float]:
        """Return requested latitude and longitude."""
        return self.requested_latitude, self.requested_longitude

    @property
    def cell_id(self) -> str:
        """Return the stable weather cell key under the grid-facing name."""
        return self.cell_key

    @property
    def returned_coordinates(self) -> tuple[float, float]:
        """Return provider latitude and longitude."""
        return self.returned_latitude, self.returned_longitude


@dataclass(frozen=True)
class HourlySeries:
    """Store one ordered hourly variable and its provider unit."""

    name: str
    unit: str
    values: tuple[float | None, ...]

    def __post_init__(self) -> None:
        canonical = canonical_variable_name(name=self.name)
        object.__setattr__(self, "name", canonical)
        if not self.unit:
            raise ValueError("hourly variable unit must not be empty")
        converted: list[float | None] = []
        for value in self.values:
            if value is None:
                converted.append(None)
                continue
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError(f"{canonical} values must be numeric or null")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"{canonical} values must be finite or null")
            if canonical in {"precipitation", "et0"} and number < 0:
                raise ValueError(f"{canonical} values must not be negative")
            if canonical == "soil_moisture" and not 0 <= number <= 1:
                raise ValueError("soil_moisture values must be from zero to one")
            converted.append(number)
        object.__setattr__(self, "values", tuple(converted))


@dataclass(frozen=True)
class NormalizedProviderResponse:
    """Represent one successful provider answer without retaining raw JSON."""

    request_id: str
    attempt_id: UUID
    retrieved_at: datetime
    provider_endpoint: str
    model: str
    source_id: str
    first_timestamp_utc: int
    closing_timestamp_utc: int
    hourly_timestamps: tuple[int, ...]
    hourly_series: tuple[HourlySeries, ...]
    location: NormalizedLocationResponse
    provider: str | None = None
    requested_start: date | None = None
    requested_end: date | None = None
    forecast_issue_time: datetime | None = None
    publication_time: datetime | None = None
    response_status: str = "success"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id or not self.provider_endpoint or not self.model or not self.source_id:
            raise ValueError("request_id, provider_endpoint, model and source_id are required")
        if self.provider is not None and not self.provider:
            raise ValueError("provider must not be empty")
        retrieved = _utc_datetime(value=self.retrieved_at, name="retrieved_at")
        assert retrieved is not None
        object.__setattr__(self, "retrieved_at", retrieved)
        for name in ("forecast_issue_time", "publication_time"):
            object.__setattr__(
                self,
                name,
                _utc_datetime(value=getattr(self, name), name=name),
            )
        if self.response_status != "success":
            raise ValueError("only successful provider responses can be normalized")
        timestamps = tuple(self.hourly_timestamps)
        if not timestamps:
            raise ValueError("hourly_timestamps must not be empty")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in timestamps):
            raise ValueError("hourly timestamps must be Unix integer seconds")
        if tuple(sorted(timestamps)) != timestamps or len(set(timestamps)) != len(timestamps):
            raise ValueError("hourly timestamps must be ordered and unique")
        if self.first_timestamp_utc != timestamps[0] or self.closing_timestamp_utc != timestamps[-1]:
            raise ValueError("first and closing timestamps must match the ordered hourly series")
        if any(value % 3600 for value in timestamps):
            raise ValueError("hourly timestamps must fall on UTC hour boundaries")
        series_by_name: dict[str, HourlySeries] = {}
        for series in self.hourly_series:
            if not isinstance(series, HourlySeries):
                raise ValueError("hourly_series must contain HourlySeries values")
            if series.name in series_by_name:
                raise ValueError(f"duplicate hourly variable: {series.name}")
            if len(series.values) != len(timestamps):
                raise ValueError(f"{series.name} values must match hourly_timestamps")
            expected_unit = VARIABLE_UNITS[series.name]
            if series.unit != expected_unit:
                raise ValueError(f"{series.name} must use unit {expected_unit}")
            series_by_name[series.name] = series
        object.__setattr__(self, "hourly_timestamps", timestamps)
        object.__setattr__(
            self,
            "hourly_series",
            tuple(series_by_name[name] for name in UTC_HOURLY_VARIABLES if name in series_by_name),
        )
        if self.requested_start is not None and (
            not isinstance(self.requested_start, date)
            or isinstance(self.requested_start, datetime)
        ):
            raise ValueError("requested_start must be a date")
        if self.requested_end is not None and (
            not isinstance(self.requested_end, date)
            or isinstance(self.requested_end, datetime)
        ):
            raise ValueError("requested_end must be a date")
        if self.requested_start and self.requested_end and self.requested_end < self.requested_start:
            raise ValueError("requested_end must not precede requested_start")
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def attempt_uuid(self) -> UUID:
        """Return the attempt identifier under the provider-neutral name."""
        return self.attempt_id

    @property
    def first_hour_utc(self) -> int:
        """Return the first Unix timestamp in the answer."""
        return self.first_timestamp_utc

    @property
    def closing_hour_utc(self) -> int:
        """Return the closing Unix timestamp in the answer."""
        return self.closing_timestamp_utc

    @property
    def variables(self) -> Mapping[str, tuple[float | None, ...]]:
        """Return ordered canonical hourly values."""
        return {series.name: series.values for series in self.hourly_series}

    @property
    def hourly(self) -> Mapping[str, tuple[float | None, ...]]:
        """Return canonical hourly arrays under the provider-facing name."""
        return self.variables

    @property
    def units(self) -> Mapping[str, str]:
        """Return ordered canonical units."""
        return {series.name: series.unit for series in self.hourly_series}

    @property
    def requested_coordinates(self) -> tuple[float, float]:
        """Return the requested provider coordinates."""
        return self.location.requested_coordinates

    @property
    def returned_coordinates(self) -> tuple[float, float]:
        """Return the coordinates reported by the provider."""
        return self.location.returned_coordinates

    @property
    def retrieval_time(self) -> datetime:
        """Return the actual UTC retrieval time."""
        return self.retrieved_at


def make_normalized_response(
    *,
    request_id: str,
    attempt_id: UUID,
    retrieved_at: datetime,
    provider_endpoint: str,
    model: str,
    source_id: str,
    hourly_timestamps: Sequence[int],
    variables: Mapping[str, Sequence[float | None]],
    units: Mapping[str, str],
    location: NormalizedLocationResponse,
    provider: str | None = None,
    requested_start: date | None = None,
    requested_end: date | None = None,
    forecast_issue_time: datetime | None = None,
    publication_time: datetime | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> NormalizedProviderResponse:
    """Build a normalized response from ordered provider arrays."""
    series = tuple(
        HourlySeries(name=name, unit=units[name], values=tuple(values))
        for name, values in variables.items()
    )
    timestamps = tuple(hourly_timestamps)
    if not timestamps:
        raise ValueError("hourly_timestamps must not be empty")
    return NormalizedProviderResponse(
        request_id=request_id,
        attempt_id=attempt_id,
        retrieved_at=retrieved_at,
        provider_endpoint=provider_endpoint,
        model=model,
        source_id=source_id,
        first_timestamp_utc=timestamps[0],
        closing_timestamp_utc=timestamps[-1],
        hourly_timestamps=timestamps,
        hourly_series=series,
        location=location,
        provider=provider,
        requested_start=requested_start,
        requested_end=requested_end,
        forecast_issue_time=forecast_issue_time,
        publication_time=publication_time,
        metadata=metadata or {},
    )
