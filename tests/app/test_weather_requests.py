"""Focused checks for weather cell eligibility, planning, quota and provider metadata."""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from django.db import close_old_connections, connection

from weather_requests.eligibility import (
    WeatherEligibilityError,
    weather_cell,
    weather_cell_key,
    weather_cells_for_forest_cells,
)
from weather_requests.models import WeatherRequest, WeatherRequestAttempt
from weather_requests.planning import (
    MAX_LOCATIONS,
    build_request_spec,
    combine_request_specs,
    nominal_weight,
    plan_cell_request_specs,
    request_compatibility_key,
    required_dates,
    reservation_weight,
    requested_hour_count,
)
from weather_requests.provider import (
    CompletedRequestError,
    PendingRequestError,
    PermanentProviderError,
    ProviderError,
    ResponseValidationError,
    fetch_reserved_weather,
    fetch_weather,
    get_or_create_request,
)
from weather_requests.quota import check_quota, reserve_attempt
from weather_requests.services import _budget_weights


def test_weather_cell_key_rounds_to_the_stored_two_decimal_centre() -> None:
    assert weather_cell_key(latitude="44.05001", longitude="10.84999") == "44.05,10.85"
    assert weather_cell(latitude=44.05, longitude=10.85).key == "44.05,10.85"


def test_weather_cells_deduplicate_and_reject_non_forest_rows() -> None:
    rows = [
        SimpleNamespace(is_forest=True, weather_latitude=44.05, weather_longitude=10.85),
        SimpleNamespace(is_forest=True, weather_latitude=44.050001, weather_longitude=10.849999),
    ]
    cells = weather_cells_for_forest_cells(cells=rows)
    assert cells == (weather_cell(latitude=44.05, longitude=10.85),)
    with pytest.raises(WeatherEligibilityError):
        weather_cells_for_forest_cells(
            cells=[SimpleNamespace(is_forest=False, weather_latitude=44.05, weather_longitude=10.85)]
        )


def test_first_request_contains_29_dates_and_conservative_utc_reservation() -> None:
    cell = weather_cell(latitude=44.05, longitude=10.85)
    spec = build_request_spec(locations=[cell], assessment_date=date(2026, 10, 11))
    assert spec is not None
    assert spec.start_date == date(2026, 9, 20)
    assert spec.end_date == date(2026, 10, 18)
    assert spec.days == 29
    assert float(spec.nominal_weight) == pytest.approx(29 / 14, abs=0.000001)
    assert float(spec.reservation_weight) == pytest.approx(30 / 14, abs=0.000001)
    assert spec.query["timezone"] == "GMT"
    assert spec.query["timeformat"] == "unixtime"
    assert spec.query["start_hour"] == spec.utc_start.strftime("%Y-%m-%dT%H:%M")
    assert spec.query["end_hour"] == spec.utc_end.strftime("%Y-%m-%dT%H:%M")
    assert "start_date" not in spec.query
    assert "end_date" not in spec.query


@pytest.mark.django_db(transaction=True)
def test_provider_transport_receives_iso_minute_hour_bounds() -> None:
    cell = weather_cell(latitude=44.05, longitude=10.85)
    spec = build_request_spec(locations=[cell], assessment_date=date(2026, 10, 12))
    assert spec is not None
    captured: dict[str, str] = {}

    def transport(*, url: str, timeout: float):
        captured["url"] = url
        return _response_for_spec(spec=spec)

    fetch_weather(spec=spec, transport=transport)
    query = parse_qs(urlsplit(captured["url"]).query)
    assert query["start_hour"] == [spec.utc_start.strftime("%Y-%m-%dT%H:%M")]
    assert query["end_hour"] == [spec.utc_end.strftime("%Y-%m-%dT%H:%M")]
    assert "start_date" not in query
    assert "end_date" not in query


@pytest.mark.django_db(transaction=True)
def test_transport_type_error_is_one_call_and_one_counted_attempt() -> None:
    cell = weather_cell(latitude=44.05, longitude=10.85)
    spec = build_request_spec(locations=[cell], assessment_date=date(2026, 10, 12))
    assert spec is not None
    calls = 0

    def transport(*, url: str, timeout: float):
        nonlocal calls
        calls += 1
        raise TypeError("transport implementation failed")

    with pytest.raises(TypeError, match="transport implementation failed"):
        fetch_weather(spec=spec, transport=transport)

    request = WeatherRequest.objects.get(request_digest=spec.digest)
    assert calls == 1
    assert request.attempts.count() == 1
    assert request.attempts.get().outcome == WeatherRequestAttempt.Outcome.CRASHED


def test_existing_coverage_requests_missing_dates_with_three_day_overlap() -> None:
    cell = weather_cell(latitude=44.05, longitude=10.85)
    assessment = date(2026, 10, 11)
    stored = set(required_dates(assessment_date=assessment)) - {
        assessment + timedelta(days=offset) for offset in range(8)
    }
    spec = build_request_spec(locations=[cell], assessment_date=assessment, stored_dates=stored)
    assert spec is not None
    assert spec.start_date == assessment - timedelta(days=3)
    assert spec.end_date == assessment + timedelta(days=7)
    assert spec.days == 11
    assert spec.reservation_weight == 1


def test_first_cell_plan_is_one_29_date_request() -> None:
    specs = plan_cell_request_specs(
        locations=[weather_cell(latitude=44.05, longitude=10.85)],
        assessment_date=date(2026, 10, 12),
        has_previous_snapshot=False,
    )
    assert len(specs) == 1
    assert (specs[0].start_date, specs[0].end_date, specs[0].days) == (
        date(2026, 9, 21),
        date(2026, 10, 19),
        29,
    )


def test_daily_cell_plan_refreshes_the_fixed_three_day_overlap() -> None:
    assessment = date(2026, 10, 12)
    specs = plan_cell_request_specs(
        locations=[weather_cell(latitude=44.05, longitude=10.85)],
        assessment_date=assessment,
        has_previous_snapshot=True,
        completed_dates=required_dates(assessment_date=assessment),
    )
    assert len(specs) == 1
    assert (specs[0].start_date, specs[0].end_date, specs[0].days) == (
        assessment - timedelta(days=3),
        assessment + timedelta(days=7),
        11,
    )
    assert specs[0].reservation_weight == 1


def test_ten_day_stale_snapshot_reuses_safe_history_then_refreshes_daily_window() -> None:
    assessment = date(2026, 10, 12)
    completed = required_dates(assessment_date=assessment - timedelta(days=10))
    specs = plan_cell_request_specs(
        locations=[weather_cell(latitude=44.05, longitude=10.85)],
        assessment_date=assessment,
        has_previous_snapshot=True,
        completed_dates=completed,
    )
    assert [(spec.start_date, spec.end_date) for spec in specs] == [
        (assessment - timedelta(days=3), assessment + timedelta(days=7))
    ]


def test_snapshot_older_than_required_history_is_split_before_daily_refresh() -> None:
    assessment = date(2026, 10, 12)
    specs = plan_cell_request_specs(
        locations=[weather_cell(latitude=44.05, longitude=10.85)],
        assessment_date=assessment,
        has_previous_snapshot=True,
        completed_dates=(),
    )
    assert [(spec.start_date, spec.end_date) for spec in specs] == [
        (assessment - timedelta(days=21), assessment - timedelta(days=9)),
        (assessment - timedelta(days=8), assessment - timedelta(days=4)),
        (assessment - timedelta(days=3), assessment + timedelta(days=7)),
    ]
    assert all(spec.days <= 13 for spec in specs[:-1])
    assert specs[-1].days == 11
    assert all(spec.reservation_weight == 1 for spec in specs)
    with pytest.raises(ValueError, match="multiple requests"):
        build_request_spec(
            locations=[weather_cell(latitude=44.05, longitude=10.85)],
            assessment_date=assessment,
            stored_dates=required_dates(assessment_date=assessment - timedelta(days=30)),
        )


def test_history_parts_keep_one_reserved_call_per_place_across_dst() -> None:
    assessment = date(2026, 11, 15)
    specs = plan_cell_request_specs(
        locations=[weather_cell(latitude=44.05, longitude=10.85)],
        assessment_date=assessment,
        has_previous_snapshot=True,
        completed_dates=(),
    )
    assert requested_hour_count(start_date=specs[0].start_date, end_date=specs[0].end_date) > 13 * 24
    assert all(spec.reservation_weight == 1 for spec in specs)


def test_weight_helpers_count_more_than_ten_variables_without_request_identity() -> None:
    assert nominal_weight(variables=11, days=14, places=1) == Decimal("1.100000")
    assert reservation_weight(
        variables=11,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 13),
        places=1,
    ) == Decimal("1.100000")


def test_fourteen_date_weight_keeps_nominal_and_conservative_closing_hour_distinct() -> None:
    assert nominal_weight(variables=5, days=14, places=1) == Decimal("1.000000")
    assert reservation_weight(
        variables=5,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 14),
        places=1,
    ) == Decimal("1.071429")


def test_budget_weights_are_hand_calculated_per_provider_batch() -> None:
    weights = _budget_weights(cell_count=20)
    assert float(weights["first_nominal"]) == pytest.approx(20 * 29 / 14, abs=0.000001)
    assert weights["daily_nominal"] == 20
    assert float(weights["first_reserved"]) == pytest.approx(20 * 30 / 14, abs=0.000001)
    assert weights["daily_reserved"] == 20
    assert weights["steady_month_nominal"] == 31 * 20
    assert weights["steady_month_reserved"] == 31 * 20
    assert float(weights["first_month_nominal"]) == pytest.approx(
        20 * 29 / 14 + 30 * 20,
        abs=0.000001,
    )
    assert float(weights["first_month_reserved"]) == pytest.approx(
        20 * 30 / 14 + 30 * 20,
        abs=0.000001,
    )


def test_budget_weights_sum_each_batch_at_the_one_hundred_place_cap() -> None:
    weights = _budget_weights(cell_count=101)
    assert float(weights["first_nominal"]) == pytest.approx(101 * 29 / 14, abs=0.00001)
    assert float(weights["first_reserved"]) == pytest.approx(101 * 30 / 14, abs=0.00001)
    assert weights["daily_reserved"] == 101


def test_request_identity_changes_when_any_provider_parameter_changes() -> None:
    cell = weather_cell(latitude=44.05, longitude=10.85)
    first = build_request_spec(locations=[cell], assessment_date=date(2026, 10, 11), model="best_match")
    second = build_request_spec(locations=[cell], assessment_date=date(2026, 10, 11), model="ecmwf_ifs")
    assert first is not None and second is not None
    assert first.digest != second.digest
    assert first.canonical["query"] != second.canonical["query"]


@pytest.mark.parametrize(
    "option",
    [
        {"latitude": "1"},
        {"longitude": "2"},
        {"hourly": "temperature_2m"},
        {"models": "ecmwf_ifs"},
        {"timezone": "Europe/Rome"},
        {"timeformat": "iso8601"},
        {"start_hour": "2026-01-01T00:00"},
        {"end_hour": "2026-01-02T00:00"},
        {"start_date": "2026-01-01"},
        {"end_date": "2026-01-02"},
        {"temperature_unit": "fahrenheit"},
        {"precipitation_unit": "inch"},
        {"cell_selection": "sea"},
    ],
)
def test_request_rejects_options_that_override_reserved_query_contract(
    option: dict[str, str],
) -> None:
    with pytest.raises(ValueError, match="reserved query keys"):
        build_request_spec(
            locations=[weather_cell(latitude=44.05, longitude=10.85)],
            assessment_date=date(2026, 10, 11),
            options=option,
        )


def test_compatible_plans_can_be_batched_without_changing_identity_fields() -> None:
    cells = [weather_cell(latitude=44.05, longitude=10.85), weather_cell(latitude=44.15, longitude=10.95)]
    first = build_request_spec(locations=[cells[0]], assessment_date=date(2026, 10, 11))
    second = build_request_spec(locations=[cells[1]], assessment_date=date(2026, 10, 11))
    assert first is not None and second is not None
    combined = combine_request_specs(specs=[first, second])
    assert request_compatibility_key(spec=first) == request_compatibility_key(spec=combined)
    assert combined.locations == tuple(cells)
    assert combined.digest != first.digest


def test_request_rejects_more_than_one_hundred_locations() -> None:
    cells = [
        weather_cell(latitude=40.05 + index * 0.1, longitude=8.05)
        for index in range(MAX_LOCATIONS + 1)
    ]
    with pytest.raises(ValueError, match="at most 100"):
        build_request_spec(locations=cells, assessment_date=date(2026, 10, 11))


def test_local_day_bounds_include_the_closing_timestamp_on_both_clock_change_days() -> None:
    assert requested_hour_count(start_date=date(2026, 3, 29), end_date=date(2026, 3, 29)) == 24
    assert requested_hour_count(start_date=date(2026, 10, 25), end_date=date(2026, 10, 25)) == 26


def _request() -> WeatherRequest:
    return WeatherRequest.objects.create(
        request_digest="a" * 64,
        canonical_spec={},
        forest_build_version="forest-test-v1",
    )


@pytest.mark.django_db(transaction=True)
def test_quota_reservation_counts_each_attempt_and_respects_minute_boundary() -> None:
    request = _request()
    start = datetime(2026, 10, 11, 12, tzinfo=UTC)
    first = reserve_attempt(request=request, reservation_weight=540, now=start)
    assert first.attempt is not None
    refused = reserve_attempt(request=request, reservation_weight=1, now=start)
    assert refused.attempt is None
    assert refused.quota.retry_at == start + timedelta(seconds=60)
    allowed = reserve_attempt(request=request, reservation_weight=1, now=start + timedelta(seconds=60))
    assert allowed.attempt is not None
    assert WeatherRequestAttempt.objects.count() == 2
    assert check_quota(reservation_weight=540, now=start + timedelta(seconds=60)).allowed is False


@pytest.mark.django_db(transaction=True)
def test_quota_reservation_remains_after_a_subprocess_restart() -> None:
    start = datetime(2026, 10, 11, 12, tzinfo=UTC)
    script = """
from datetime import UTC, datetime

from weather_requests.models import WeatherRequest
from weather_requests.quota import reserve_attempt

request = WeatherRequest.objects.create(
    request_digest="c" * 64,
    canonical_spec={},
    forest_build_version="forest-subprocess-test",
)
result = reserve_attempt(
    request=request,
    reservation_weight=500,
    now=datetime(2026, 10, 11, 12, tzinfo=UTC),
)
assert result.attempt is not None
"""
    environment = os.environ.copy()
    environment["MICOMETEO_DB_NAME"] = str(connection.settings_dict["NAME"])
    completed = subprocess.run(
        [sys.executable, "apps/application/manage.py", "shell", "-c", script],
        cwd=os.getcwd(),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    decision = check_quota(reservation_weight=1, now=start)
    assert decision.usage["minute"] == 500
    assert decision.usage["month"] == 500


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("limit", "window"),
    [(4500, "hour"), (9000, "day"), (270000, "month")],
)
def test_quota_respects_each_longer_rolling_window(limit: int, window: str) -> None:
    request = _request()
    start = datetime(2026, 10, 11, 12, tzinfo=UTC)
    count = limit // 500
    spacing = timedelta(seconds=60) if window == "hour" else timedelta(hours=1)
    WeatherRequestAttempt.objects.bulk_create(
        [
            WeatherRequestAttempt(
                request=request,
                attempt_number=index + 1,
                reserved_at=start - spacing * index,
                reservation_weight=500,
            )
            for index in range(count)
        ]
    )
    decision = check_quota(reservation_weight=1, now=start)
    assert decision.allowed is False
    assert window in decision.reason


@pytest.mark.django_db(transaction=True)
def test_concurrent_reservations_serialize_under_the_single_quota_lock() -> None:
    request = _request()
    start = datetime(2026, 10, 11, 12, tzinfo=UTC)
    barrier = Barrier(2)

    def reserve() -> bool:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return reserve_attempt(
                request=request.id,
                reservation_weight=300,
                now=start,
            ).attempt is not None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: reserve(), range(2)))

    assert sorted(results) == [False, True]
    assert WeatherRequestAttempt.objects.filter(request=request).count() == 1


def _response_for_spec(*, spec, status: int = 200, body: bytes | None = None):
    if body is not None:
        return status, {}, body
    count = int((spec.utc_end - spec.utc_start).total_seconds() // 3600) + 1
    times = [int((spec.utc_start + timedelta(hours=index)).timestamp()) for index in range(count)]
    units = {
        "precipitation": "mm",
        "temperature_2m": "°C",
        "soil_moisture_0_to_7cm": "m³/m³",
        "soil_temperature_0_to_7cm": "°C",
        "et0_fao_evapotranspiration": "mm",
    }
    return [
        {
            "latitude": cell.latitude,
            "longitude": cell.longitude,
            "elevation": 200,
            "timezone": "GMT",
            "hourly_units": {key: units[key] for key in spec.variables},
            "hourly": {
                "time": times,
                **{variable: [0.0] * count for variable in spec.variables},
            },
        }
        for cell in spec.locations
    ]


@pytest.mark.django_db(transaction=True)
def test_provider_accepts_ordered_snapped_grid_coordinates_and_preserves_both_points() -> None:
    cells = [
        weather_cell(latitude=44.05, longitude=10.85),
        weather_cell(latitude=44.15, longitude=10.95),
    ]
    spec = build_request_spec(locations=cells, assessment_date=date(2026, 10, 11))
    assert spec is not None
    payload = _response_for_spec(spec=spec)
    payload[0]["latitude"] += 0.03
    payload[0]["longitude"] -= 0.02
    payload[0]["location_id"] = 0
    payload[1]["latitude"] -= 0.02
    payload[1]["longitude"] += 0.03
    payload[1]["location_id"] = 1
    result = fetch_weather(spec=spec, transport=lambda **kwargs: payload)

    assert result.metadata["locations"][0]["requested_latitude"] == cells[0].latitude
    assert result.metadata["locations"][0]["latitude"] == pytest.approx(44.08)


@pytest.mark.django_db(transaction=True)
def test_provider_rejects_a_mismatched_optional_location_id() -> None:
    cells = [
        weather_cell(latitude=44.05, longitude=10.85),
        weather_cell(latitude=44.15, longitude=10.95),
    ]
    spec = build_request_spec(locations=cells, assessment_date=date(2026, 10, 11))
    assert spec is not None
    payload = _response_for_spec(spec=spec)
    payload[0]["location_id"] = 1
    payload[1]["location_id"] = 0

    with pytest.raises(ResponseValidationError, match="location_id"):
        fetch_weather(spec=spec, transport=lambda **kwargs: payload)


@pytest.mark.django_db(transaction=True)
def test_provider_preserves_source_retrieval_units_elevation_and_raw_hourly_in_memory() -> None:
    cell = weather_cell(latitude=44.05, longitude=10.85)
    spec = build_request_spec(locations=[cell], assessment_date=date(2026, 10, 11))
    assert spec is not None
    retrieved = datetime(2026, 10, 11, 14, tzinfo=UTC)
    result = fetch_weather(
        spec=spec,
        clock=lambda: retrieved,
        transport=lambda **kwargs: _response_for_spec(spec=spec),
    )
    assert result.metadata["source"] == "Open-Meteo Forecast API"
    assert result.metadata["retrieved_at"] == retrieved.isoformat()
    assert result.metadata["locations"][0]["elevation"] == 200
    assert result.metadata["units"]["precipitation"] == "mm"
    assert result.raw_hourly[0]["time"]
    assert result.logical_request.status == WeatherRequest.Status.COMPLETED


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("precipitation", True),
        ("temperature_2m", float("nan")),
        ("soil_temperature_0_to_7cm", "not numeric"),
        ("precipitation", -0.1),
        ("et0_fao_evapotranspiration", -0.1),
        ("soil_moisture_0_to_7cm", 1.1),
    ],
)
def test_provider_rejects_invalid_hourly_values_and_fails_the_attempt(
    variable: str,
    value: object,
) -> None:
    cell = weather_cell(latitude=44.05, longitude=10.85)
    spec = build_request_spec(locations=[cell], assessment_date=date(2026, 10, 11))
    assert spec is not None
    payload = _response_for_spec(spec=spec)
    payload[0]["hourly"][variable][0] = value

    with pytest.raises(ResponseValidationError, match="invalid|negative|outside"):
        fetch_weather(spec=spec, transport=lambda **kwargs: payload)

    request = WeatherRequest.objects.get(request_digest=spec.digest)
    attempt = request.attempts.get()
    assert request.status == WeatherRequest.Status.FAILED
    assert attempt.outcome == WeatherRequestAttempt.Outcome.FAILED
    assert request.completed_at is None


@pytest.mark.django_db(transaction=True)
def test_reserved_fetch_rejects_a_weight_mismatch_before_transport() -> None:
    cell = weather_cell(latitude=44.05, longitude=10.85)
    spec = build_request_spec(locations=[cell], assessment_date=date(2026, 10, 11))
    assert spec is not None
    request = get_or_create_request(spec=spec)
    reservation = reserve_attempt(
        request=request,
        reservation_weight=spec.reservation_weight + Decimal("1"),
        now=datetime(2026, 10, 11, 14, tzinfo=UTC),
    )
    assert reservation.attempt is not None

    with pytest.raises(ProviderError, match="weight"):
        fetch_reserved_weather(
            spec=spec,
            attempt=reservation.attempt,
            transport=lambda **kwargs: (_ for _ in ()).throw(AssertionError("HTTP called")),
        )
    assert reservation.attempt.outcome == WeatherRequestAttempt.Outcome.RESERVATION


@pytest.mark.django_db(transaction=True)
def test_concurrent_reserved_fetch_claims_one_attempt_before_transport() -> None:
    cell = weather_cell(latitude=44.05, longitude=10.85)
    spec = build_request_spec(locations=[cell], assessment_date=date(2026, 10, 11))
    assert spec is not None
    request = get_or_create_request(spec=spec)
    reservation = reserve_attempt(
        request=request,
        reservation_weight=spec.reservation_weight,
        now=datetime(2026, 10, 11, 14, tzinfo=UTC),
    )
    assert reservation.attempt is not None
    first_started = Event()
    release_first = Event()
    calls = 0
    calls_lock = Lock()

    def transport(**kwargs: object):
        nonlocal calls
        with calls_lock:
            calls += 1
            call_number = calls
        if call_number == 1:
            first_started.set()
            assert release_first.wait(timeout=10)
        return _response_for_spec(spec=spec)

    def run() -> object:
        close_old_connections()
        try:
            try:
                return fetch_reserved_weather(
                    spec=spec,
                    attempt=reservation.attempt,
                    transport=transport,
                )
            except Exception as error:
                return error
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(run)
        assert first_started.wait(timeout=10)
        second = executor.submit(run)
        second_result = second.result(timeout=10)
        release_first.set()
        first_result = first.result(timeout=10)

    assert not isinstance(first_result, Exception)
    assert isinstance(second_result, ProviderError)
    assert calls == 1
    attempt = WeatherRequestAttempt.objects.get(pk=reservation.attempt.pk)
    assert attempt.outcome == WeatherRequestAttempt.Outcome.SUCCESS


@pytest.mark.django_db(transaction=True)
def test_429_records_full_message_and_leaves_request_pending_for_later_attempt() -> None:
    cell = weather_cell(latitude=44.05, longitude=10.85)
    spec = build_request_spec(locations=[cell], assessment_date=date(2026, 10, 11))
    assert spec is not None
    message = "provider says too many places, preserve every byte"
    now = datetime(2026, 10, 11, 14, tzinfo=UTC)
    with pytest.raises(PendingRequestError):
        fetch_weather(
            spec=spec,
            clock=lambda: now,
            transport=lambda **kwargs: (429, {"Retry-After": "30"}, message.encode("utf-8")),
        )
    request = WeatherRequest.objects.get(request_digest=spec.digest)
    attempt = request.attempts.get()
    assert request.status == WeatherRequest.Status.PENDING
    assert request.latest_provider_message == message
    assert attempt.outcome == WeatherRequestAttempt.Outcome.REFUSED
    assert attempt.full_message == message
    assert request.retry_at == now + timedelta(seconds=30)


@pytest.mark.django_db(transaction=True)
def test_network_failure_and_worker_crash_each_leave_a_counted_attempt() -> None:
    cell = weather_cell(latitude=44.05, longitude=10.85)
    network_spec = build_request_spec(locations=[cell], assessment_date=date(2026, 10, 11))
    assert network_spec is not None
    now = datetime(2026, 10, 11, 14, tzinfo=UTC)
    with pytest.raises(PendingRequestError):
        fetch_weather(
            spec=network_spec,
            clock=lambda: now,
            transport=lambda **kwargs: (_ for _ in ()).throw(OSError("connection lost")),
        )
    network_request = WeatherRequest.objects.get(request_digest=network_spec.digest)
    network_attempt = network_request.attempts.get()
    assert network_request.status == WeatherRequest.Status.PENDING
    assert network_attempt.outcome == WeatherRequestAttempt.Outcome.RETRY
    assert "connection lost" in network_attempt.full_message

    crash_spec = build_request_spec(locations=[cell], assessment_date=date(2026, 10, 12))
    assert crash_spec is not None
    with pytest.raises(RuntimeError, match="worker crashed"):
        fetch_weather(
            spec=crash_spec,
            clock=lambda: now,
            transport=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("worker crashed")),
        )
    crash_request = WeatherRequest.objects.get(request_digest=crash_spec.digest)
    crash_attempt = crash_request.attempts.get()
    assert crash_request.status == WeatherRequest.Status.PENDING
    assert crash_attempt.outcome == WeatherRequestAttempt.Outcome.CRASHED
    assert "worker crashed" in crash_attempt.full_message


@pytest.mark.django_db(transaction=True)
def test_parameter_refusal_is_permanent_and_keeps_the_full_response_body() -> None:
    cell = weather_cell(latitude=44.05, longitude=10.85)
    spec = build_request_spec(locations=[cell], assessment_date=date(2026, 10, 11))
    assert spec is not None
    message = "bad start_date and unsupported option details"
    with pytest.raises(PermanentProviderError):
        fetch_weather(
            spec=spec,
            transport=lambda **kwargs: (400, {}, message.encode("utf-8")),
        )
    request = WeatherRequest.objects.get(request_digest=spec.digest)
    attempt = request.attempts.get()
    assert request.status == WeatherRequest.Status.FAILED
    assert request.latest_provider_message == message
    assert attempt.outcome == WeatherRequestAttempt.Outcome.FAILED
    assert attempt.full_message == message


@pytest.mark.django_db(transaction=True)
def test_completed_request_cannot_silently_fetch_hourly_data_again() -> None:
    cell = weather_cell(latitude=44.05, longitude=10.85)
    spec = build_request_spec(locations=[cell], assessment_date=date(2026, 10, 11))
    assert spec is not None
    now = datetime(2026, 10, 11, 14, tzinfo=UTC)
    fetch_weather(spec=spec, clock=lambda: now, transport=lambda **kwargs: _response_for_spec(spec=spec))
    with pytest.raises(CompletedRequestError):
        fetch_weather(spec=spec, clock=lambda: now, transport=lambda **kwargs: (_ for _ in ()).throw(AssertionError()))


@pytest.mark.django_db(transaction=True)
def test_completed_request_can_be_recovered_only_with_explicit_refetch_flag() -> None:
    cell = weather_cell(latitude=44.05, longitude=10.85)
    spec = build_request_spec(locations=[cell], assessment_date=date(2026, 10, 11))
    assert spec is not None
    now = datetime(2026, 10, 11, 14, tzinfo=UTC)
    fetch_weather(spec=spec, clock=lambda: now, transport=lambda **kwargs: _response_for_spec(spec=spec))
    recovered = fetch_weather(
        spec=spec,
        clock=lambda: now,
        transport=lambda **kwargs: _response_for_spec(spec=spec),
        allow_completed_refetch=True,
    )
    assert recovered.logical_request.status == WeatherRequest.Status.COMPLETED
    assert recovered.logical_request.attempts.count() == 2
