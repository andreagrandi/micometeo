from __future__ import annotations

import uuid

from django.tasks import task

from .services import process_weather_fetch_batch, run_cleanup_job


@task
def weather_fetch_task(*, batch_id: str) -> bool:
    """Run one durable weather fetch batch."""
    return process_weather_fetch_batch(batch_id=uuid.UUID(batch_id))


@task
def weather_cleanup_task(*, job_id: str) -> dict[str, int | str]:
    """Run one weather retention task without network access."""
    return run_cleanup_job(job_id=uuid.UUID(job_id))
