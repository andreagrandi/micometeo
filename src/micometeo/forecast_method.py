"""Calculate the experimental porcini growth estimate for one 500 m square."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import math
from numbers import Real


METHOD_VERSION = "porcini-experimental-v1"
EVENT_KEY = "visible_porcini_fruiting_bodies_in_500m_cell_on_italian_date"

OLD_RAIN_KEY = "older_rain"
RECENT_RAIN_KEY = "recent_rain"
TARGET_TEMPERATURE_KEY = "target_temperature"
REFERENCE_ALTITUDE_KEY = "reference_altitude"
SQUARE_ALTITUDE_KEY = "square_altitude"
FOREST_SHARE_KEY = "forest_share"

_TEMPERATURE_SEMANTICS = {"temperature_at_reference_altitude"}


@dataclass(frozen=True)
class NumericInput:
    """A numeric value with the source and period that produced it."""

    value: float | None
    unit: str
    source_id: str
    period_start: date
    period_end: date
    completed_day_count: int
    forecast_day_count: int
    quality: str | None = None
    semantic: str | None = None


@dataclass(frozen=True)
class ForecastInputs:
    """Inputs for one assessment date, target date and 500 m square."""

    assessment_date: date
    target_date: date
    old_rain: NumericInput | None
    recent_rain: NumericInput | None
    target_temperature: NumericInput | None
    reference_altitude: NumericInput | None
    square_altitude: NumericInput | None
    forest_share: NumericInput | None


@dataclass(frozen=True)
class ForecastMethodConfig:
    """Frozen parameters for one version of the experimental calculation."""

    version: str = METHOD_VERSION
    old_rain_saturation_mm: float = 60.0
    recent_rain_saturation_mm: float = 30.0
    temperature_optimum_c: float = 13.0
    temperature_width_c: float = 10.0
    temperature_lapse_rate_c_per_m: float = 0.0065
    minimum_forest_share: float = 0.1
    recent_rain_base: float = 0.90
    recent_rain_weight: float = 0.10
    temperature_base: float = 0.75
    temperature_weight: float = 0.25
    forest_base: float = 0.75
    forest_weight: float = 0.25
    minimum_percentage: int = 5
    maximum_percentage: int = 95


METHOD_V1 = ForecastMethodConfig()


@dataclass(frozen=True)
class ForecastFact:
    """One input or derived value used by the experimental calculation."""

    role_key: str
    original_value: float
    unit: str
    source_id: str
    source_ids: tuple[str, ...]
    period_start: date
    period_end: date
    completed_day_count: int
    forecast_day_count: int
    normalized_factor: float | None
    translation_key: str
    quality: str | None = None


@dataclass(frozen=True)
class ForecastResult:
    """The percentage, availability details and facts for one calculation."""

    whole_percentage: int | None
    unavailable_reason: str | None
    missing_inputs: tuple[str, ...]
    method_version: str
    event_key: str
    experimental_unvalidated: bool
    ordered_facts: tuple[ForecastFact, ...]


def _is_date(value: object) -> bool:
    return isinstance(value, date) and not isinstance(value, datetime)


def _validate_date(*, value: object, name: str) -> date:
    if not _is_date(value):
        raise ValueError(f"{name} must be a date")
    return value


def _validate_method(*, method: ForecastMethodConfig) -> None:
    if not isinstance(method, ForecastMethodConfig):
        raise ValueError("method must be a ForecastMethodConfig")
    if method.version != METHOD_VERSION:
        raise ValueError(f"unsupported method version: {method.version}")
    if method != METHOD_V1:
        raise ValueError("porcini-experimental-v1 parameters are frozen")
    numeric_fields = (
        "old_rain_saturation_mm",
        "recent_rain_saturation_mm",
        "temperature_optimum_c",
        "temperature_width_c",
        "temperature_lapse_rate_c_per_m",
        "minimum_forest_share",
        "recent_rain_base",
        "recent_rain_weight",
        "temperature_base",
        "temperature_weight",
        "forest_base",
        "forest_weight",
    )
    for field_name in numeric_fields:
        value = getattr(method, field_name)
        if not isinstance(value, Real) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(f"method {field_name} must be finite")
    if method.old_rain_saturation_mm <= 0 or method.recent_rain_saturation_mm <= 0:
        raise ValueError("rain saturation values must be greater than zero")
    if method.temperature_width_c <= 0 or method.temperature_lapse_rate_c_per_m < 0:
        raise ValueError("temperature width and lapse rate must be valid")
    if not 0 <= method.minimum_forest_share < 1:
        raise ValueError("minimum forest share must be from zero to less than one")
    for base, weight, name in (
        (method.recent_rain_base, method.recent_rain_weight, "recent rain"),
        (method.temperature_base, method.temperature_weight, "temperature"),
        (method.forest_base, method.forest_weight, "forest"),
    ):
        if not 0 <= base <= 1 or not 0 <= weight <= 1 or base + weight > 1:
            raise ValueError(f"{name} multiplier must stay from zero to one")
    if (
        not isinstance(method.minimum_percentage, int)
        or isinstance(method.minimum_percentage, bool)
        or not isinstance(method.maximum_percentage, int)
        or isinstance(method.maximum_percentage, bool)
        or method.minimum_percentage != 5
        or method.maximum_percentage != 95
    ):
        raise ValueError("percentage bounds must be exactly 5 and 95")


def _validate_numeric_input(
    *,
    item: NumericInput | None,
    name: str,
    expected_unit: str,
    expected_start: date,
    expected_end: date,
    expected_completed: int,
    expected_forecast: int,
    allow_negative: bool,
    semantic_values: set[str] | None = None,
) -> None:
    if item is None:
        return
    if not isinstance(item, NumericInput):
        raise ValueError(f"{name} must be a NumericInput")
    if item.unit != expected_unit:
        raise ValueError(f"{name} must use {expected_unit}")
    if not isinstance(item.source_id, str) or not item.source_id:
        raise ValueError(f"{name} source_id must not be empty")
    start = _validate_date(value=item.period_start, name=f"{name} period_start")
    end = _validate_date(value=item.period_end, name=f"{name} period_end")
    if end < start:
        raise ValueError(f"{name} period_end must not precede period_start")
    if not isinstance(item.completed_day_count, int) or isinstance(item.completed_day_count, bool):
        raise ValueError(f"{name} completed_day_count must be an integer")
    if not isinstance(item.forecast_day_count, int) or isinstance(item.forecast_day_count, bool):
        raise ValueError(f"{name} forecast_day_count must be an integer")
    if item.completed_day_count < 0 or item.forecast_day_count < 0:
        raise ValueError(f"{name} day counts must not be negative")
    period_days = (end - start).days + 1
    if item.completed_day_count + item.forecast_day_count != period_days:
        raise ValueError(f"{name} day counts must cover its period")
    if (
        start != expected_start
        or end != expected_end
        or item.completed_day_count != expected_completed
        or item.forecast_day_count != expected_forecast
    ):
        raise ValueError(f"{name} has the wrong period or day composition")
    if item.quality is not None and not isinstance(item.quality, str):
        raise ValueError(f"{name} quality must be text")
    if semantic_values is not None and item.semantic not in semantic_values:
        raise ValueError(f"{name} must be at the Open-Meteo reference altitude")
    if semantic_values is None and item.semantic is not None:
        raise ValueError(f"{name} does not accept a semantic value")
    if item.value is None:
        return
    if not isinstance(item.value, Real) or isinstance(item.value, bool):
        raise ValueError(f"{name} value must be numeric")
    if not math.isfinite(float(item.value)):
        raise ValueError(f"{name} value must be finite")
    if not allow_negative and item.value < 0:
        raise ValueError(f"{name} value must not be negative")


def _clamp(*, value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("calculation factor must be finite")
    return max(0.0, min(1.0, value))


def _make_fact(
    *,
    item: NumericInput,
    role_key: str,
    normalized_factor: float | None,
    translation_key: str,
    original_value: float | None = None,
    source_id: str | None = None,
    source_ids: tuple[str, ...] | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    completed_day_count: int | None = None,
    forecast_day_count: int | None = None,
    quality: str | None = None,
) -> ForecastFact:
    if item.value is None and original_value is None:
        raise ValueError(f"cannot create a fact for missing {role_key}")
    return ForecastFact(
        role_key=role_key,
        original_value=float(item.value if original_value is None else original_value),
        unit=item.unit,
        source_id=source_id or item.source_id,
        source_ids=source_ids or (item.source_id,),
        period_start=period_start or item.period_start,
        period_end=period_end or item.period_end,
        completed_day_count=(
            item.completed_day_count if completed_day_count is None else completed_day_count
        ),
        forecast_day_count=(
            item.forecast_day_count if forecast_day_count is None else forecast_day_count
        ),
        normalized_factor=normalized_factor,
        translation_key=translation_key,
        quality=item.quality if quality is None else quality,
    )


def _facts_and_factors(
    *, inputs: ForecastInputs, method: ForecastMethodConfig
) -> tuple[tuple[ForecastFact, ...], dict[str, float]]:
    old = inputs.old_rain
    recent = inputs.recent_rain
    target_temperature = inputs.target_temperature
    reference_altitude = inputs.reference_altitude
    square_altitude = inputs.square_altitude
    forest = inputs.forest_share
    factors: dict[str, float] = {}
    facts: list[ForecastFact] = []
    if old is not None and old.value is not None:
        factors[OLD_RAIN_KEY] = _clamp(value=float(old.value) / method.old_rain_saturation_mm)
        facts.append(
            _make_fact(
                item=old,
                role_key=OLD_RAIN_KEY,
                normalized_factor=factors[OLD_RAIN_KEY],
                translation_key="forecast.fact.older_rain",
            )
        )
    if recent is not None and recent.value is not None:
        factors[RECENT_RAIN_KEY] = _clamp(
            value=float(recent.value) / method.recent_rain_saturation_mm
        )
        facts.append(
            _make_fact(
                item=recent,
                role_key=RECENT_RAIN_KEY,
                normalized_factor=factors[RECENT_RAIN_KEY],
                translation_key="forecast.fact.recent_rain",
            )
        )
    if target_temperature is not None and target_temperature.value is not None:
        facts.append(
            _make_fact(
                item=target_temperature,
                role_key="target_temperature_at_reference",
                normalized_factor=None,
                translation_key="forecast.fact.target_temperature_at_reference",
            )
        )
    if reference_altitude is not None and reference_altitude.value is not None:
        facts.append(
            _make_fact(
                item=reference_altitude,
                role_key=REFERENCE_ALTITUDE_KEY,
                normalized_factor=None,
                translation_key="forecast.fact.reference_altitude",
            )
        )
    if square_altitude is not None and square_altitude.value is not None:
        facts.append(
            _make_fact(
                item=square_altitude,
                role_key=SQUARE_ALTITUDE_KEY,
                normalized_factor=None,
                translation_key="forecast.fact.square_altitude",
            )
        )
    if (
        target_temperature is not None
        and target_temperature.value is not None
        and reference_altitude is not None
        and reference_altitude.value is not None
        and square_altitude is not None
        and square_altitude.value is not None
    ):
        corrected = float(target_temperature.value) - method.temperature_lapse_rate_c_per_m * (
            float(square_altitude.value) - float(reference_altitude.value)
        )
        if not math.isfinite(corrected):
            raise ValueError("corrected target temperature must be finite")
        temperature_factor = _clamp(
            value=1.0
            - abs(corrected - method.temperature_optimum_c) / method.temperature_width_c
        )
        factors[TARGET_TEMPERATURE_KEY] = temperature_factor
        facts.append(
            _make_fact(
                item=target_temperature,
                role_key="corrected_temperature",
                original_value=corrected,
                source_id="derived:corrected_temperature",
                source_ids=(
                    target_temperature.source_id,
                    reference_altitude.source_id,
                    square_altitude.source_id,
                ),
                period_start=target_temperature.period_start,
                period_end=target_temperature.period_end,
                completed_day_count=target_temperature.completed_day_count,
                forecast_day_count=target_temperature.forecast_day_count,
                quality="derived",
                normalized_factor=temperature_factor,
                translation_key="forecast.fact.corrected_temperature",
            )
        )
    if forest is not None and forest.value is not None:
        factors[FOREST_SHARE_KEY] = _clamp(
            value=(float(forest.value) - method.minimum_forest_share)
            / (1.0 - method.minimum_forest_share)
        )
        facts.append(
            _make_fact(
                item=forest,
                role_key=FOREST_SHARE_KEY,
                normalized_factor=factors[FOREST_SHARE_KEY],
                translation_key="forecast.fact.forest_share",
            )
        )
    return tuple(facts), factors


def calculate_forecast(
    *, inputs: ForecastInputs, method: ForecastMethodConfig = METHOD_V1
) -> ForecastResult:
    """Return an experimental whole percentage for one 500 m square."""
    _validate_method(method=method)
    assessment_date = _validate_date(value=inputs.assessment_date, name="assessment_date")
    target_date = _validate_date(value=inputs.target_date, name="target_date")
    if target_date < assessment_date:
        raise ValueError("target_date must not precede assessment_date")
    days_ahead = (target_date - assessment_date).days
    if days_ahead > 7:
        raise ValueError("target_date must be at most seven days after assessment_date")

    _validate_numeric_input(
        item=inputs.old_rain,
        name=OLD_RAIN_KEY,
        expected_unit="mm",
        expected_start=target_date - timedelta(days=21),
        expected_end=target_date - timedelta(days=8),
        expected_completed=14,
        expected_forecast=0,
        allow_negative=False,
    )
    _validate_numeric_input(
        item=inputs.recent_rain,
        name=RECENT_RAIN_KEY,
        expected_unit="mm",
        expected_start=target_date - timedelta(days=7),
        expected_end=target_date - timedelta(days=1),
        expected_completed=7 - days_ahead,
        expected_forecast=days_ahead,
        allow_negative=False,
    )
    _validate_numeric_input(
        item=inputs.target_temperature,
        name=TARGET_TEMPERATURE_KEY,
        expected_unit="deg_c",
        expected_start=target_date,
        expected_end=target_date,
        expected_completed=0,
        expected_forecast=1,
        allow_negative=True,
        semantic_values=_TEMPERATURE_SEMANTICS,
    )
    for name, item in (
        (REFERENCE_ALTITUDE_KEY, inputs.reference_altitude),
        (SQUARE_ALTITUDE_KEY, inputs.square_altitude),
    ):
        _validate_numeric_input(
            item=item,
            name=name,
            expected_unit="m",
            expected_start=assessment_date,
            expected_end=assessment_date,
            expected_completed=1,
            expected_forecast=0,
            allow_negative=True,
        )
    _validate_numeric_input(
        item=inputs.forest_share,
        name=FOREST_SHARE_KEY,
        expected_unit="fraction",
        expected_start=assessment_date,
        expected_end=assessment_date,
        expected_completed=1,
        expected_forecast=0,
        allow_negative=True,
    )
    if inputs.forest_share is not None and inputs.forest_share.value is not None:
        if not 0 <= inputs.forest_share.value <= 1:
            raise ValueError("forest_share value must be from zero to one")

    facts, factors = _facts_and_factors(inputs=inputs, method=method)
    missing = tuple(
        name
        for name, item in (
            (OLD_RAIN_KEY, inputs.old_rain),
            (RECENT_RAIN_KEY, inputs.recent_rain),
            (TARGET_TEMPERATURE_KEY, inputs.target_temperature),
            (REFERENCE_ALTITUDE_KEY, inputs.reference_altitude),
            (SQUARE_ALTITUDE_KEY, inputs.square_altitude),
            (FOREST_SHARE_KEY, inputs.forest_share),
        )
        if item is None or item.value is None
    )
    forest_value = None if inputs.forest_share is None else inputs.forest_share.value
    if forest_value is None:
        reason = "missing_forest_data"
    elif forest_value < method.minimum_forest_share:
        reason = "forest_below_minimum"
    elif missing:
        reason = missing[0]
    else:
        reason = None
    if reason is not None:
        return ForecastResult(
            whole_percentage=None,
            unavailable_reason=reason,
            missing_inputs=missing,
            method_version=method.version,
            event_key=EVENT_KEY,
            experimental_unvalidated=True,
            ordered_facts=facts,
        )

    score = (
        factors[OLD_RAIN_KEY]
        * (method.recent_rain_base + method.recent_rain_weight * factors[RECENT_RAIN_KEY])
        * (method.temperature_base + method.temperature_weight * factors[TARGET_TEMPERATURE_KEY])
        * (method.forest_base + method.forest_weight * factors[FOREST_SHARE_KEY])
    )
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("calculation score must stay from zero to one")
    raw_percentage = Decimal("5") + Decimal("90") * Decimal(str(score))
    whole_percentage = int(raw_percentage.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if not method.minimum_percentage <= whole_percentage <= method.maximum_percentage:
        raise ValueError("calculation output is outside configured bounds")
    return ForecastResult(
        whole_percentage=whole_percentage,
        unavailable_reason=None,
        missing_inputs=(),
        method_version=method.version,
        event_key=EVENT_KEY,
        experimental_unvalidated=True,
        ordered_facts=facts,
    )
