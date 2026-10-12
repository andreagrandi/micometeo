from argparse import ArgumentParser
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from ...services import enqueue_cleanup


class Command(BaseCommand):
    """Queue one idempotent weather cleanup task."""

    help = "Queue weather retention cleanup without making provider requests."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--cleanup-date", type=date.fromisoformat, default=None)
        parser.add_argument("--protected-snapshot-id", action="append", default=[])

    def handle(self, *args, **options) -> None:
        try:
            job = enqueue_cleanup(
                cleanup_date=options["cleanup_date"],
                protected_snapshot_ids=options["protected_snapshot_id"],
            )
        except (ValueError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"cleanup_date={job.cleanup_date.isoformat()} status={job.status} task_id={job.task_id}"
        )
