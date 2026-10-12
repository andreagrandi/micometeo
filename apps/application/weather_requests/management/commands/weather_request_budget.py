import json
from argparse import ArgumentParser

from django.core.management.base import BaseCommand, CommandError

from ...services import budget_for_forest_build


class Command(BaseCommand):
    """Report national and regional weather request accounting without network I/O."""

    help = "Report eligible weather cells and their conservative provider budget."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--forest-build-version", required=True)

    def handle(self, *args, **options) -> None:
        try:
            report = budget_for_forest_build(
                forest_build_version=options["forest_build_version"],
            )
        except (ValueError, OSError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report, sort_keys=True))
