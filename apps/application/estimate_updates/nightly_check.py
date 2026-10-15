"""Check that today's Tuscany forecast run is published, and retry the step that stopped."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.db import transaction
from django_tasks_db.models import DBTaskResult

from weather_on_demand.models import ScheduledWeatherRun, WeatherFetchBatch
from weather_on_demand.services import reopen_weather_fetch, start_scheduled_weather_run
from weather_requests.eligibility import TUSCANY_ISTAT_CODE

from .models import ForecastRun
from .tasks import queue_tuscany_forecast

logger = logging.getLogger(__name__)

PUBLISHED = "published"
NO_WEATHER_RUN = "no_weather_run"
WEATHER_FAILED = "weather_failed"
FORECAST_FAILED = "forecast_failed"
NOT_FINISHED = "not_finished"

_TRACEBACK_LINES = 8


@dataclass(frozen=True)
class NightlyCheckResult:
    """Hold the reason code and the plain message for one date."""

    reason: str
    message: str

    @property
    def is_published(self) -> bool:
        return self.reason == PUBLISHED


def _task_row(*, run: ScheduledWeatherRun) -> DBTaskResult | None:
    if run.forecast_task_id is None:
        return None
    return DBTaskResult.objects.filter(id=run.forecast_task_id).first()


def _forecast_failure_message(*, run: ScheduledWeatherRun, task: DBTaskResult | None, failed: ForecastRun | None) -> str:
    parts = ["The weather was ready, but the forecast run failed."]
    if run.reason_code == "forecast_queue_failure":
        parts.append(f"The forecast task could not be queued: {run.full_reason}")
    if failed is not None and failed.failure_reason:
        parts.append(f"Forecast run reason: {failed.failure_reason}")
    if task is not None and task.status == "FAILED":
        tail = "\n".join(str(task.traceback or "").strip().splitlines()[-_TRACEBACK_LINES:])
        parts.append(f"Task error: {task.exception_class_path}\n{tail}".rstrip())
    return "\n".join(parts)


def check_nightly_update(*, assessment_date: date, region_code: str = TUSCANY_ISTAT_CODE) -> NightlyCheckResult:
    """Read the stored run states and say whether the forecast run is published.

    The reason code names the step that stopped when it is not.
    """
    if ForecastRun.objects.filter(
        region_code=region_code,
        assessment_date=assessment_date,
        status=ForecastRun.Status.PUBLISHED,
    ).exists():
        return NightlyCheckResult(reason=PUBLISHED, message=f"The {assessment_date} forecast run is published.")
    run = ScheduledWeatherRun.objects.filter(region_code=region_code, assessment_date=assessment_date).first()
    if run is None:
        return NightlyCheckResult(
            reason=NO_WEATHER_RUN,
            message=(
                f"No weather run was started for {assessment_date}. "
                "The worker or the cron job is probably down."
            ),
        )
    if run.status == ScheduledWeatherRun.Status.FAILED:
        return NightlyCheckResult(
            reason=WEATHER_FAILED,
            message=(
                f"The weather run for {assessment_date} failed.\n"
                f"Reason code: {run.reason_code}\n"
                f"Full reason: {run.full_reason}"
            ),
        )
    if run.status != ScheduledWeatherRun.Status.COMPLETED:
        return NightlyCheckResult(
            reason=NOT_FINISHED,
            message=f"The weather run for {assessment_date} is still {run.status}.",
        )
    task = _task_row(run=run)
    # A retried task is still waiting while the earlier failed ForecastRun row exists.
    if task is not None and task.status in {"READY", "RUNNING"}:
        return NightlyCheckResult(
            reason=NOT_FINISHED,
            message=f"The weather run is completed and the forecast task is still {task.status}.",
        )
    failed = ForecastRun.objects.filter(
        region_code=region_code,
        assessment_date=assessment_date,
        status=ForecastRun.Status.FAILED,
    ).first()
    if (
        run.reason_code == "forecast_queue_failure"
        or (task is not None and task.status == "FAILED")
        or failed is not None
    ):
        return NightlyCheckResult(
            reason=FORECAST_FAILED,
            message=_forecast_failure_message(run=run, task=task, failed=failed),
        )
    return NightlyCheckResult(
        reason=NOT_FINISHED,
        message=f"The weather run is completed, but the {assessment_date} forecast run is not published yet.",
    )


def _requeue_forecast(*, run_id: uuid.UUID, assessment_date: date, region_code: str) -> None:
    """Queue a new forecast task for a completed run and store its ID."""
    with transaction.atomic():
        run = ScheduledWeatherRun.objects.select_for_update().get(id=run_id)
        run.forecast_task_id = queue_tuscany_forecast(region_code=region_code, assessment_date=assessment_date)
        if run.reason_code == "forecast_queue_failure":
            run.reason_code = "ready"
            run.full_reason = ""
        run.save(update_fields=["forecast_task_id", "reason_code", "full_reason", "updated_at"])


def retry_nightly_update(
    *,
    assessment_date: date,
    region_code: str = TUSCANY_ISTAT_CODE,
) -> NightlyCheckResult:
    """Retry the step that stopped and return the state found before the retry.

    It never sends an email.
    """
    result = check_nightly_update(assessment_date=assessment_date, region_code=region_code)
    if result.is_published:
        logger.info("Nightly retry for %s: the run is published, nothing to retry.", assessment_date)
        return result

    def start() -> None:
        start_scheduled_weather_run(
            assessment_date=assessment_date,
            region_code=region_code,
            forest_build_version=settings.SPORAMETEO_FOREST_BUILD_VERSION,
        )

    run = ScheduledWeatherRun.objects.filter(region_code=region_code, assessment_date=assessment_date).first()
    if result.reason == NO_WEATHER_RUN:
        start()
        action = "started the weather run"
    elif result.reason == WEATHER_FAILED:
        reopened = 0
        failed_ids = list(
            WeatherFetchBatch.objects.filter(
                scheduled_run=run,
                status=WeatherFetchBatch.Status.FAILED,
            ).values_list("id", flat=True)
        )
        for batch_id in failed_ids:
            # Reopening one batch also reopens its sibling batches, so check the status again.
            if WeatherFetchBatch.objects.get(id=batch_id).status == WeatherFetchBatch.Status.FAILED:
                reopen_weather_fetch(batch_id=batch_id)
                reopened += 1
        start()
        action = f"reopened {reopened} failed weather batches and resumed the weather run"
    elif result.reason == FORECAST_FAILED:
        _requeue_forecast(run_id=run.id, assessment_date=assessment_date, region_code=region_code)
        action = "queued a new forecast task"
    elif run.status != ScheduledWeatherRun.Status.COMPLETED:
        start()
        action = "resumed the weather run"
    elif run.forecast_task_id is None:
        start()
        action = "queued the missing forecast task"
    else:
        action = "nothing, the forecast task is still running"
    logger.info("Nightly retry for %s (%s): %s.", assessment_date, result.reason, action)
    return result
