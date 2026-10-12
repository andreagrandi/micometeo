from __future__ import annotations

from django.tasks import task

from .services import process_estimate_task


@task
def estimate_update_task(*, job_id: str) -> str:
    """Run one durable estimate calculation without weather access."""
    result = process_estimate_task(task_id=job_id)
    return str(result.update.public_id)
