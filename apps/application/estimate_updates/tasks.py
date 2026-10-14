from __future__ import annotations

from django.tasks import task

from .services import process_estimate_task


@task
def estimate_update_task(*, job_id: str) -> str:
    """Run one durable estimate calculation without weather access."""
    result = process_estimate_task(task_id=job_id)
    return str(result.update.public_id)


@task
def warm_published_map_cache_task(*, region_code: str) -> int:
    """Fill the shared map cache for the published run without any remote access."""
    from map_api.published import warm_published_map_cache

    return warm_published_map_cache(region_code=region_code)["tiles"]
