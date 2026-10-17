from __future__ import annotations

import uuid
from datetime import date

from django.tasks import task

from .services import process_estimate_task


@task
def estimate_update_task(*, job_id: str) -> str:
    """Run one durable estimate calculation without weather access."""
    result = process_estimate_task(task_id=job_id)
    return str(result.update.public_id)


@task
def warm_published_map_cache_task(*, region_code: str) -> int:
    """Prepare the overview of the published run in the shared map cache without any remote access."""
    from map_api.published import warm_published_map_cache

    return warm_published_map_cache(region_code=region_code)["squares"]


@task
def tuscany_forecast_task(*, region_code: str, assessment_date: str) -> str:
    """Calculate and publish the Tuscany forecast run for one date.
    A failed run raises, so the task row shows the failure."""
    from .forecast_runs import ForecastRunError, process_forecast_run, start_forecast_run
    from .models import ForecastRun

    run = start_forecast_run(
        assessment_date=date.fromisoformat(assessment_date),
        region_code=region_code,
    )
    run = process_forecast_run(run_id=run.id)
    if run.status == ForecastRun.Status.FAILED:
        raise ForecastRunError(f"The forecast run {run.id} failed. {run.failure_reason}")
    return str(run.status)


def queue_tuscany_forecast(*, region_code: str, assessment_date: date) -> uuid.UUID:
    """Queue the forecast task for a date and return the task ID."""
    result = tuscany_forecast_task.enqueue(
        region_code=region_code,
        assessment_date=assessment_date.isoformat(),
    )
    return uuid.UUID(str(result.id))
