"""Focused checks for daily weather aggregation and immutable summaries."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from micometeo.weather.features import day_start, hours_in_local_day
from weather_summaries.aggregation import aggregate_response
from weather_summaries.contracts import (
    HourlySeries,
    NormalizedLocationResponse,
    NormalizedProviderResponse,
)
from weather_summaries.inputs import canonical_forecast_inputs


ASSESSMENT = date(2026, 10, 11)


@pytest.mark.django_db(transaction=True)
def test_thirty_day_snapshot_coexists_with_unchanged_legacy_snapshot() -> None:
    from weather_summaries.models import WeatherSnapshot
    from weather_summaries.services import build_weather_snapshot, store_weather_daily_rows, store_weather_response

    legacy = store_weather_response(response_for(
        start=ASSESSMENT - timedelta(days=21), end=ASSESSMENT + timedelta(days=7), rain=0.0,
    ), ASSESSMENT)
    original_ids = tuple(legacy.snapshot.days.order_by("date").values_list("daily_id", flat=True))
    start = ASSESSMENT - timedelta(days=30)
    end = ASSESSMENT + timedelta(days=7)
    rows = store_weather_daily_rows(response_for(start=start, end=end, rain=2.0), start=start, end=end)
    current = build_weather_snapshot(
        cell_key="cell-1", assessment_date=ASSESSMENT, reference_elevation_m=420.0,
        new_daily_row_ids=[row.id for row in rows], pipeline_version=2,
    )
    assert current.snapshot is not None
    assert current.snapshot.id != legacy.snapshot.id
    assert current.snapshot.days.count() == 38
    assert WeatherSnapshot.objects.filter(cell_key="cell-1", assessment_date=ASSESSMENT).count() == 2
    legacy.snapshot.refresh_from_db()
    assert legacy.snapshot.pipeline_version == 1
    assert tuple(legacy.snapshot.days.order_by("date").values_list("daily_id", flat=True)) == original_ids
    assert legacy.snapshot.summaries.get(days_ahead=0).recent_rain_mm == 0.0
    assert current.snapshot.summaries.get(days_ahead=0).recent_rain_mm == 336.0


def response_for(
    *,
    start: date,
    end: date,
    rain: float = 1.0,
    temperature: float = 10.0,
    optional: bool = True,
    attempt_id=None,
) -> NormalizedProviderResponse:
    first = int(day_start(day=start).timestamp())
    closing = int(day_start(day=end + timedelta(days=1)).timestamp())
    timestamps = tuple(range(first, closing + 1, 3600))
    values = {
        "precipitation": (rain,) * len(timestamps),
        "temperature": (temperature,) * len(timestamps),
    }
    units = {"precipitation": "mm", "temperature": "deg_c"}
    if optional:
        values.update(
            {
                "et0": (0.1,) * len(timestamps),
                "soil_temperature": (temperature - 1,) * len(timestamps),
                "soil_moisture": (0.2,) * len(timestamps),
            }
        )
        units.update({"et0": "mm", "soil_temperature": "deg_c", "soil_moisture": "m3_m3"})
    return NormalizedProviderResponse(
        request_id="request-1",
        attempt_id=attempt_id or uuid4(),
        retrieved_at=datetime(2026, 10, 12, 10, tzinfo=UTC),
        provider_endpoint="https://example.test/forecast",
        model="test-model",
        source_id="provider:test-model",
        first_timestamp_utc=first,
        closing_timestamp_utc=closing,
        hourly_timestamps=timestamps,
        hourly_series=tuple(
            HourlySeries(name=name, unit=units[name], values=values[name])
            for name in values
        ),
        location=NormalizedLocationResponse(
            cell_key="cell-1",
            requested_latitude=43.77,
            requested_longitude=11.25,
            returned_latitude=43.77,
            returned_longitude=11.25,
            elevation_m=420.0,
        ),
        requested_start=start,
        requested_end=end,
    )


def response_with_series(
    response: NormalizedProviderResponse,
    *,
    values_by_name: dict[str, tuple[float | None, ...]],
    location: NormalizedLocationResponse | None = None,
) -> NormalizedProviderResponse:
    """Return a response with selected canonical arrays replaced."""
    series = tuple(
        replace(item, values=values_by_name.get(item.name, item.values))
        for item in response.hourly_series
    )
    return replace(response, hourly_series=series, location=location or response.location)


def test_spring_and_autumn_clock_days_have_expected_hours() -> None:
    assert hours_in_local_day(day=date(2026, 3, 29)) == 23
    assert hours_in_local_day(day=date(2026, 10, 25)) == 25

    spring = aggregate_response(response=response_for(start=date(2026, 3, 29), end=date(2026, 3, 29)))
    autumn = aggregate_response(response=response_for(start=date(2026, 10, 25), end=date(2026, 10, 25)))

    assert spring[0].rain_mm == 23.0
    assert spring[0].mean_temperature_c == 10.0
    assert autumn[0].rain_mm == 25.0
    assert autumn[0].mean_temperature_c == 10.0


def test_leap_day_and_year_boundary_dates_are_kept_in_order() -> None:
    rows = aggregate_response(
        response=response_for(start=date(2028, 2, 28), end=date(2028, 3, 1)),
    )

    assert [row.date for row in rows] == [
        date(2028, 2, 28),
        date(2028, 2, 29),
        date(2028, 3, 1),
    ]
    year_rows = aggregate_response(
        response=response_for(start=date(2027, 12, 31), end=date(2028, 1, 1)),
    )
    assert [row.date for row in year_rows] == [date(2027, 12, 31), date(2028, 1, 1)]


def test_amounts_use_closing_midnight_and_instant_values_exclude_it() -> None:
    response = response_for(start=date(2026, 10, 24), end=date(2026, 10, 24))
    values = {
        series.name: list(series.values)
        for series in response.hourly_series
    }
    values["precipitation"][-1] = 50.0
    values["temperature"][-1] = 100.0
    updated = NormalizedProviderResponse(
        request_id=response.request_id,
        attempt_id=response.attempt_id,
        retrieved_at=response.retrieved_at,
        provider_endpoint=response.provider_endpoint,
        model=response.model,
        source_id=response.source_id,
        first_timestamp_utc=response.first_timestamp_utc,
        closing_timestamp_utc=response.closing_timestamp_utc,
        hourly_timestamps=response.hourly_timestamps,
        hourly_series=tuple(
            HourlySeries(name=name, unit=next(item.unit for item in response.hourly_series if item.name == name), values=tuple(series))
            for name, series in values.items()
        ),
        location=response.location,
        requested_start=response.requested_start,
        requested_end=response.requested_end,
    )

    row = aggregate_response(response=updated)[0]

    assert row.rain_mm == 73.0
    assert row.mean_temperature_c == 10.0
    assert row.min_temperature_c == 10.0


def test_missing_required_hour_is_checked_gap_but_absent_optional_is_local() -> None:
    response = response_for(start=ASSESSMENT, end=ASSESSMENT, optional=False)
    timestamps = response.hourly_timestamps[:-1]
    values = {
        series.name: series.values[:-1]
        for series in response.hourly_series
    }
    missing = NormalizedProviderResponse(
        request_id=response.request_id,
        attempt_id=response.attempt_id,
        retrieved_at=response.retrieved_at,
        provider_endpoint=response.provider_endpoint,
        model=response.model,
        source_id=response.source_id,
        first_timestamp_utc=timestamps[0],
        closing_timestamp_utc=timestamps[-1],
        hourly_timestamps=timestamps,
        hourly_series=tuple(
            HourlySeries(name=series.name, unit=series.unit, values=values[series.name])
            for series in response.hourly_series
        ),
        location=response.location,
        requested_start=ASSESSMENT,
        requested_end=ASSESSMENT,
    )

    row = aggregate_response(response=missing)[0]

    assert row.status == "checked_known_missing"
    assert row.rain_mm is None
    assert row.mean_temperature_c == 10.0
    assert row.et0_mm is None
    assert row.metadata["variables"]["et0"]["reason"] == "optional_variable_absent"


def test_missing_required_variable_is_checked_gap_without_rejecting_successful_response() -> None:
    response = response_for(start=ASSESSMENT, end=ASSESSMENT)
    temperature = next(series for series in response.hourly_series if series.name == "temperature")
    missing_rain = NormalizedProviderResponse(
        request_id=response.request_id,
        attempt_id=response.attempt_id,
        retrieved_at=response.retrieved_at,
        provider_endpoint=response.provider_endpoint,
        model=response.model,
        source_id=response.source_id,
        first_timestamp_utc=response.first_timestamp_utc,
        closing_timestamp_utc=response.closing_timestamp_utc,
        hourly_timestamps=response.hourly_timestamps,
        hourly_series=(temperature,),
        location=response.location,
        requested_start=ASSESSMENT,
        requested_end=ASSESSMENT,
    )

    row = aggregate_response(response=missing_rain)[0]

    assert row.status == "checked_known_missing"
    assert row.rain_mm is None
    assert row.mean_temperature_c == 10.0
    assert row.metadata["variables"]["precipitation"]["reason"] == "required_variable_absent"


def test_zero_rain_is_complete_and_later_values_outside_requested_range_are_ignored() -> None:
    response = response_for(start=ASSESSMENT - timedelta(days=1), end=ASSESSMENT, rain=0.0)
    row = aggregate_response(
        response=response,
        start=ASSESSMENT,
        end=ASSESSMENT,
    )[0]

    assert row.rain_mm == 0.0
    assert row.status == "complete"


def test_normalization_rejects_duplicate_unordered_nonhourly_and_refused_answers() -> None:
    response = response_for(start=ASSESSMENT, end=ASSESSMENT)

    with pytest.raises(ValueError, match="ordered and unique"):
        NormalizedProviderResponse(
            request_id=response.request_id,
            attempt_id=response.attempt_id,
            retrieved_at=response.retrieved_at,
            provider_endpoint=response.provider_endpoint,
            model=response.model,
            source_id=response.source_id,
            first_timestamp_utc=response.hourly_timestamps[0],
            closing_timestamp_utc=response.hourly_timestamps[-1],
            hourly_timestamps=(response.hourly_timestamps[1], response.hourly_timestamps[0]),
            hourly_series=(),
            location=response.location,
        )

    with pytest.raises(ValueError, match="hour boundaries"):
        NormalizedProviderResponse(
            request_id=response.request_id,
            attempt_id=response.attempt_id,
            retrieved_at=response.retrieved_at,
            provider_endpoint=response.provider_endpoint,
            model=response.model,
            source_id=response.source_id,
            first_timestamp_utc=1,
            closing_timestamp_utc=1,
            hourly_timestamps=(1,),
            hourly_series=(),
            location=response.location,
        )

    with pytest.raises(ValueError, match="only successful"):
        NormalizedProviderResponse(
            request_id=response.request_id,
            attempt_id=response.attempt_id,
            retrieved_at=response.retrieved_at,
            provider_endpoint=response.provider_endpoint,
            model=response.model,
            source_id=response.source_id,
            first_timestamp_utc=response.first_timestamp_utc,
            closing_timestamp_utc=response.closing_timestamp_utc,
            hourly_timestamps=response.hourly_timestamps,
            hourly_series=response.hourly_series,
            location=response.location,
            response_status="refused",
        )


@pytest.mark.django_db(transaction=True)
def test_full_response_creates_one_snapshot_and_eight_summaries_atomically() -> None:
    from weather_summaries.services import store_weather_response

    response = response_for(
        start=ASSESSMENT - timedelta(days=21),
        end=ASSESSMENT + timedelta(days=7),
    )

    result = store_weather_response(response, ASSESSMENT)

    assert result.snapshot is not None
    assert len(result.daily) == 29
    assert len(result.summaries) == 8
    assert result.summaries[0].days_ahead == 0
    assert result.summaries[-1].days_ahead == 7
    assert result.summaries[0].old_rain_mm == 336.0
    assert result.summaries[-1].recent_rain_mm == 168.0
    assert result.summaries[-1].metadata["old_rain"]["period_start"] == "2026-09-27"
    assert result.summaries[-1].metadata["old_rain"]["period_end"] == "2026-10-10"
    assert result.summaries[-1].metadata["recent_rain"]["completed_day_count"] == 0
    assert result.summaries[-1].metadata["recent_rain"]["forecast_day_count"] == 7
    assert result.snapshot.source_ids == ["provider:test-model"]
    assert result.snapshot.latest_retrieval.isoformat().startswith("2026-10-12T10:00:00")
    assert len(result.snapshot.days.all()) == 29

    for days_ahead, summary in enumerate(result.summaries):
        assert summary.days_ahead == days_ahead
        assert summary.visitor_rain_7_mm == 168.0
        assert summary.visitor_rain_14_mm == 336.0
        assert summary.visitor_rain_21_mm == 504.0
        assert summary.old_rain_mm == 336.0
        assert summary.recent_rain_mm == 168.0
        assert summary.target_rain_mm == 24.0
        assert summary.target_mean_temperature_c == 10.0
        assert summary.metadata["old_rain"]["completed_day_count"] == 14
        assert summary.metadata["old_rain"]["forecast_day_count"] == 0
        assert summary.metadata["recent_rain"]["completed_day_count"] == 7 - days_ahead
        assert summary.metadata["recent_rain"]["forecast_day_count"] == days_ahead
        assert summary.metadata["target"]["completed_day_count"] == 0
        assert summary.metadata["target"]["forecast_day_count"] == 1

    inputs = canonical_forecast_inputs(result.summaries[-1])
    assert inputs.assessment_date == ASSESSMENT
    assert inputs.target_date == ASSESSMENT + timedelta(days=7)

    repeated = store_weather_response(response, ASSESSMENT)

    assert repeated.snapshot == result.snapshot
    assert repeated.summaries == result.summaries


@pytest.mark.django_db(transaction=True)
def test_conflicting_attempt_cannot_rewrite_protected_daily_cache() -> None:
    from weather_summaries.services import WeatherDailyConflictError, store_weather_response

    response = response_for(
        start=ASSESSMENT - timedelta(days=21),
        end=ASSESSMENT + timedelta(days=7),
    )
    store_weather_response(response, ASSESSMENT)
    conflicting = response_for(
        start=ASSESSMENT - timedelta(days=21),
        end=ASSESSMENT + timedelta(days=7),
        rain=2.0,
        attempt_id=response.attempt_id,
    )

    with pytest.raises(WeatherDailyConflictError):
        store_weather_response(conflicting, ASSESSMENT)


@pytest.mark.django_db(transaction=True)
def test_new_attempt_uses_exact_previous_snapshot_for_older_dates() -> None:
    from weather_summaries.services import store_weather_response

    first = store_weather_response(
        response_for(
            start=ASSESSMENT - timedelta(days=21),
            end=ASSESSMENT + timedelta(days=7),
        ),
        ASSESSMENT,
    )
    next_assessment = ASSESSMENT + timedelta(days=1)
    next_response = response_for(
        start=next_assessment - timedelta(days=1),
        end=next_assessment + timedelta(days=7),
        rain=2.0,
    )
    second = store_weather_response(
        next_response,
        next_assessment,
        previous_snapshot=first.snapshot,
    )

    assert second.snapshot is not None
    assert second.snapshot != first.snapshot
    assert len(second.snapshot.days.all()) == 29
    assert second.snapshot.days.filter(date=next_assessment + timedelta(days=7)).exists()
    assert second.snapshot.days.filter(date=ASSESSMENT - timedelta(days=20)).exists()
    assert first.snapshot.days.get(date=ASSESSMENT).daily.rain_mm == 24.0
    assert second.snapshot.days.get(date=next_assessment).daily.rain_mm == 48.0


@pytest.mark.django_db(transaction=True)
def test_micometeo_issue45r_previous_forecast_requires_refetch() -> None:
    from weather_summaries.services import reusable_previous_daily_rows, store_weather_response

    first = store_weather_response(
        response_for(
            start=ASSESSMENT - timedelta(days=21),
            end=ASSESSMENT + timedelta(days=7),
            rain=1.0,
        ),
        ASSESSMENT,
    )
    next_assessment = ASSESSMENT + timedelta(days=1)

    reusable = reusable_previous_daily_rows(
        previous_snapshot=first.snapshot,
        assessment_date=next_assessment,
        cell_key="cell-1",
        reference_elevation_m=420.0,
    )

    assert ASSESSMENT in first.snapshot.days.values_list("date", flat=True)
    assert next_assessment not in reusable

    missing_refetch = store_weather_response(
        response_for(
            start=next_assessment + timedelta(days=7),
            end=next_assessment + timedelta(days=7),
            rain=2.0,
        ),
        next_assessment,
        previous_snapshot=first.snapshot,
    )

    assert missing_refetch.snapshot is None

    refreshed = store_weather_response(
        response_for(
            start=next_assessment - timedelta(days=1),
            end=next_assessment + timedelta(days=7),
            rain=2.0,
        ),
        next_assessment,
        previous_snapshot=first.snapshot,
    )

    assert refreshed.snapshot is not None
    assert first.snapshot.days.get(date=next_assessment).daily.rain_mm == 24.0
    assert refreshed.snapshot.days.get(date=next_assessment).daily.rain_mm == 48.0


@pytest.mark.django_db(transaction=True)
def test_multipart_rows_build_snapshot_from_two_attempts_and_exact_previous_rows() -> None:
    from weather_summaries.services import (
        build_weather_snapshot,
        store_weather_daily_rows,
        store_weather_response,
    )

    first = store_weather_response(
        response_for(
            start=ASSESSMENT - timedelta(days=21),
            end=ASSESSMENT + timedelta(days=7),
            rain=1.0,
        ),
        ASSESSMENT,
    )
    next_assessment = ASSESSMENT + timedelta(days=1)
    first_chunk = replace(
        response_for(start=ASSESSMENT, end=ASSESSMENT + timedelta(days=3), rain=2.0),
        request_id="request-chunk-a",
        source_id="provider:chunk-a",
        retrieved_at=datetime(2026, 10, 12, 11, tzinfo=UTC),
    )
    second_chunk = replace(
        response_for(
            start=ASSESSMENT + timedelta(days=4),
            end=next_assessment + timedelta(days=7),
            rain=3.0,
        ),
        request_id="request-chunk-b",
        source_id="provider:chunk-b",
        retrieved_at=datetime(2026, 10, 12, 12, tzinfo=UTC),
    )

    first_rows = store_weather_daily_rows(
        first_chunk,
        start=ASSESSMENT,
        end=ASSESSMENT + timedelta(days=3),
    )
    second_rows = store_weather_daily_rows(
        second_chunk,
        start=ASSESSMENT + timedelta(days=4),
        end=next_assessment + timedelta(days=7),
    )
    result = build_weather_snapshot(
        cell_key="cell-1",
        assessment_date=next_assessment,
        reference_elevation_m=420.0,
        new_daily_row_ids=tuple(row.id for row in first_rows + second_rows),
        previous_snapshot=first.snapshot,
    )

    assert result.snapshot is not None
    assert result.snapshot.source_ids == [
        "provider:test-model",
        "provider:chunk-a",
        "provider:chunk-b",
    ]
    assert result.snapshot.source_attempt_ids == [
        str(first.snapshot.days.first().daily.attempt_id),
        str(first_rows[0].attempt_id),
        str(second_rows[0].attempt_id),
    ]
    assert result.snapshot.latest_retrieval == second_chunk.retrieved_at
    reused_day = ASSESSMENT - timedelta(days=20)
    assert result.snapshot.days.get(date=reused_day).daily.id == first.snapshot.days.get(
        date=reused_day
    ).daily.id
    assert result.snapshot.days.get(date=next_assessment).daily.rain_mm == 48.0
    assert result.snapshot.days.get(date=next_assessment + timedelta(days=7)).daily.rain_mm == 72.0

    inputs = canonical_forecast_inputs(result.summaries[-1])
    assert inputs.assessment_date == next_assessment
    assert inputs.old_rain.source_id != "provider:test-model"
    assert result.summaries[-1].metadata["old_rain"]["source_ids"] == [
        "provider:test-model",
        "provider:chunk-a",
    ]
    assert result.summaries[-1].metadata["target"]["source_ids"] == [
        "provider:chunk-b"
    ]


@pytest.mark.django_db(transaction=True)
def test_multipart_snapshot_stays_unpublished_until_all_dates_are_supplied() -> None:
    from weather_summaries.services import build_weather_snapshot, store_weather_daily_rows

    next_assessment = ASSESSMENT + timedelta(days=1)
    response = response_for(start=ASSESSMENT, end=next_assessment + timedelta(days=7))
    rows = store_weather_daily_rows(
        response,
        start=ASSESSMENT,
        end=next_assessment + timedelta(days=7),
    )

    result = build_weather_snapshot(
        cell_key="cell-1",
        assessment_date=next_assessment,
        reference_elevation_m=420.0,
        new_daily_row_ids=[row.id for row in rows],
    )

    assert result.snapshot is None
    assert result.summaries == ()


@pytest.mark.django_db(transaction=True)
def test_build_snapshot_rejects_foreign_rows_and_conflicting_dates() -> None:
    from weather_summaries.services import (
        WeatherDailyConflictError,
        build_weather_snapshot,
        store_weather_daily_rows,
    )

    first = store_weather_daily_rows(
        response_for(start=ASSESSMENT, end=ASSESSMENT + timedelta(days=1)),
        start=ASSESSMENT,
        end=ASSESSMENT + timedelta(days=1),
    )
    overlapping_response = replace(
        response_for(start=ASSESSMENT + timedelta(days=1), end=ASSESSMENT + timedelta(days=2)),
        request_id="request-overlap",
    )
    overlapping = store_weather_daily_rows(
        overlapping_response,
        start=ASSESSMENT + timedelta(days=1),
        end=ASSESSMENT + timedelta(days=2),
    )

    with pytest.raises(WeatherDailyConflictError, match="multiple new daily rows"):
        build_weather_snapshot(
            cell_key="cell-1",
            assessment_date=ASSESSMENT,
            reference_elevation_m=420.0,
            new_daily_row_ids=[first[1].id, overlapping[0].id],
        )

    foreign_base = response_for(start=ASSESSMENT, end=ASSESSMENT)
    foreign_response = replace(
        foreign_base,
        request_id="request-foreign",
        location=replace(foreign_base.location, cell_key="cell-2"),
    )
    foreign_rows = store_weather_daily_rows(
        foreign_response,
        start=ASSESSMENT,
        end=ASSESSMENT,
    )

    with pytest.raises(WeatherDailyConflictError, match="another weather cell"):
        build_weather_snapshot(
            cell_key="cell-1",
            assessment_date=ASSESSMENT,
            reference_elevation_m=420.0,
            new_daily_row_ids=[foreign_rows[0].id],
        )

    elevation_base = response_for(start=ASSESSMENT, end=ASSESSMENT)
    changed_elevation = replace(
        elevation_base,
        request_id="request-elevation",
        location=replace(elevation_base.location, elevation_m=500.0),
    )
    changed_rows = store_weather_daily_rows(
        changed_elevation,
        start=ASSESSMENT,
        end=ASSESSMENT,
    )

    with pytest.raises(WeatherDailyConflictError, match="another reference elevation"):
        build_weather_snapshot(
            cell_key="cell-1",
            assessment_date=ASSESSMENT,
            reference_elevation_m=420.0,
            new_daily_row_ids=[changed_rows[0].id],
        )


@pytest.mark.django_db(transaction=True)
def test_previous_snapshot_forecast_days_are_not_reused_for_new_assessment() -> None:
    from weather_summaries.services import store_weather_response

    first = store_weather_response(
        response_for(
            start=ASSESSMENT - timedelta(days=21),
            end=ASSESSMENT + timedelta(days=7),
        ),
        ASSESSMENT,
    )
    next_assessment = ASSESSMENT + timedelta(days=1)
    result = store_weather_response(
        response_for(
            start=next_assessment + timedelta(days=7),
            end=next_assessment + timedelta(days=7),
        ),
        next_assessment,
        previous_snapshot=first.snapshot,
    )

    assert result.snapshot is None
    assert result.summaries == ()


@pytest.mark.django_db(transaction=True)
def test_known_missing_required_value_keeps_snapshot_ready_and_nulls_only_affected_value() -> None:
    from weather_summaries.models import WeatherDaily
    from weather_summaries.services import store_weather_response

    response = response_for(
        start=ASSESSMENT - timedelta(days=21),
        end=ASSESSMENT + timedelta(days=7),
    )
    target_start = int(day_start(day=ASSESSMENT + timedelta(days=7)).timestamp())
    target_end = int(day_start(day=ASSESSMENT + timedelta(days=8)).timestamp())
    precipitation = list(response.variables["precipitation"])
    for index, timestamp in enumerate(response.hourly_timestamps):
        if target_start < timestamp <= target_end:
            precipitation[index] = None
    response = response_with_series(
        response,
        values_by_name={"precipitation": tuple(precipitation)},
    )

    result = store_weather_response(response, ASSESSMENT)

    assert result.snapshot is not None
    target_day = result.snapshot.days.get(date=ASSESSMENT + timedelta(days=7)).daily
    target_summary = result.summaries[-1]
    assert target_day.status == WeatherDaily.Status.CHECKED_KNOWN_MISSING
    assert target_day.rain_mm is None
    assert target_day.mean_temperature_c == 10.0
    assert target_summary.target_rain_mm is None
    assert target_summary.target_mean_temperature_c == 10.0
    assert target_summary.frost is False


@pytest.mark.django_db(transaction=True)
def test_absent_optional_variable_does_not_make_required_daily_rows_incomplete() -> None:
    from weather_summaries.models import WeatherDaily
    from weather_summaries.services import store_weather_response

    result = store_weather_response(
        response_for(
            start=ASSESSMENT - timedelta(days=21),
            end=ASSESSMENT + timedelta(days=7),
            optional=False,
        ),
        ASSESSMENT,
    )

    assert result.snapshot is not None
    assert WeatherDaily.objects.filter(status=WeatherDaily.Status.COMPLETE).count() == 29
    assert result.summaries[0].target_et0_mm is None
    assert result.summaries[0].target_mean_soil_temperature_c is None
    assert result.summaries[0].target_mean_soil_moisture is None


@pytest.mark.django_db(transaction=True)
def test_missing_whole_date_does_not_create_partial_snapshot() -> None:
    from weather_summaries.models import WeatherDaily, WeatherSnapshot
    from weather_summaries.services import store_weather_response

    result = store_weather_response(
        response_for(
            start=ASSESSMENT - timedelta(days=20),
            end=ASSESSMENT + timedelta(days=7),
        ),
        ASSESSMENT,
    )

    assert result.snapshot is None
    assert result.summaries == ()
    assert WeatherSnapshot.objects.count() == 0
    assert WeatherDaily.objects.count() == 28


@pytest.mark.django_db(transaction=True)
def test_gmt_provider_metadata_still_uses_italian_day_boundaries() -> None:
    from weather_summaries.services import store_weather_response

    response = response_for(
        start=ASSESSMENT - timedelta(days=21),
        end=ASSESSMENT + timedelta(days=7),
    )
    gmt_location = replace(response.location, timezone="GMT")

    result = store_weather_response(
        response_with_series(response, values_by_name={}, location=gmt_location),
        ASSESSMENT,
    )

    assert result.snapshot is not None
    assert result.summaries[0].visitor_rain_7_mm == 168.0


@pytest.mark.django_db(transaction=True)
def test_same_assessment_with_different_elevation_rolls_back_new_daily_rows() -> None:
    from weather_summaries.models import WeatherDaily, WeatherSnapshot
    from weather_summaries.services import WeatherDailyConflictError, store_weather_response

    response = response_for(
        start=ASSESSMENT - timedelta(days=21),
        end=ASSESSMENT + timedelta(days=7),
    )
    store_weather_response(response, ASSESSMENT)
    changed_location = replace(response.location, elevation_m=500.0)

    with pytest.raises(WeatherDailyConflictError):
        store_weather_response(
            response_with_series(response, values_by_name={}, location=changed_location),
            ASSESSMENT,
        )

    assert WeatherDaily.objects.count() == 29
    assert WeatherSnapshot.objects.count() == 1
