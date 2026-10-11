import time
import uuid

from django.db import transaction
from django.tasks import task
from django.utils import timezone

from .models import BackgroundJobAttempt, RepresentativeResult
from .services import (
    ActiveBackgroundJobError,
    ControlledRepresentativeFailure,
    StaleBackgroundTaskError,
    _failure_reason,
    _mark_attempt_completed,
    _mark_attempt_failed,
    logical_job_lock,
)


@task
def representative_job_task(*, attempt_id: str) -> int:
    """Run the deterministic representative job for one persisted attempt."""

    parsed_attempt_id = uuid.UUID(attempt_id)
    attempt = (
        BackgroundJobAttempt.objects.select_related("job", "job__input")
        .get(id=parsed_attempt_id)
    )

    with logical_job_lock(logical_key=attempt.job.logical_key, wait=False) as acquired:
        if not acquired:
            raise ActiveBackgroundJobError(
                f"Another worker owns logical job {attempt.job.logical_key}."
            )

        with transaction.atomic():
            attempt = (
                BackgroundJobAttempt.objects.select_for_update()
                .select_related("job", "job__input")
                .get(id=parsed_attempt_id)
            )
            if attempt.state == BackgroundJobAttempt.State.COMPLETED:
                return RepresentativeResult.objects.get(job_id=attempt.job_id).result_value
            if attempt.state == BackgroundJobAttempt.State.FAILED:
                raise StaleBackgroundTaskError(
                    f"Attempt {attempt.id} is already failed."
                )
            if attempt.state == BackgroundJobAttempt.State.RUNNING:
                raise ActiveBackgroundJobError(
                    f"Attempt {attempt.id} is already running."
                )

            attempt.state = BackgroundJobAttempt.State.RUNNING
            attempt.started_at = timezone.now()
            attempt.save(update_fields=["state", "started_at"])
            representative_input = attempt.job.input

        try:
            if representative_input.delay_seconds:
                time.sleep(representative_input.delay_seconds)
            if representative_input.fail_first_attempt and attempt.attempt_number == 1:
                raise ControlledRepresentativeFailure(
                    "Forced failure for the first representative attempt."
                )
            result_value = representative_input.value * 2
            return _mark_attempt_completed(
                attempt_id=parsed_attempt_id,
                result_value=result_value,
            )
        except Exception as exc:
            _mark_attempt_failed(
                attempt_id=parsed_attempt_id,
                reason=_failure_reason(exc),
            )
            raise
