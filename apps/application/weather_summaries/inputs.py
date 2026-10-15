"""Adapt stored summaries to the frozen experimental forecast method."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from sporameteo.forecast_method import ForecastInputs, NumericInput


@dataclass(frozen=True)
class WeatherNumericInputs:
    """Weather values needed by the forecast method, with provenance."""

    old_rain: NumericInput
    recent_rain: NumericInput
    target_temperature: NumericInput
    reference_altitude: NumericInput


@dataclass(frozen=True)
class CanonicalForecastInputs:
    """All method inputs before the separate habitat adapter supplies values."""

    assessment_date: date
    target_date: date
    old_rain: NumericInput
    recent_rain: NumericInput
    target_temperature: NumericInput
    reference_altitude: NumericInput
    square_altitude: NumericInput | None = None
    forest_share: NumericInput | None = None

    def as_forecast_inputs(self) -> ForecastInputs:
        """Return the exact input contract consumed by the frozen method."""
        return ForecastInputs(
            assessment_date=self.assessment_date,
            target_date=self.target_date,
            old_rain=self.old_rain,
            recent_rain=self.recent_rain,
            target_temperature=self.target_temperature,
            reference_altitude=self.reference_altitude,
            square_altitude=self.square_altitude,
            forest_share=self.forest_share,
        )


def _get(*, summary: Any, name: str, default: Any = None) -> Any:
    if isinstance(summary, dict):
        return summary.get(name, default)
    return getattr(summary, name, default)


def _metadata(*, summary: Any, section: str) -> dict[str, Any]:
    metadata = _get(summary=summary, name="metadata", default={}) or {}
    section_metadata = metadata.get(section, {}) if isinstance(metadata, dict) else {}
    return section_metadata if isinstance(section_metadata, dict) else {}


def _provenance_ids(*, summary: Any, metadata: dict[str, Any], name: str) -> tuple[str, ...]:
    """Return ordered, unique provenance IDs from a summary section."""
    values = metadata.get(name)
    if not values:
        values = _get(summary=summary, name=name, default=[])
    if isinstance(values, str):
        values = [values]
    if not values:
        return ()
    return tuple(dict.fromkeys(str(value) for value in values if value))


def _composite_source_id(*, section: str, source_ids: tuple[str, ...]) -> str:
    """Return a stable identity for all source rows in one summary section."""
    if not source_ids:
        return f"weather-summary:{section}"
    encoded = json.dumps(source_ids, ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"weather-summary:{section}:{digest}"


def _numeric(
    *,
    summary: Any,
    value: float | None,
    unit: str,
    section: str,
    default_start: date,
    default_end: date,
    semantic: str | None = None,
) -> NumericInput:
    metadata = _metadata(summary=summary, section=section)
    source_ids = _provenance_ids(summary=summary, metadata=metadata, name="source_ids")
    source_id = _composite_source_id(section=section, source_ids=source_ids)
    start = metadata.get("period_start")
    end = metadata.get("period_end")
    try:
        period_start = date.fromisoformat(start) if start else default_start
        period_end = date.fromisoformat(end) if end else default_end
    except (TypeError, ValueError):
        period_start, period_end = default_start, default_end
    completed = int(metadata.get("completed_day_count", 0))
    forecast = int(metadata.get("forecast_day_count", 0))
    return NumericInput(
        value=value,
        unit=unit,
        source_id=str(source_id),
        period_start=period_start,
        period_end=period_end,
        completed_day_count=completed,
        forecast_day_count=forecast,
        quality=metadata.get("retrieval_quality"),
        semantic=semantic,
    )


def weather_numeric_inputs(summary: Any) -> WeatherNumericInputs:
    """Return weather inputs while retaining missing values and their evidence."""
    assessment_date = _get(summary=summary, name="assessment_date")
    if assessment_date is None:
        snapshot = _get(summary=summary, name="snapshot")
        assessment_date = _get(summary=snapshot, name="assessment_date")
    if not isinstance(assessment_date, date) or hasattr(assessment_date, "hour"):
        raise ValueError("summary must expose assessment_date")
    target_date = _get(summary=summary, name="target_date")
    if not isinstance(target_date, date) or hasattr(target_date, "hour"):
        raise ValueError("summary must expose target_date")
    old_start = target_date.fromordinal(target_date.toordinal() - 21)
    old_end = target_date.fromordinal(target_date.toordinal() - 8)
    recent_start = target_date.fromordinal(target_date.toordinal() - 7)
    recent_end = target_date.fromordinal(target_date.toordinal() - 1)
    snapshot = _get(summary=summary, name="snapshot")
    elevation = _get(summary=snapshot, name="reference_elevation_m")
    source_ids = _provenance_ids(
        summary=snapshot,
        metadata=_metadata(summary=summary, section="reference_altitude"),
        name="source_ids",
    )
    return WeatherNumericInputs(
        old_rain=_numeric(
            summary=summary,
            value=_get(summary=summary, name="old_rain_mm"),
            unit="mm",
            section="old_rain",
            default_start=old_start,
            default_end=old_end,
        ),
        recent_rain=_numeric(
            summary=summary,
            value=_get(summary=summary, name="recent_rain_mm"),
            unit="mm",
            section="recent_rain",
            default_start=recent_start,
            default_end=recent_end,
        ),
        target_temperature=_numeric(
            summary=summary,
            value=_get(summary=summary, name="target_mean_temperature_c"),
            unit="deg_c",
            section="target",
            default_start=target_date,
            default_end=target_date,
            semantic="temperature_at_reference_altitude",
        ),
        reference_altitude=NumericInput(
            value=elevation,
            unit="m",
            source_id=_composite_source_id(section="elevation", source_ids=source_ids),
            period_start=assessment_date,
            period_end=assessment_date,
            completed_day_count=1,
            forecast_day_count=0,
            quality="complete" if elevation is not None else "missing",
        ),
    )


def canonical_forecast_inputs(
    summary: Any,
    square_altitude: NumericInput | None = None,
    forest_share: NumericInput | None = None,
) -> CanonicalForecastInputs:
    """Combine weather values with optional terrain and forest values."""
    weather = weather_numeric_inputs(summary=summary)
    assessment_date = _get(summary=summary, name="assessment_date")
    if assessment_date is None:
        snapshot = _get(summary=summary, name="snapshot")
        assessment_date = _get(summary=snapshot, name="assessment_date")
    target_date = _get(summary=summary, name="target_date")
    if not isinstance(assessment_date, date) or hasattr(assessment_date, "hour"):
        raise ValueError("summary must expose assessment_date")
    if not isinstance(target_date, date) or hasattr(target_date, "hour"):
        raise ValueError("summary must expose target_date")
    return CanonicalForecastInputs(
        assessment_date=assessment_date,
        target_date=target_date,
        old_rain=weather.old_rain,
        recent_rain=weather.recent_rain,
        target_temperature=weather.target_temperature,
        reference_altitude=weather.reference_altitude,
        square_altitude=square_altitude,
        forest_share=forest_share,
    )
