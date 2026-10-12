import json
from argparse import ArgumentParser
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ...services import check_weather_response


class Command(BaseCommand):
    """Check one real provider response for no more than one hundred cells."""

    help = "Fetch and validate one small weather response, preserving metadata only in the report."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--forest-build-version", required=True)
        parser.add_argument("--assessment-date", required=True, type=date.fromisoformat)
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--cache-dir", type=Path, default=None)

    def handle(self, *args, **options) -> None:
        try:
            report = check_weather_response(
                forest_build_version=options["forest_build_version"],
                assessment_date=options["assessment_date"],
                limit=options["limit"],
                cache_dir=options["cache_dir"],
            )
        except (ValueError, OSError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report, sort_keys=True))
