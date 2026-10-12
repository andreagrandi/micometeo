import json
from argparse import ArgumentParser
from datetime import date

from django.core.management.base import BaseCommand

from ...services import weather_status


class Command(BaseCommand):
    """Print durable weather fetch and cleanup status."""

    help = "Report on-demand weather fetches, provider calls and cleanup."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--assessment-date", type=date.fromisoformat, default=None)

    def handle(self, *args, **options) -> None:
        self.stdout.write(
            json.dumps(
                weather_status(assessment_date=options["assessment_date"]),
                sort_keys=True,
            )
        )
