"""Focused checks for the experimental porcini forecast method."""

from dataclasses import replace
from datetime import date, timedelta
import math

import pytest

from micometeo.forecast_method import (
    EVENT_KEY,
    METHOD_V1,
    ForecastInputs,
    NumericInput,
    calculate_forecast,
)


ASSESSMENT = date(2026, 6, 15)


def make_input(
    *,
    role: str,
    value: float | None,
    assessment: date = ASSESSMENT,
    target: date | None = None,
    unit: str | None = None,
    source_id: str | None = None,
    semantic: str | None = None,
) -> NumericInput:
    target_date = target or assessment
    days_ahead = (target_date - assessment).days
    if role == "old_rain":
        period_start = target_date - timedelta(days=21)
        period_end = target_date - timedelta(days=8)
        completed = 14
        forecast = 0
        default_unit = "mm"
    elif role == "recent_rain":
        period_start = target_date - timedelta(days=7)
        period_end = target_date - timedelta(days=1)
        completed = 7 - days_ahead
        forecast = days_ahead
        default_unit = "mm"
    elif role == "target_temperature":
        period_start = target_date
        period_end = target_date
        completed = 0
        forecast = 1
        default_unit = "deg_c"
    else:
        period_start = assessment
        period_end = assessment
        completed = 1
        forecast = 0
        default_unit = "m" if role in {"reference_altitude", "square_altitude"} else "fraction"
    if role == "target_temperature" and semantic is None:
        semantic = "temperature_at_reference_altitude"
    return NumericInput(
        value=value,
        unit=unit or default_unit,
        source_id=source_id or f"test:{role}",
        period_start=period_start,
        period_end=period_end,
        completed_day_count=completed,
        forecast_day_count=forecast,
        semantic=semantic,
    )


def make_inputs(
    *,
    assessment: date = ASSESSMENT,
    days_ahead: int = 0,
    old_rain: float | None = 60.0,
    recent_rain: float | None = 30.0,
    target_temperature: float | None = 16.25,
    reference_altitude: float | None = 500.0,
    square_altitude: float | None = 1000.0,
    forest_share: float | None = 1.0,
) -> ForecastInputs:
    target = assessment + timedelta(days=days_ahead)
    return ForecastInputs(
        assessment_date=assessment,
        target_date=target,
        old_rain=None
        if old_rain is None
        else make_input(role="old_rain", value=old_rain, assessment=assessment, target=target),
        recent_rain=None
        if recent_rain is None
        else make_input(role="recent_rain", value=recent_rain, assessment=assessment, target=target),
        target_temperature=None
        if target_temperature is None
        else make_input(
            role="target_temperature",
            value=target_temperature,
            assessment=assessment,
            target=target,
        ),
        reference_altitude=None
        if reference_altitude is None
        else make_input(
            role="reference_altitude",
            value=reference_altitude,
            assessment=assessment,
            target=target,
        ),
        square_altitude=None
        if square_altitude is None
        else make_input(
            role="square_altitude",
            value=square_altitude,
            assessment=assessment,
            target=target,
        ),
        forest_share=None
        if forest_share is None
        else make_input(
            role="forest_share",
            value=forest_share,
            assessment=assessment,
            target=target,
        ),
    )


def test_fixed_examples_return_documented_percentages_and_facts() -> None:
    ideal = calculate_forecast(inputs=make_inputs())
    dry = calculate_forecast(inputs=make_inputs(old_rain=0.0))
    low_forest = calculate_forecast(inputs=make_inputs(forest_share=0.1))

    assert ideal.whole_percentage == 95
    assert dry.whole_percentage == 5
    assert low_forest.whole_percentage == 73
    assert ideal.unavailable_reason is None
    assert ideal.experimental_unvalidated is True
    assert ideal.method_version == METHOD_V1.version
    assert ideal.event_key == EVENT_KEY
    assert tuple(fact.role_key for fact in ideal.ordered_facts) == (
        "older_rain",
        "recent_rain",
        "target_temperature_at_reference",
        "reference_altitude",
        "square_altitude",
        "corrected_temperature",
        "forest_share",
    )
    assert ideal.ordered_facts[0].normalized_factor == 1.0
    assert ideal.ordered_facts[5].original_value == 13.0
    assert ideal.ordered_facts[5].source_ids == (
        "test:target_temperature",
        "test:reference_altitude",
        "test:square_altitude",
    )
    assert ideal == calculate_forecast(inputs=make_inputs())


def test_missing_required_input_is_unavailable_and_keeps_known_facts() -> None:
    result = calculate_forecast(inputs=make_inputs(old_rain=None))

    assert result.whole_percentage is None
    assert result.unavailable_reason == "older_rain"
    assert result.missing_inputs == ("older_rain",)
    assert "older_rain" not in {fact.role_key for fact in result.ordered_facts}
    assert "forest_share" in {fact.role_key for fact in result.ordered_facts}


def test_missing_forest_and_low_forest_are_distinct() -> None:
    missing = calculate_forecast(inputs=make_inputs(forest_share=None))
    low = calculate_forecast(inputs=make_inputs(forest_share=0.099999))

    assert missing.unavailable_reason == "missing_forest_data"
    assert missing.missing_inputs == ("forest_share",)
    assert low.unavailable_reason == "forest_below_minimum"
    assert low.missing_inputs == ()


@pytest.mark.parametrize(
    ("role", "unit"),
    [
        ("old_rain", "deg_c"),
        ("recent_rain", "m"),
        ("target_temperature", "mm"),
        ("reference_altitude", "fraction"),
        ("square_altitude", "mm"),
        ("forest_share", "mm"),
    ],
)
def test_wrong_units_raise_value_error(role: str, unit: str) -> None:
    inputs = make_inputs()
    replacement = make_input(role=role, value=1.0, unit=unit)
    inputs = replace(inputs, **{role: replacement})

    with pytest.raises(ValueError, match="must use"):
        calculate_forecast(inputs=inputs)


def test_nonfinite_negative_and_out_of_range_values_raise() -> None:
    with pytest.raises(ValueError, match="finite"):
        calculate_forecast(inputs=make_inputs(old_rain=math.inf))
    with pytest.raises(ValueError, match="must not be negative"):
        calculate_forecast(inputs=make_inputs(recent_rain=-1.0))
    with pytest.raises(ValueError, match="from zero to one"):
        calculate_forecast(inputs=make_inputs(forest_share=1.1))


def test_future_target_requires_exact_period_composition() -> None:
    assessment = date(2028, 2, 29)
    result = calculate_forecast(inputs=make_inputs(assessment=assessment, days_ahead=7))

    recent = next(fact for fact in result.ordered_facts if fact.role_key == "recent_rain")
    target = next(
        fact
        for fact in result.ordered_facts
        if fact.role_key == "target_temperature_at_reference"
    )
    assert result.whole_percentage == 95
    assert recent.period_start == date(2028, 2, 29)
    assert recent.period_end == date(2028, 3, 6)
    assert recent.completed_day_count == 0
    assert recent.forecast_day_count == 7
    assert target.period_start == date(2028, 3, 7)
    assert target.completed_day_count == 0
    assert target.forecast_day_count == 1


@pytest.mark.parametrize("days_ahead", range(8))
def test_every_supported_days_ahead_value_has_matching_recent_composition(
    days_ahead: int,
) -> None:
    result = calculate_forecast(inputs=make_inputs(days_ahead=days_ahead))

    recent = next(fact for fact in result.ordered_facts if fact.role_key == "recent_rain")
    assert recent.completed_day_count == 7 - days_ahead
    assert recent.forecast_day_count == days_ahead


def test_target_temperature_is_adjusted_once_from_reference_to_square() -> None:
    result = calculate_forecast(inputs=make_inputs(target_temperature=16.25))
    corrected = next(
        fact for fact in result.ordered_facts if fact.role_key == "corrected_temperature"
    )

    assert corrected.original_value == pytest.approx(13.0)
    assert corrected.normalized_factor == 1.0

    adjusted = make_input(
        role="target_temperature",
        value=13.0,
        semantic="temperature_at_square_altitude",
    )
    with pytest.raises(ValueError, match="reference altitude"):
        calculate_forecast(inputs=replace(make_inputs(), target_temperature=adjusted))

    missing_semantic = replace(
        make_inputs().target_temperature,
        value=None,
        semantic=None,
    )
    with pytest.raises(ValueError, match="reference altitude"):
        calculate_forecast(inputs=replace(make_inputs(), target_temperature=missing_semantic))


def test_calendar_boundaries_and_altitudes_have_no_hard_exclusions() -> None:
    june = calculate_forecast(inputs=make_inputs(assessment=date(2026, 6, 15)))
    november = calculate_forecast(inputs=make_inputs(assessment=date(2026, 11, 15)))
    high = calculate_forecast(inputs=make_inputs(square_altitude=2500.0))
    low = calculate_forecast(inputs=make_inputs(square_altitude=-20.0))

    assert june.whole_percentage == november.whole_percentage == 95
    assert high.whole_percentage is not None
    assert low.whole_percentage is not None


def test_round_half_up_and_invalid_method_configuration_are_explicit() -> None:
    low_forest = calculate_forecast(inputs=make_inputs(forest_share=0.1))
    assert low_forest.whole_percentage == 73

    invalid_frozen_value = replace(METHOD_V1, old_rain_saturation_mm=120.0)
    with pytest.raises(ValueError, match="parameters are frozen"):
        calculate_forecast(inputs=make_inputs(), method=invalid_frozen_value)
    unsupported = replace(METHOD_V1, version="porcini-experimental-v2")
    with pytest.raises(ValueError, match="unsupported method version"):
        calculate_forecast(inputs=make_inputs(), method=unsupported)


def test_documented_future_example_keeps_values_and_period_facts() -> None:
    result = calculate_forecast(
        inputs=make_inputs(
            assessment=date(2026, 6, 15),
            days_ahead=3,
            old_rain=48.0,
            recent_rain=15.0,
            target_temperature=15.0,
            reference_altitude=500.0,
            square_altitude=500.0,
            forest_share=0.75,
        )
    )

    assert result.whole_percentage == 65
    old_rain = next(fact for fact in result.ordered_facts if fact.role_key == "older_rain")
    recent_rain = next(fact for fact in result.ordered_facts if fact.role_key == "recent_rain")
    target_temperature = next(
        fact
        for fact in result.ordered_facts
        if fact.role_key == "target_temperature_at_reference"
    )
    assert old_rain.original_value == 48.0
    assert old_rain.period_start == date(2026, 5, 28)
    assert old_rain.period_end == date(2026, 6, 10)
    assert old_rain.completed_day_count == 14
    assert old_rain.forecast_day_count == 0
    assert recent_rain.original_value == 15.0
    assert recent_rain.period_start == date(2026, 6, 11)
    assert recent_rain.period_end == date(2026, 6, 17)
    assert recent_rain.completed_day_count == 4
    assert recent_rain.forecast_day_count == 3
    assert target_temperature.period_start == date(2026, 6, 18)
    assert target_temperature.period_end == date(2026, 6, 18)
    assert target_temperature.completed_day_count == 0
    assert target_temperature.forecast_day_count == 1


def test_changed_input_changes_its_fact_and_normalized_factor() -> None:
    result = calculate_forecast(inputs=make_inputs(old_rain=30.0))
    fact = next(fact for fact in result.ordered_facts if fact.role_key == "older_rain")

    assert result.whole_percentage == 50
    assert fact.original_value == 30.0
    assert fact.normalized_factor == 0.5
