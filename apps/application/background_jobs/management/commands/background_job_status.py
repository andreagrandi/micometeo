import uuid
from argparse import ArgumentParser
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from background_jobs.models import BackgroundJob, BackgroundJobAttempt


def _identifier(value: str) -> uuid.UUID | str:
    try:
        return uuid.UUID(value)
    except ValueError:
        return value


class Command(BaseCommand):
    help = "Show the persisted state of a background job attempt."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("identifier", type=_identifier)

    def handle(self, *, identifier: uuid.UUID | str, **options) -> None:
        attempt = None
        if isinstance(identifier, uuid.UUID):
            attempt = (
                BackgroundJobAttempt.objects.select_related("job")
                .filter(id=identifier)
                .first()
            )
            if attempt is None:
                job = BackgroundJob.objects.filter(id=identifier).first()
                if job is not None:
                    attempt = job.attempts.select_related("job").order_by("-attempt_number").first()
        else:
            attempt = (
                BackgroundJobAttempt.objects.select_related("job")
                .filter(job__logical_key=identifier)
                .order_by("-attempt_number")
                .first()
            )
        if attempt is None:
            raise CommandError("No background job attempt matched that identifier.")

        self.stdout.write(f"job_id={attempt.job_id}")
        self.stdout.write(f"attempt_id={attempt.id}")
        self.stdout.write(f"attempt_number={attempt.attempt_number}")
        self.stdout.write(f"state={attempt.state}")
        self.stdout.write(f"queued_at={attempt.queued_at.isoformat()}")
        self.stdout.write(f"started_at={_format_time(attempt.started_at)}")
        self.stdout.write(f"ended_at={_format_time(attempt.ended_at)}")
        self.stdout.write(f"task_id={attempt.task_id}")
        self.stdout.write(f"retry_of={attempt.retry_of_id}")
        self.stdout.write(f"failure_reason={attempt.failure_reason}")


def _format_time(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""
