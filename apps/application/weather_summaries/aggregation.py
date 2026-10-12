"""Turn one normalized hourly answer into immutable Italian daily values."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from micometeo.weather.features import ROME, day_start, hours_in_local_day

from .contracts import (
    VARIABLE_UNITS,
    NormalizedProviderResponse,
)


@dataclass(frozen=True)
class DailyWeather:
    """Store one local day and per-variable completeness evidence."""

    date: date
    rain_mm: float | None
    mean_temperature_c: float | None
    min_temperature_c: float | None
    et0_mm: float | None
    mean_soil_temperature_c: float | None
    mean_soil_moisture: float | None
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def values(self) -> dict[str, float | None]:
        """Return canonical stored values by variable name."""
        return {
            "rain_mm": self.rain_mm,
            "mean_temperature_c": self.mean_temperature_c,
            "min_temperature_c": self.min_temperature_c,
            "et0_mm": self.et0_mm,
            "mean_soil_temperature_c": self.mean_soil_temperature_c,
            "mean_soil_moisture": self.mean_soil_moisture,
        }

    @property
    def day(self) -> date:
        """Return the Italian date under the short name used by adapters."""
        return self.date


def _epoch(*, moment: datetime) -> int:
    return int(moment.astimezone(UTC).timestamp())


def _date_range(*, start: date, end: date) -> tuple[date, ...]:
    if end < start:
        raise ValueError("end date must not precede start date")
    return tuple(start + timedelta(days=offset) for offset in range((end - start).days + 1))


def _mean_or_none(*, values: list[float | None], expected: int) -> tuple[float | None, str, tuple[int, ...]]:
    null_hours = tuple(index for index, value in enumerate(values) if value is None)
    if len(values) != expected or null_hours:
        return None, "missing_hour", null_hours
    return round(sum(value for value in values if value is not None) / expected, 4), "complete", ()


def _sum_or_none(*, values: list[float | None], expected: int) -> tuple[float | None, str, tuple[int, ...]]:
    null_hours = tuple(index for index, value in enumerate(values) if value is None)
    if len(values) != expected or null_hours:
        return None, "missing_hour", null_hours
    return round(sum(value for value in values if value is not None), 4), "complete", ()


def _derive_range(*, response: NormalizedProviderResponse) -> tuple[date, date]:
    first = datetime.fromtimestamp(response.first_timestamp_utc, tz=UTC).astimezone(ROME).date()
    last = datetime.fromtimestamp(response.closing_timestamp_utc, tz=UTC).astimezone(ROME).date()
    if response.requested_start is not None:
        first = response.requested_start
    if response.requested_end is not None:
        last = response.requested_end
    elif last > first:
        last -= timedelta(days=1)
    return first, last


def aggregate_response(
    *,
    response: NormalizedProviderResponse,
    start: date | None = None,
    end: date | None = None,
) -> tuple[DailyWeather, ...]:
    """Aggregate requested hourly values using Europe/Rome midnight boundaries.

    Rain and reference evapotranspiration are hourly amounts ending at the next
    local hour, so the closing midnight belongs to the preceding date. Instant
    values use the half-open local-day interval and exclude that closing value.
    """
    requested_start, requested_end = _derive_range(response=response)
    first = start or requested_start
    last = end or requested_end
    if first < requested_start or last > requested_end:
        raise ValueError("aggregation range must stay inside the provider answer")
    timestamps = response.hourly_timestamps
    variables = response.variables
    results: list[DailyWeather] = []
    for current in _date_range(start=first, end=last):
        local_start = _epoch(moment=day_start(day=current))
        local_end = _epoch(moment=day_start(day=current + timedelta(days=1)))
        expected = hours_in_local_day(day=current)
        amount_indexes = [
            index
            for index, timestamp in enumerate(timestamps)
            if local_start < timestamp <= local_end
        ]
        instant_indexes = [
            index
            for index, timestamp in enumerate(timestamps)
            if local_start <= timestamp < local_end
        ]
        variable_metadata: dict[str, dict[str, Any]] = {}

        if "precipitation" not in variables:
            rain, rain_reason, rain_nulls = None, "required_variable_absent", ()
            rain_present_hours = 0
        else:
            precipitation_values = [variables["precipitation"][index] for index in amount_indexes]
            rain, rain_reason, rain_nulls = _sum_or_none(
                values=precipitation_values,
                expected=expected,
            )
            rain_present_hours = len(amount_indexes)
        variable_metadata["precipitation"] = {
            "unit": VARIABLE_UNITS["precipitation"],
            "expected_hours": expected,
            "present_hours": rain_present_hours,
            "null_hours": list(rain_nulls),
            "null_timestamps": [timestamps[amount_indexes[index]] for index in rain_nulls],
            "quality": "complete" if rain is not None else "checked_known_missing",
            "reason": rain_reason,
            "sample_boundary": "(start_midnight,next_midnight]",
        }

        if "temperature" not in variables:
            temperature, temperature_reason, temperature_nulls = None, "required_variable_absent", ()
            temperature_values: list[float | None] = []
            temperature_present_hours = 0
        else:
            temperature_values = [variables["temperature"][index] for index in instant_indexes]
            temperature, temperature_reason, temperature_nulls = _mean_or_none(
                values=temperature_values,
                expected=expected,
            )
            temperature_present_hours = len(instant_indexes)
        minimum_temperature = (
            min(value for value in temperature_values if value is not None)
            if temperature is not None
            else None
        )
        variable_metadata["temperature"] = {
            "unit": VARIABLE_UNITS["temperature"],
            "expected_hours": expected,
            "present_hours": temperature_present_hours,
            "null_hours": list(temperature_nulls),
            "null_timestamps": [timestamps[instant_indexes[index]] for index in temperature_nulls],
            "quality": "complete" if temperature is not None else "checked_known_missing",
            "reason": temperature_reason,
            "sample_boundary": "[start_midnight,next_midnight)",
        }

        optional_values: dict[str, float | None] = {}
        for variable, column, combine in (
            ("et0", "et0_mm", "sum"),
            ("soil_temperature", "mean_soil_temperature_c", "mean"),
            ("soil_moisture", "mean_soil_moisture", "mean"),
        ):
            if variable not in variables:
                optional_values[column] = None
                variable_metadata[variable] = {
                    "unit": VARIABLE_UNITS[variable],
                    "expected_hours": expected,
                    "present_hours": 0,
                    "null_hours": [],
                    "null_timestamps": [],
                    "quality": "absent_optional",
                    "reason": "optional_variable_absent",
                    "sample_boundary": "(start_midnight,next_midnight]"
                    if combine == "sum"
                    else "[start_midnight,next_midnight)",
                }
                continue
            indexes = amount_indexes if combine == "sum" else instant_indexes
            values = [variables[variable][index] for index in indexes]
            if combine == "sum":
                value, reason, nulls = _sum_or_none(values=values, expected=expected)
            else:
                value, reason, nulls = _mean_or_none(values=values, expected=expected)
            optional_values[column] = value
            variable_metadata[variable] = {
                "unit": VARIABLE_UNITS[variable],
                "expected_hours": expected,
                "present_hours": len(indexes),
                "null_hours": list(nulls),
                "null_timestamps": [timestamps[indexes[index]] for index in nulls],
                "quality": "complete" if value is not None else "checked_known_missing",
                "reason": reason,
                "sample_boundary": "(start_midnight,next_midnight]"
                if combine == "sum"
                else "[start_midnight,next_midnight)",
            }

        status = (
            "complete"
            if rain is not None and temperature is not None
            else "checked_known_missing"
        )
        results.append(
            DailyWeather(
                date=current,
                rain_mm=rain,
                mean_temperature_c=temperature,
                min_temperature_c=minimum_temperature,
                et0_mm=optional_values["et0_mm"],
                mean_soil_temperature_c=optional_values["mean_soil_temperature_c"],
                mean_soil_moisture=optional_values["mean_soil_moisture"],
                status=status,
                metadata={
                    "expected_hours": expected,
                    "present_amount_hours": len(amount_indexes),
                    "present_instant_hours": len(instant_indexes),
                    "variables": variable_metadata,
                },
            )
        )
    return tuple(results)


def aggregate_hourly(
    *,
    hourly_timestamps: tuple[int, ...],
    variables: dict[str, tuple[float | None, ...]],
    start: date,
    end: date,
) -> tuple[DailyWeather, ...]:
    """Aggregate canonical arrays through a small pure convenience wrapper."""
    from uuid import uuid4

    from .contracts import HourlySeries, NormalizedLocationResponse

    if not hourly_timestamps:
        raise ValueError("hourly_timestamps must not be empty")
    series = tuple(
        HourlySeries(name=name, unit=VARIABLE_UNITS[name], values=values)
        for name, values in variables.items()
    )
    response = NormalizedProviderResponse(
        request_id="pure-aggregation",
        attempt_id=uuid4(),
        retrieved_at=datetime.now(tz=UTC),
        provider_endpoint="pure-aggregation",
        model="pure-aggregation",
        source_id="pure-aggregation",
        first_timestamp_utc=hourly_timestamps[0],
        closing_timestamp_utc=hourly_timestamps[-1],
        hourly_timestamps=hourly_timestamps,
        hourly_series=series,
        location=NormalizedLocationResponse(
            cell_key="pure-aggregation",
            requested_latitude=0.0,
            requested_longitude=0.0,
            returned_latitude=0.0,
            returned_longitude=0.0,
            elevation_m=None,
        ),
        requested_start=start,
        requested_end=end,
    )
    return aggregate_response(response=response, start=start, end=end)
