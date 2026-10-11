import uuid
from argparse import ArgumentParser, ArgumentTypeError

from django.core.management.base import BaseCommand, CommandError

from background_jobs.services import BackgroundJobError, retry_background_job


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ArgumentTypeError("Enter a valid attempt UUID.") from exc


class Command(BaseCommand):
    help = "Queue an explicit retry for a failed background job attempt."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("attempt_id", type=_uuid)

    def handle(self, *, attempt_id: uuid.UUID, **options) -> None:
        try:
            attempt = retry_background_job(attempt_id=attempt_id)
        except BackgroundJobError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"job_id={attempt.job_id}")
        self.stdout.write(f"attempt_id={attempt.id}")
        self.stdout.write(f"task_id={attempt.task_id}")
        self.stdout.write(f"retry_of={attempt.retry_of_id}")
        self.stdout.write(f"state={attempt.state}")
