"""Compact result and read contracts shared by estimate consumers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


UNAVAILABLE_REASON_CODES: dict[str, int] = {
    "older_rain": 128,
    "recent_rain": 129,
    "target_temperature": 130,
    "reference_altitude": 131,
    "square_altitude": 132,
    "missing_forest_data": 133,
    "forest_below_minimum": 134,
    "weather_summary_missing": 135,
    "terrain_data_missing": 136,
    "period_temperature": 137,
    "weather_history": 138,
    "missing_rain_mm": 139,
    "missing_temperature_c": 140,
    "missing_et0_mm": 141,
}
UNAVAILABLE_CODE_REASONS = {value: key for key, value in UNAVAILABLE_REASON_CODES.items()}


class EstimateReadStatus(StrEnum):
    """Describe the state returned for one requested square and date."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NO_FOREST = "noforest"
    NO_RESULT_YET = "noresultyet"
    UNKNOWN = "unknown"
    EXPIRED = "expired"


@dataclass(frozen=True)
class EstimateDay:
    """Represent one decoded value for one target date."""

    target_date: date
    percentage: int | None
    unavailable_reason: str | None

    @property
    def available(self) -> bool:
        """Return whether the day has a whole percentage."""
        return self.percentage is not None


@dataclass(frozen=True)
class EstimateRead:
    """Represent one map or detail read without falling back to another update."""

    status: EstimateReadStatus
    forest_cell_id: int
    target_date: date | None = None
    assessment_date: date | None = None
    update_id: UUID | None = None
    percentage: int | None = None
    unavailable_reason: str | None = None
    calculated_at: datetime | None = None
    method_version: str | None = None
    message_key: str = ""
    facts: tuple[dict[str, Any], ...] = ()

    @property
    def state(self) -> str:
        """Return the machine-readable state value."""
        return self.status.value

    def as_dict(self) -> dict[str, Any]:
        """Return the shared map and detail response shape."""
        return {
            "state": self.status.value,
            "forest_cell_id": self.forest_cell_id,
            "target_date": self.target_date.isoformat() if self.target_date else None,
            "assessment_date": (
                self.assessment_date.isoformat() if self.assessment_date else None
            ),
            "update_id": str(self.update_id) if self.update_id else None,
            "percentage": self.percentage,
            "unavailable_reason": self.unavailable_reason,
            "calculated_at": self.calculated_at.isoformat() if self.calculated_at else None,
            "method_version": self.method_version,
            "message_key": self.message_key,
            "facts": list(self.facts),
        }


def encode_result_bytes(
    *,
    percentages: tuple[int | None, ...] | list[int | None],
    unavailable_reasons: tuple[str | None, ...] | list[str | None],
) -> bytes:
    """Encode exactly eight percentages and documented unavailable codes."""
    if len(percentages) != 8 or len(unavailable_reasons) != 8:
        raise ValueError("An estimate result must contain exactly eight target dates.")
    encoded = bytearray()
    for percentage, reason in zip(percentages, unavailable_reasons, strict=True):
        if percentage is not None:
            if isinstance(percentage, bool) or not isinstance(percentage, int):
                raise ValueError("Estimate percentages must be whole integers.")
            if not 0 <= percentage <= 100:
                raise ValueError("Estimate percentages must be from zero through one hundred.")
            if reason is not None:
                raise ValueError("An available percentage cannot have an unavailable reason.")
            encoded.append(percentage)
            continue
        if reason not in UNAVAILABLE_REASON_CODES:
            raise ValueError(f"Unknown estimate unavailable reason: {reason!r}.")
        encoded.append(UNAVAILABLE_REASON_CODES[reason])
    return bytes(encoded)


def decode_result_bytes(*, values: bytes | bytearray | memoryview) -> tuple[int | str, ...]:
    """Decode eight bytes into percentages or stable unavailable reasons."""
    raw = bytes(values)
    if len(raw) != 8:
        raise ValueError("An estimate result must contain exactly eight bytes.")
    decoded: list[int | str] = []
    for value in raw:
        if 0 <= value <= 100:
            decoded.append(value)
        elif value in UNAVAILABLE_CODE_REASONS:
            decoded.append(UNAVAILABLE_CODE_REASONS[value])
        else:
            raise ValueError(f"Unknown estimate result byte: {value}.")
    return tuple(decoded)


def decode_result_days(
    *,
    values: bytes | bytearray | memoryview,
    assessment_date: date,
) -> tuple[EstimateDay, ...]:
    """Decode eight stored bytes into assessment day through day seven."""
    decoded = decode_result_bytes(values=values)
    return tuple(
        EstimateDay(
            target_date=date.fromordinal(assessment_date.toordinal() + offset),
            percentage=value if isinstance(value, int) else None,
            unavailable_reason=value if isinstance(value, str) else None,
        )
        for offset, value in enumerate(decoded)
    )
