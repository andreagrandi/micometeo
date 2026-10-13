"""Check scheduled Tuscany weather preparation, stored history and the 38-day window."""

from __future__ import annotations

import io
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.management import call_command
from django.core.management.base import CommandError
from django_tasks_db.models import DBTaskResult

import weather_on_demand.services as weather_services
import weather_summaries.services as summary_services
from background_jobs.worker import MicometeoWorker
from micometeo.weather.openmeteo import ARCHIVE_URL, FORECAST_URL
from micometeo.weather.policy import WEATHER_HISTORY_VERSION
from national_forest.models import ForestBuild, ForestCell, ForestChunk
from national_grid.models import GridBuild, GridBuildCell, GridCell, GridChunk, GridRegion
from national_grid.subset import TUSCANY_ISTAT_CODE as SUBSET_TUSCANY_CODE
from weather_on_demand.models import (
    ScheduledWeatherRun,
    WeatherFetch,
    WeatherFetchBatch,
    WeatherFetchPart,
    WeatherVisitorReservation,
)
from weather_requests.eligibility import (
    TUSCANY_ISTAT_CODE,
    WeatherEligibilityError,
    tuscany_weather_cells,
    weather_cell,
)
from weather_requests.models import WeatherRequest, WeatherRequestAttempt
from weather_requests.planning import plan_current_weather_requests
from weather_requests.services import budget_for_forest_build
from weather_summaries.models import WeatherDaily, WeatherSnapshot
from tests.app.test_weather_on_demand import _FakeOpenMeteo

pytestmark = pytest.mark.django_db(transaction=True)

DAY = date(2026, 10, 11)
FIRST_CELL = "43.50,11.20"
SECOND_CELL = "43.60,11.20"


def _local_day(*, query: dict[str, str], edge: str) -> date:
    """Return the Italian first or last date a request asks for."""
    if f"{edge}_date" in query and "T" not in query[f"{edge}_hour"]:
        return date.fromisoformat(query[f"{edge}_date"])
    value = datetime.fromisoformat(query[f"{edge}_hour"].replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    local = value.astimezone(ZoneInfo("Europe/Rome"))
    return local.date() if edge == "start" else local.date() - timedelta(days=1)


class _Clock:
    """Provide a clock that the test moves by hand."""

    def __init__(self, *, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class _Transport:
    """Record every provider call and fail if two overlap."""

    def __init__(
        self,
        *,
        clock: _Clock,
        inner: Callable[..., object] | None = None,
        override: Callable[[dict[str, str]], object | None] | None = None,
    ) -> None:
        self.clock = clock
        self.inner = inner or _FakeOpenMeteo()
        self.override = override
        self.calls: list[dict[str, object]] = []
        self.in_flight = 0

    def __call__(self, *, url: str, timeout: float) -> object:
        query = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
        assert self.in_flight == 0, "two provider requests ran at the same time"
        self.in_flight += 1
        try:
            self.calls.append(
                {
                    "at": self.clock.now,
                    "endpoint": url.split("?")[0],
                    "start": _local_day(query=query, edge="start"),
                    "end": _local_day(query=query, edge="end"),
                    "cells": len(query["latitude"].split(",")),
                }
            )
            if self.override is not None:
                answer = self.override(query)
                if answer is not None:
                    return answer
            return self.inner(url=url, timeout=timeout)
        finally:
            self.in_flight -= 1

    @property
    def count(self) -> int:
        return len(self.calls)


def _never_called(**kwargs: object) -> object:
    raise AssertionError("The provider must not be called.")


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Use the default sources and keep estimate callbacks out of these tests."""
    monkeypatch.delenv("MICOMETEO_WEATHER_ENDPOINT", raising=False)
    monkeypatch.delenv("MICOMETEO_WEATHER_HISTORY_ENDPOINT", raising=False)
    estimate_callback = weather_services._ESTIMATE_CALLBACK
    cleanup_callback = weather_services._CLEANUP_CALLBACK
    weather_services.configure_estimate_callback(None)
    weather_services.configure_cleanup_callback(None)
    yield
    weather_services.configure_estimate_callback(estimate_callback)
    weather_services.configure_cleanup_callback(cleanup_callback)


def _square(*, west: int, south: int) -> Polygon:
    return Polygon(
        [(west, south), (west + 500, south), (west + 500, south + 500), (west, south + 500), (west, south)]
    )


@pytest.fixture
def forest(settings) -> dict[str, str]:
    """Build a forest with two Tuscany weather cells, one Lazio cell and one non-forest square."""
    grid = GridBuild.objects.create(
        version=f"grid-{uuid.uuid4()}",
        fingerprint="d" * 64,
        status=GridBuild.Status.COMPLETED,
        planned_chunk_count=1,
        completed_chunk_count=1,
        cell_count=5,
    )
    tuscany = GridRegion.objects.create(
        build=grid, istat_code="09", name="Toscana", geometry=MultiPolygon([_square(west=1_000, south=1_000)])
    )
    lazio = GridRegion.objects.create(
        build=grid, istat_code="12", name="Lazio", geometry=MultiPolygon([_square(west=9_000, south=1_000)])
    )
    chunk = GridChunk.objects.create(
        build=grid,
        west_e=1_000,
        south_n=1_000,
        east_e=11_000,
        north_n=1_500,
        status=GridChunk.Status.COMPLETED,
        cell_count=5,
    )
    forest_build = ForestBuild.objects.create(
        version=f"forest-{uuid.uuid4()}",
        grid_build=grid,
        fingerprint="e" * 64,
        status=ForestBuild.Status.COMPLETED,
        planned_chunk_count=1,
        completed_chunk_count=1,
        cell_count=5,
        forest_cell_count=4,
        weather_cell_count=3,
    )
    forest_chunk = ForestChunk.objects.create(
        build=forest_build,
        grid_chunk=chunk,
        west_e=1_000,
        south_n=1_000,
        east_e=11_000,
        north_n=1_500,
        status=ForestChunk.Status.COMPLETED,
        cell_count=5,
    )
    squares = (
        (tuscany, True, 43.5, 11.2),
        (tuscany, True, 43.5, 11.2),
        (tuscany, True, 43.6, 11.2),
        (tuscany, False, None, None),
        (lazio, True, 41.9, 12.5),
    )
    for index, (region, is_forest, latitude, longitude) in enumerate(squares):
        west = 1_000 + index * 500
        cell = GridCell.objects.create(
            cell_id=f"500m_E{west}_N1000-{grid.version}",
            corner_e=west,
            corner_n=1_000,
            geometry=_square(west=west, south=1_000),
        )
        membership = GridBuildCell.objects.create(
            build=grid,
            cell=cell,
            chunk=chunk,
            owner_region=region,
            land_geometry=MultiPolygon([_square(west=west, south=1_000)]),
            land_share=1.0,
        )
        ForestCell.objects.create(
            build=forest_build,
            grid_build_cell=membership,
            chunk=forest_chunk,
            total_pixel_count=100,
            valid_pixel_count=100,
            forest_pixel_count=80 if is_forest else 0,
            broadleaf_pixel_count=80 if is_forest else 0,
            conifer_pixel_count=0,
            unclassifiable_pixel_count=0,
            outside_pixel_count=0,
            valid_coverage=1.0,
            coverage_quality="high",
            forest_share=0.8 if is_forest else 0.0,
            broadleaf_share=1.0 if is_forest else 0.0,
            leaf_type=ForestCell.LeafType.BROADLEAF if is_forest else ForestCell.LeafType.NO_FOREST,
            is_forest=is_forest,
            weather_latitude=latitude,
            weather_longitude=longitude,
        )
    settings.MICOMETEO_FOREST_BUILD_VERSION = forest_build.version
    return {"version": forest_build.version}


def _clock(*, day: date = DAY, hour: int = 2) -> _Clock:
    return _Clock(now=datetime(day.year, day.month, day.day, hour, tzinfo=UTC))


def _start(*, forest: dict[str, str], clock: _Clock, day: date = DAY) -> ScheduledWeatherRun:
    return weather_services.start_scheduled_weather_run(
        assessment_date=day,
        region_code="09",
        forest_build_version=forest["version"],
        clock=clock,
    )


def _task_time(*, run: ScheduledWeatherRun) -> datetime | None:
    """Return when the queued task of a run may start, or None when it may start now."""
    when = DBTaskResult.objects.get(id=run.task_id).run_after
    return when if when.year < 3000 else None


def _drive(
    *,
    run: ScheduledWeatherRun,
    clock: _Clock,
    transport: _Transport,
    limit: int = 80,
) -> ScheduledWeatherRun:
    """Run steps the way a worker would, moving the fake clock to each queued start time."""
    for _ in range(limit):
        run.refresh_from_db()
        if run.status in {ScheduledWeatherRun.Status.COMPLETED, ScheduledWeatherRun.Status.FAILED}:
            return run
        weather_services.run_scheduled_weather_step(run_id=run.id, clock=clock, transport=transport)
        run.refresh_from_db()
        if run.status in {ScheduledWeatherRun.Status.COMPLETED, ScheduledWeatherRun.Status.FAILED}:
            return run
        when = _task_time(run=run)
        if when is not None and when > clock.now:
            clock.now = when
    raise AssertionError("The run did not finish.")


def _daily(
    *,
    cell_key: str,
    day: date,
    endpoint: str,
    created_offset: int = 0,
    metadata: dict[str, object] | None = None,
    status: str = WeatherDaily.Status.COMPLETE,
) -> WeatherDaily:
    return WeatherDaily.objects.create(
        cell_key=cell_key,
        date=day,
        source_provider="open-meteo",
        source_model="best_match",
        source_endpoint=endpoint,
        source_id=f"source-{uuid.uuid4()}",
        request_id=f"request-{uuid.uuid4()}",
        attempt_id=uuid.uuid4(),
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=created_offset),
        requested_latitude=43.5,
        requested_longitude=11.2,
        returned_latitude=43.5,
        returned_longitude=11.2,
        reference_elevation_m=200,
        rain_mm=1.0,
        status=status,
        metadata=metadata or {},
    )


# Window and planner


@pytest.mark.parametrize(
    ("instant", "expected_day"),
    [
        (datetime(2026, 3, 28, 23, 30, tzinfo=UTC), date(2026, 3, 29)),
        (datetime(2026, 10, 24, 22, 30, tzinfo=UTC), date(2026, 10, 25)),
    ],
)
def test_window_is_30_completed_days_today_and_7_forecast_days_in_rome(
    instant: datetime, expected_day: date
) -> None:
    today = weather_services.italian_assessment_date(clock=lambda: instant)
    first_day, last_day = weather_services.weather_window(assessment_date=today)

    assert today == expected_day
    assert first_day == today - timedelta(days=30)
    assert last_day == today + timedelta(days=7)
    assert (last_day - first_day).days + 1 == 38
    planned = plan_current_weather_requests(
        locations=[weather_cell(latitude=43.5, longitude=11.2)], assessment_date=today
    )
    assert min(spec.start_date for spec in planned) == first_day
    assert max(spec.end_date for spec in planned) == last_day


@pytest.mark.parametrize("day", [date(2026, 3, 29), date(2026, 10, 25)])
def test_snapshot_covers_exactly_38_dates_on_clock_change_days(day: date, forest) -> None:
    clock = _clock(day=day)
    run = _drive(run=_start(forest=forest, clock=clock, day=day), clock=clock, transport=_Transport(clock=clock))

    assert run.status == ScheduledWeatherRun.Status.COMPLETED
    snapshot = WeatherSnapshot.objects.get(cell_key=FIRST_CELL, assessment_date=day)
    dates = list(snapshot.days.order_by("date").values_list("date", flat=True))
    assert dates == [day - timedelta(days=30) + timedelta(days=index) for index in range(38)]


def test_initial_plan_is_three_history_parts_and_one_eight_day_forecast() -> None:
    cell = weather_cell(latitude=43.5, longitude=11.2)

    specs = plan_current_weather_requests(locations=[cell], assessment_date=DAY)

    assert [(spec.start_date, spec.end_date, spec.endpoint) for spec in specs] == [
        (DAY - timedelta(days=30), DAY - timedelta(days=18), ARCHIVE_URL),
        (DAY - timedelta(days=17), DAY - timedelta(days=5), ARCHIVE_URL),
        (DAY - timedelta(days=4), DAY - timedelta(days=1), ARCHIVE_URL),
        (DAY, DAY + timedelta(days=7), FORECAST_URL),
    ]
    assert [(spec.end_date - spec.start_date).days + 1 for spec in specs] == [13, 13, 4, 8]
    assert sum(spec.reservation_weight for spec in specs) == 4


def test_refresh_plan_is_yesterday_and_an_eight_day_forecast() -> None:
    cell = weather_cell(latitude=43.5, longitude=11.2)
    completed = [DAY - timedelta(days=offset) for offset in range(2, 31)]

    specs = plan_current_weather_requests(locations=[cell], assessment_date=DAY, completed_dates=completed)

    assert [(spec.start_date, spec.end_date) for spec in specs] == [
        (DAY - timedelta(days=1), DAY - timedelta(days=1)),
        (DAY, DAY + timedelta(days=7)),
    ]
    assert sum(spec.reservation_weight for spec in specs) == 2


def test_tuscany_sized_dry_run_costs_1332_counted_calls_in_16_requests() -> None:
    cells = [weather_cell(latitude=43.0 + index // 20 * 0.1, longitude=10.0 + index % 20 * 0.1) for index in range(333)]

    plan = weather_services.plan_scheduled_weather(cells=cells, assessment_date=DAY)

    assert plan.cells_total == 333
    assert plan.mode == "initial"
    assert plan.counted_calls == Decimal("1332")
    assert plan.http_requests == 16
    assert [(part.kind, part.cells, part.http_requests) for part in plan.parts] == [
        ("history", 333, 4),
        ("history", 333, 4),
        ("history", 333, 4),
        ("forecast", 333, 4),
    ]


def test_budget_report_keeps_counted_calls_and_http_requests_apart(forest) -> None:
    report = budget_for_forest_build(forest_build_version=forest["version"])

    assert report["national"]["distinct_weather_cells"] == 3
    assert report["counted_calls"]["reserved"] == {"initial_load": 12.0, "nightly_refresh": 6.0}
    assert report["counted_calls"]["nominal"] == {"initial_load": 12.0, "nightly_refresh": 6.0}
    assert report["http_requests"] == {"initial_load": 4, "nightly_refresh": 2}
    assert "first_29_dates" not in str(report)


# Scope


def test_scope_helper_matches_the_tuscany_code_used_by_the_subset_tool() -> None:
    assert TUSCANY_ISTAT_CODE == SUBSET_TUSCANY_CODE == "09"


def test_tuscany_cells_count_each_shared_weather_cell_once(forest) -> None:
    cells = tuscany_weather_cells(forest_build_version=forest["version"])

    assert [cell.key for cell in cells] == [FIRST_CELL, SECOND_CELL]
    assert ForestCell.objects.filter(
        build__version=forest["version"],
        is_forest=True,
        grid_build_cell__owner_region__istat_code="09",
    ).count() == 3


@pytest.mark.parametrize("region_code", ["12", "", "9", "IT"])
def test_non_tuscany_regions_are_rejected(region_code: str, forest) -> None:
    clock = _clock()
    with pytest.raises(WeatherEligibilityError, match="only Tuscany"):
        tuscany_weather_cells(forest_build_version=forest["version"], region_code=region_code)
    with pytest.raises(WeatherEligibilityError):
        weather_services.start_scheduled_weather_run(
            assessment_date=DAY,
            region_code=region_code,
            forest_build_version=forest["version"],
            clock=clock,
        )
    assert ScheduledWeatherRun.objects.count() == 0
    assert WeatherRequest.objects.count() == 0


def test_command_rejects_other_regions_and_unknown_forest_builds(forest) -> None:
    with pytest.raises(CommandError, match="only Tuscany"):
        call_command("refresh_tuscany_weather", "--dry-run", "--region-code=12", stdout=io.StringIO())
    with pytest.raises(CommandError, match="No forest build"):
        call_command(
            "refresh_tuscany_weather", "--dry-run", "--forest-build-version=missing", stdout=io.StringIO()
        )


# Dry run and command


def _table_counts() -> dict[str, int]:
    return {
        model.__name__: model.objects.count()
        for model in (
            ScheduledWeatherRun,
            WeatherFetch,
            WeatherFetchBatch,
            WeatherFetchPart,
            WeatherRequest,
            WeatherRequestAttempt,
            WeatherDaily,
            WeatherSnapshot,
            DBTaskResult,
        )
    }


def test_dry_run_prints_the_plan_and_writes_nothing(forest) -> None:
    before = _table_counts()
    out = io.StringIO()

    call_command("refresh_tuscany_weather", "--dry-run", f"--assessment-date={DAY.isoformat()}", stdout=out)

    text = out.getvalue()
    assert "Dry run for 2026-10-11, no data written" in text
    assert "Window: 2026-09-11 through 2026-10-18" in text
    assert "Mode: initial" in text
    assert "Weather cells: 2, already ready for the date: 0" in text
    assert "Counted calls: 8" in text
    assert "HTTP requests: 4" in text
    assert _table_counts() == before


def test_dry_run_matches_the_real_plan_for_an_initial_load_and_a_refresh(forest) -> None:
    clock = _clock()
    cells = tuscany_weather_cells(forest_build_version=forest["version"])
    initial = weather_services.plan_scheduled_weather(cells=cells, assessment_date=DAY)
    run = _start(forest=forest, clock=clock)
    assert run.mode == initial.mode == "initial"
    assert run.planned_counted_calls == initial.counted_calls == Decimal("8")
    assert run.planned_http_requests == initial.http_requests == 4
    assert WeatherFetchBatch.objects.filter(scheduled_run=run).count() == initial.http_requests
    _drive(run=run, clock=clock, transport=_Transport(clock=clock))

    next_day = DAY + timedelta(days=1)
    refresh = weather_services.plan_scheduled_weather(cells=cells, assessment_date=next_day)
    assert refresh.mode == "refresh"
    assert refresh.counted_calls == Decimal("4")
    assert refresh.http_requests == 2
    assert [(part.kind, part.start_date, part.end_date) for part in refresh.parts] == [
        ("history", DAY, DAY),
        ("forecast", next_day, next_day + timedelta(days=7)),
    ]
    before = _table_counts()
    weather_services.plan_scheduled_weather(cells=cells, assessment_date=next_day)
    assert _table_counts() == before


def test_command_starts_a_run_and_prints_its_id(forest) -> None:
    out = io.StringIO()

    call_command("refresh_tuscany_weather", f"--assessment-date={DAY.isoformat()}", stdout=out)

    run = ScheduledWeatherRun.objects.get()
    assert f"run_id={run.id}" in out.getvalue()
    assert run.region_code == "09"
    assert run.forest_build_version == forest["version"]
    assert DBTaskResult.objects.filter(task_path="weather_on_demand.tasks.scheduled_weather_run_task").count() == 1


def test_worker_claims_a_scheduled_run_under_one_logical_key_per_run(forest) -> None:
    run = _start(forest=forest, clock=_clock())
    task_result = DBTaskResult.objects.get(id=run.task_id)

    keys = MicometeoWorker._logical_lock_keys_for_task(None, task_result)

    assert keys == (f"scheduled-weather-run:09:{DAY.isoformat()}",)


# Pacing, single request and restarts


def test_run_starts_one_request_at_a_time_at_least_90_seconds_apart(forest) -> None:
    clock = _clock()
    transport = _Transport(clock=clock)
    run = _start(forest=forest, clock=clock)

    run = _drive(run=run, clock=clock, transport=transport)

    assert run.status == ScheduledWeatherRun.Status.COMPLETED
    assert transport.count == 4
    starts = [call["at"] for call in transport.calls]
    assert all(later - earlier >= timedelta(seconds=90) for earlier, later in zip(starts, starts[1:]))
    assert run.provider_attempts == 4
    assert run.started_at is not None and run.completed_at is not None
    assert WeatherSnapshot.objects.filter(assessment_date=DAY).count() == 2
    assert WeatherRequestAttempt.objects.count() == 4
    sources = {request.provenance["source"] for request in WeatherRequest.objects.all()}
    assert sources == {"tuscany_schedule"}


def test_a_step_before_next_start_at_makes_no_request_and_queues_itself(forest) -> None:
    clock = _clock()
    transport = _Transport(clock=clock)
    run = _start(forest=forest, clock=clock)

    weather_services.run_scheduled_weather_step(run_id=run.id, clock=clock, transport=transport)
    run.refresh_from_db()
    assert transport.count == 1
    assert run.next_start_at == clock.now + timedelta(seconds=90)
    queued_after_first_step = run.task_id

    clock.now += timedelta(seconds=30)
    weather_services.run_scheduled_weather_step(run_id=run.id, clock=clock, transport=transport)
    run.refresh_from_db()

    assert transport.count == 1
    assert run.task_id != queued_after_first_step
    assert _task_time(run=run) == run.next_start_at


def test_duplicate_start_makes_no_second_run_batch_request_or_task(forest) -> None:
    clock = _clock()
    first = _start(forest=forest, clock=clock)
    counts = _table_counts()

    second = _start(forest=forest, clock=clock)

    assert second.id == first.id
    assert second.task_id == first.task_id
    assert _table_counts() == counts
    transport = _Transport(clock=clock)
    _drive(run=first, clock=clock, transport=transport)
    finished_counts = _table_counts()
    third = _start(forest=forest, clock=clock)
    assert third.status == ScheduledWeatherRun.Status.COMPLETED
    assert _table_counts() == finished_counts
    assert transport.count == 4


def test_restart_resumes_without_downloading_completed_parts_again(forest) -> None:
    clock = _clock()
    transport = _Transport(clock=clock)
    run = _start(forest=forest, clock=clock)
    for _ in range(2):
        weather_services.run_scheduled_weather_step(run_id=run.id, clock=clock, transport=transport)
        run.refresh_from_db()
        clock.now = _task_time(run=run) or clock.now
    assert transport.count == 2
    DBTaskResult.objects.filter(id=run.task_id).update(status="FAILED")

    weather_services.recover_weather_fetches(now=clock.now)
    run.refresh_from_db()
    assert DBTaskResult.objects.get(id=run.task_id).status == "READY"
    resumed = _start(forest=forest, clock=clock)
    assert resumed.id == run.id
    run = _drive(run=run, clock=clock, transport=transport)

    assert run.status == ScheduledWeatherRun.Status.COMPLETED
    ranges = [(call["start"], call["end"]) for call in transport.calls]
    assert len(ranges) == len(set(ranges)) == 4
    assert WeatherFetchBatch.objects.filter(scheduled_run=run).count() == 4


def test_batches_over_100_cells_skip_the_visitor_limit_for_scheduled_runs() -> None:
    cells = [weather_cell(latitude=43.0 + index // 20 * 0.1, longitude=10.0 + index % 20 * 0.1) for index in range(101)]

    batches = weather_services._plan_batches(
        cells=cells,
        assessment_date=DAY,
        visitor_hash=None,
        now=datetime(2026, 10, 11, 2, tzinfo=UTC),
        model="best_match",
        forest_build_version="forest",
        options=None,
    )

    assert len(batches) == 8
    assert sorted(request.canonical_spec["query"]["latitude"].count(",") + 1 for request in WeatherRequest.objects.all()) == [1] * 4 + [100] * 4
    assert WeatherVisitorReservation.objects.count() == 0
    assert WeatherFetch.objects.filter(assessment_date=DAY).count() == 101
    assert not WeatherFetch.objects.filter(reason_code="visitor_limit").exists()


# Quota and retries


def _fill_quota(*, window: str, now: datetime) -> None:
    """Record earlier attempts that use up exactly one rolling allowance."""
    quota_request = WeatherRequest.objects.create(
        request_digest="q" * 64, canonical_spec={}, forest_build_version="quota-test"
    )
    ages = {
        "minute": [(1, timedelta(seconds=10), 540)],
        "hour": [(9, timedelta(seconds=120), 500)],
        "day": [(18, timedelta(hours=2), 500)],
        "month": [(540, timedelta(days=2), 500)],
    }
    spacing = {
        "minute": timedelta(0),
        "hour": timedelta(seconds=70),
        "day": timedelta(minutes=15),
        "month": timedelta(hours=1),
    }[window]
    count, first_age, weight = ages[window][0]
    WeatherRequestAttempt.objects.bulk_create(
        [
            WeatherRequestAttempt(
                request=quota_request,
                attempt_number=index + 1,
                reserved_at=now - first_age - spacing * index,
                reservation_weight=weight,
                outcome=WeatherRequestAttempt.Outcome.SUCCESS,
            )
            for index in range(count)
        ]
    )


@pytest.mark.parametrize("window", ["minute", "hour", "day", "month"])
def test_each_rolling_quota_window_blocks_the_run_until_it_clears(window: str, forest) -> None:
    clock = _clock()
    transport = _Transport(clock=clock)
    run = _start(forest=forest, clock=clock)
    _fill_quota(window=window, now=clock.now)
    attempts_before = WeatherRequestAttempt.objects.count()

    weather_services.run_scheduled_weather_step(run_id=run.id, clock=clock, transport=transport)
    run.refresh_from_db()

    assert transport.count == 0
    assert run.provider_attempts == 0
    assert run.status == ScheduledWeatherRun.Status.RUNNING
    assert run.reason_code == "quota_exhausted"
    assert f"Quota limit reached: {window}" in run.full_reason
    retry_at = _task_time(run=run)
    assert retry_at is not None and retry_at > clock.now
    assert run.next_start_at == retry_at
    assert WeatherRequestAttempt.objects.count() == attempts_before

    clock.now = retry_at - timedelta(seconds=1)
    weather_services.run_scheduled_weather_step(run_id=run.id, clock=clock, transport=transport)
    assert transport.count == 0

    run = _drive(run=run, clock=clock, transport=transport)

    assert run.status == ScheduledWeatherRun.Status.COMPLETED
    assert transport.calls[0]["at"] >= retry_at
    assert transport.count == 4


def test_transient_failure_retries_later_and_stores_nothing(forest) -> None:
    clock = _clock()
    state = {"failures": 1}

    def fail_once(query: dict[str, str]) -> object | None:
        if state["failures"]:
            state["failures"] -= 1
            return 503, {}, b"temporarily busy"
        return None

    transport = _Transport(clock=clock, override=fail_once)
    run = _start(forest=forest, clock=clock)

    weather_services.run_scheduled_weather_step(run_id=run.id, clock=clock, transport=transport)
    run.refresh_from_db()

    assert run.status == ScheduledWeatherRun.Status.RUNNING
    assert run.provider_attempts == 1
    assert WeatherDaily.objects.count() == 0
    assert WeatherSnapshot.objects.count() == 0
    assert run.reason_code == "provider_unavailable"
    assert _task_time(run=run) >= run.next_start_at
    run = _drive(run=run, clock=clock, transport=transport)
    assert run.status == ScheduledWeatherRun.Status.COMPLETED
    assert run.provider_attempts == 5
    assert transport.count == 5


def test_provider_refusal_with_429_waits_and_is_recorded(forest) -> None:
    clock = _clock()
    state = {"failures": 1}

    def refuse_once(query: dict[str, str]) -> object | None:
        if state["failures"]:
            state["failures"] -= 1
            return 429, {"Retry-After": "600"}, b"daily limit"
        return None

    transport = _Transport(clock=clock, override=refuse_once)
    run = _start(forest=forest, clock=clock)

    weather_services.run_scheduled_weather_step(run_id=run.id, clock=clock, transport=transport)
    run.refresh_from_db()

    assert run.reason_code == "provider_refused"
    assert _task_time(run=run) == clock.now + timedelta(seconds=600)
    assert WeatherDaily.objects.count() == 0
    assert WeatherRequestAttempt.objects.get().outcome == WeatherRequestAttempt.Outcome.REFUSED


# Stored history


def test_next_night_reuses_stored_history_and_fetches_only_the_new_day_and_forecast(forest) -> None:
    clock = _clock()
    first_transport = _Transport(clock=clock)
    first = _drive(run=_start(forest=forest, clock=clock), clock=clock, transport=first_transport)
    first_snapshot_ids = set(WeatherSnapshot.objects.values_list("id", flat=True))
    first_row_ids = set(WeatherDaily.objects.values_list("id", flat=True))
    assert first.status == ScheduledWeatherRun.Status.COMPLETED
    next_day = DAY + timedelta(days=1)
    assert DAY not in summary_services.stored_history_rows(cell_key=FIRST_CELL, assessment_date=next_day)

    clock = _clock(day=next_day)
    transport = _Transport(clock=clock)
    run = _drive(run=_start(forest=forest, clock=clock, day=next_day), clock=clock, transport=transport)

    assert run.mode == "refresh"
    assert run.status == ScheduledWeatherRun.Status.COMPLETED
    assert {
        (call["endpoint"], call["start"], call["end"], call["cells"]) for call in transport.calls
    } == {
        (ARCHIVE_URL, DAY, DAY, 2),
        (FORECAST_URL, next_day, next_day + timedelta(days=7), 2),
    }
    assert first_snapshot_ids <= set(WeatherSnapshot.objects.values_list("id", flat=True))
    assert first_row_ids <= set(WeatherDaily.objects.values_list("id", flat=True))
    new_row = WeatherDaily.objects.get(cell_key=FIRST_CELL, date=DAY, source_endpoint=ARCHIVE_URL)
    assert new_row.metadata["history_version"] == WEATHER_HISTORY_VERSION
    old_forecast_row = WeatherDaily.objects.get(cell_key=FIRST_CELL, date=DAY, source_endpoint=FORECAST_URL)
    assert old_forecast_row.id in first_row_ids
    snapshot = WeatherSnapshot.objects.get(cell_key=FIRST_CELL, assessment_date=next_day)
    assert snapshot.days.get(date=DAY).daily_id == new_row.id
    assert snapshot.days.count() == 38
    stored_parts = WeatherFetchPart.objects.filter(
        fetch__assessment_date=next_day, reason_code="stored_history", batch__isnull=True
    )
    assert stored_parts.count() == 2
    assert {part.request_id for part in stored_parts} == {None}


def test_a_new_process_reads_stored_history_with_no_provider_call_for_old_days(forest) -> None:
    clock = _clock()
    _drive(run=_start(forest=forest, clock=clock), clock=clock, transport=_Transport(clock=clock))
    next_day = DAY + timedelta(days=1)
    for cell_key in (FIRST_CELL, SECOND_CELL):
        rows = summary_services.stored_history_rows(cell_key=cell_key, assessment_date=next_day)
        assert sorted(rows) == [DAY - timedelta(days=offset) for offset in range(29, 0, -1)]

    plan = weather_services.plan_scheduled_weather(
        cells=tuscany_weather_cells(forest_build_version=forest["version"]),
        assessment_date=next_day,
    )

    assert plan.counted_calls == Decimal("4")
    assert all(part.start_date >= DAY for part in plan.parts)
    completed_clock = _clock()
    completed = _start(forest=forest, clock=completed_clock)
    assert completed.status == ScheduledWeatherRun.Status.COMPLETED
    assert weather_services.run_scheduled_weather_step(
        run_id=completed.id, clock=completed_clock, transport=_never_called
    ).status == ScheduledWeatherRun.Status.COMPLETED


def test_forecast_rows_for_past_days_never_count_as_history() -> None:
    _daily(cell_key=FIRST_CELL, day=DAY - timedelta(days=3), endpoint=FORECAST_URL)
    archive = _daily(cell_key=FIRST_CELL, day=DAY - timedelta(days=2), endpoint=ARCHIVE_URL)
    _daily(cell_key=SECOND_CELL, day=DAY - timedelta(days=2), endpoint=ARCHIVE_URL)
    _daily(cell_key=FIRST_CELL, day=DAY - timedelta(days=40), endpoint=ARCHIVE_URL)
    _daily(cell_key=FIRST_CELL, day=DAY, endpoint=ARCHIVE_URL)

    rows = summary_services.stored_history_rows(cell_key=FIRST_CELL, assessment_date=DAY)

    assert {day: row.id for day, row in rows.items()} == {DAY - timedelta(days=2): archive.id}


def test_earliest_stored_row_wins_and_known_missing_rows_count() -> None:
    first = _daily(cell_key=FIRST_CELL, day=DAY - timedelta(days=2), endpoint=ARCHIVE_URL)
    _daily(cell_key=FIRST_CELL, day=DAY - timedelta(days=2), endpoint=ARCHIVE_URL, created_offset=5)
    missing = _daily(
        cell_key=FIRST_CELL,
        day=DAY - timedelta(days=3),
        endpoint=ARCHIVE_URL,
        status=WeatherDaily.Status.CHECKED_KNOWN_MISSING,
    )

    rows = summary_services.stored_history_rows(cell_key=FIRST_CELL, assessment_date=DAY)

    assert rows[DAY - timedelta(days=2)].id == first.id
    assert rows[DAY - timedelta(days=3)].id == missing.id


def test_known_missing_history_is_stored_and_never_fetched_again(forest) -> None:
    clock = _clock()
    transport = _Transport(clock=clock, inner=_FakeOpenMeteo(rain_values=(None,)))
    run = _drive(run=_start(forest=forest, clock=clock), clock=clock, transport=transport)

    assert run.status == ScheduledWeatherRun.Status.COMPLETED
    history = WeatherDaily.objects.filter(source_endpoint=ARCHIVE_URL)
    assert history.exists()
    assert set(history.values_list("status", flat=True)) == {WeatherDaily.Status.CHECKED_KNOWN_MISSING}
    next_day = DAY + timedelta(days=1)
    plan = weather_services.plan_scheduled_weather(
        cells=tuscany_weather_cells(forest_build_version=forest["version"]), assessment_date=next_day
    )
    assert all(part.start_date >= DAY for part in plan.parts)


# Failures and corrections


def test_provider_refusal_fails_the_run_and_keeps_existing_rows_and_snapshots(forest) -> None:
    clock = _clock()
    _drive(run=_start(forest=forest, clock=clock), clock=clock, transport=_Transport(clock=clock))
    rows_before = {row.id: row.rain_mm for row in WeatherDaily.objects.all()}
    snapshots_before = {snapshot.id: snapshot.metadata for snapshot in WeatherSnapshot.objects.all()}
    next_day = DAY + timedelta(days=1)
    clock = _clock(day=next_day)
    refusing = _Transport(clock=clock, override=lambda query: (400, {}, b"not allowed"))

    run = _drive(run=_start(forest=forest, clock=clock, day=next_day), clock=clock, transport=refusing)

    assert run.status == ScheduledWeatherRun.Status.FAILED
    assert run.reason_code == "provider_refused"
    assert "of 2 weather cells have no snapshot" in run.full_reason
    assert {row.id: row.rain_mm for row in WeatherDaily.objects.filter(id__in=rows_before)} == rows_before
    assert {
        snapshot.id: snapshot.metadata for snapshot in WeatherSnapshot.objects.filter(id__in=snapshots_before)
    } == snapshots_before
    assert not WeatherSnapshot.objects.filter(assessment_date=next_day).exists()
    assert not WeatherDaily.objects.exclude(id__in=rows_before).exists()


def test_partial_response_is_rejected_and_stores_no_rows(forest) -> None:
    clock = _clock()
    inner = _FakeOpenMeteo()

    def truncated(*, url: str, timeout: float) -> object:
        payload = inner(url=url, timeout=timeout)
        for location in payload:
            location["hourly"] = {key: values[:-5] for key, values in location["hourly"].items()}
        return payload

    transport = _Transport(clock=clock, inner=truncated)
    run = _drive(run=_start(forest=forest, clock=clock), clock=clock, transport=transport)

    assert run.status == ScheduledWeatherRun.Status.FAILED
    assert WeatherDaily.objects.count() == 0
    assert WeatherSnapshot.objects.count() == 0
    assert transport.count == 1


def test_history_version_correction_refetches_history_and_keeps_old_evidence(
    forest, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _clock()
    _drive(run=_start(forest=forest, clock=clock), clock=clock, transport=_Transport(clock=clock))
    old_rows = {row.id: row.metadata for row in WeatherDaily.objects.all()}
    old_snapshot_ids = set(WeatherSnapshot.objects.values_list("id", flat=True))
    next_day = DAY + timedelta(days=1)
    monkeypatch.setattr(summary_services, "WEATHER_HISTORY_VERSION", WEATHER_HISTORY_VERSION + 1)
    assert summary_services.stored_history_rows(cell_key=FIRST_CELL, assessment_date=next_day) == {}

    clock = _clock(day=next_day)
    transport = _Transport(clock=clock)
    run = _drive(run=_start(forest=forest, clock=clock, day=next_day), clock=clock, transport=transport)

    assert run.status == ScheduledWeatherRun.Status.COMPLETED
    assert run.planned_counted_calls == Decimal("8")
    assert {(call["start"], call["end"]) for call in transport.calls} == {
        (next_day - timedelta(days=30), next_day - timedelta(days=18)),
        (next_day - timedelta(days=17), next_day - timedelta(days=5)),
        (next_day - timedelta(days=4), next_day - timedelta(days=1)),
        (next_day, next_day + timedelta(days=7)),
    }
    assert {row.id: row.metadata for row in WeatherDaily.objects.filter(id__in=old_rows)} == old_rows
    assert old_snapshot_ids <= set(WeatherSnapshot.objects.values_list("id", flat=True))
    new_rows = WeatherDaily.objects.exclude(id__in=old_rows).filter(source_endpoint=ARCHIVE_URL)
    assert set(row.metadata["history_version"] for row in new_rows) == {WEATHER_HISTORY_VERSION + 1}
    corrected = summary_services.stored_history_rows(cell_key=FIRST_CELL, assessment_date=next_day)
    assert len(corrected) == 30
    assert {row.metadata["history_version"] for row in corrected.values()} == {WEATHER_HISTORY_VERSION + 1}


def test_failed_run_can_be_started_again_after_the_batch_is_reopened(forest) -> None:
    clock = _clock()
    refusing = _Transport(clock=clock, override=lambda query: (400, {}, b"not allowed"))
    run = _drive(run=_start(forest=forest, clock=clock), clock=clock, transport=refusing)
    assert run.status == ScheduledWeatherRun.Status.FAILED
    failed = WeatherFetchBatch.objects.filter(scheduled_run=run, status=WeatherFetchBatch.Status.FAILED)
    assert failed.count() == 4
    weather_services.reopen_weather_fetch(batch_id=failed.first().id, now=clock.now)

    restarted = _start(forest=forest, clock=clock)
    assert restarted.id == run.id
    assert restarted.status == ScheduledWeatherRun.Status.PENDING
    finished = _drive(run=restarted, clock=clock, transport=_Transport(clock=clock))

    assert finished.status == ScheduledWeatherRun.Status.COMPLETED


# Retention


def test_cleanup_keeps_history_rows_and_referenced_snapshots(forest) -> None:
    clock = _clock()
    _drive(run=_start(forest=forest, clock=clock), clock=clock, transport=_Transport(clock=clock))
    snapshots_before = set(WeatherSnapshot.objects.values_list("id", flat=True))
    history_before = set(
        WeatherDaily.objects.filter(source_endpoint=ARCHIVE_URL).values_list("id", flat=True)
    )
    old_history = _daily(cell_key=FIRST_CELL, day=DAY - timedelta(days=400), endpoint=ARCHIVE_URL)
    old_forecast = _daily(cell_key=FIRST_CELL, day=DAY - timedelta(days=400), endpoint=FORECAST_URL)
    unused_version = _daily(
        cell_key=FIRST_CELL,
        day=DAY - timedelta(days=5),
        endpoint=ARCHIVE_URL,
        metadata={"history_version": 0},
    )

    result = weather_services.cleanup_weather(cleanup_date=DAY + timedelta(days=90))

    assert result["deleted_daily_count"] >= 1
    assert not WeatherDaily.objects.filter(id=old_forecast.id).exists()
    assert WeatherDaily.objects.filter(id__in=[old_history.id, unused_version.id]).count() == 2
    assert history_before <= set(WeatherDaily.objects.values_list("id", flat=True))
    assert snapshots_before == set(WeatherSnapshot.objects.values_list("id", flat=True))
    snapshot = WeatherSnapshot.objects.get(cell_key=FIRST_CELL, assessment_date=DAY)
    assert snapshot.days.count() == 38
