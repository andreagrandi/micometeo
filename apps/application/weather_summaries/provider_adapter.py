"""Adapt one validated provider result to the weather summaries contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .contracts import HourlySeries, NormalizedLocationResponse, NormalizedProviderResponse

if TYPE_CHECKING:
    from weather_requests.provider import ProviderResult


def normalized_provider_responses(
    *,
    result: ProviderResult,
) -> tuple[NormalizedProviderResponse, ...]:
    """Return one normalized summary response for each requested location."""
    retrieved_at = datetime.fromisoformat(str(result.metadata["retrieved_at"]))
    if retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=UTC)
    units_by_provider_name = {
        "precipitation": "mm",
        "temperature_2m": "deg_c",
        "soil_moisture_0_to_7cm": "m3_m3",
        "soil_temperature_0_to_7cm": "deg_c",
        "et0_fao_evapotranspiration": "mm",
    }
    provider_names = {
        "precipitation": "precipitation",
        "temperature_2m": "temperature",
        "soil_moisture_0_to_7cm": "soil_moisture",
        "soil_temperature_0_to_7cm": "soil_temperature",
        "et0_fao_evapotranspiration": "et0",
    }
    responses: list[NormalizedProviderResponse] = []
    for position, (cell, hourly) in enumerate(
        zip(result.spec.locations, result.raw_hourly, strict=True)
    ):
        location_metadata = result.metadata["locations"][position]
        timestamps = tuple(int(value) for value in hourly["time"])
        series = tuple(
            HourlySeries(
                name=provider_names[variable],
                unit=units_by_provider_name[variable],
                values=tuple(hourly[variable]),
            )
            for variable in result.spec.variables
        )
        responses.append(
            NormalizedProviderResponse(
                request_id=str(result.logical_request.id),
                attempt_id=result.attempt_id,
                retrieved_at=retrieved_at,
                provider_endpoint=result.spec.endpoint,
                model=result.spec.model,
                source_id=f"open-meteo:{result.logical_request.request_digest}",
                first_timestamp_utc=timestamps[0],
                closing_timestamp_utc=timestamps[-1],
                hourly_timestamps=timestamps,
                hourly_series=series,
                location=NormalizedLocationResponse(
                    cell_key=cell.key,
                    requested_latitude=cell.latitude,
                    requested_longitude=cell.longitude,
                    returned_latitude=location_metadata["latitude"],
                    returned_longitude=location_metadata["longitude"],
                    elevation_m=location_metadata.get("elevation"),
                    timezone=location_metadata.get("timezone", result.spec.timezone),
                    metadata=location_metadata,
                ),
                provider="Open-Meteo",
                requested_start=result.spec.start_date,
                requested_end=result.spec.end_date,
                metadata=dict(result.metadata),
            )
        )
    return tuple(responses)
