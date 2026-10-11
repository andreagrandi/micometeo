import uuid
from argparse import ArgumentParser, ArgumentTypeError
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from background_jobs.services import (
    FailedBackgroundJobError,
    default_logical_key,
    enqueue_representative_job,
)


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ArgumentTypeError("Enter a valid input UUID.") from exc


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ArgumentTypeError("Enter a job date as YYYY-MM-DD.") from exc


class Command(BaseCommand):
    help = "Queue the deterministic representative background job."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("input_id", type=_uuid)
        parser.add_argument(
            "--job-date",
            type=_date,
            default=None,
            help="Europe/Rome job date. The local date is used by default.",
        )
        parser.add_argument(
            "--logical-key",
            default=None,
            help="Use a specific logical key instead of the date-based key.",
        )

    def handle(
        self,
        *,
        input_id: uuid.UUID,
        job_date: date | None,
        logical_key: str | None,
        **options,
    ) -> None:
        selected_date = job_date or timezone.localdate()
        selected_key = logical_key or default_logical_key(
            input_id=input_id,
            job_date=selected_date,
        )
        try:
            attempt = enqueue_representative_job(
                input_id=input_id,
                logical_key=selected_key,
            )
        except FailedBackgroundJobError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"job_id={attempt.job_id}")
        self.stdout.write(f"attempt_id={attempt.id}")
        self.stdout.write(f"task_id={attempt.task_id}")
        self.stdout.write(f"logical_key={attempt.job.logical_key}")
        self.stdout.write(f"state={attempt.state}")
