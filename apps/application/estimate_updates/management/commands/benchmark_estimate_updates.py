from __future__ import annotations

import json
from argparse import ArgumentParser
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from ...benchmark import benchmark_estimate_updates
from ...services import _terrain_build_version


class Command(BaseCommand):
    """Measure estimates using synthetic weather in a disposable database."""

    help = "Benchmark estimate calculation and storage without HTTP requests."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--forest-build-version", required=True)
        parser.add_argument("--terrain-build-version", default=None)
        parser.add_argument("--assessment-date", required=True, type=date.fromisoformat)
        group = parser.add_mutually_exclusive_group(required=False)
        group.add_argument("--cell")
        group.add_argument("--national", action="store_true")

    def handle(self, *args, **options) -> None:
        try:
            terrain_version = options["terrain_build_version"] or _terrain_build_version()
            if not options["cell"] and not options["national"]:
                raise CommandError("Choose --cell or --national.")
            report = benchmark_estimate_updates(
                forest_build_version=options["forest_build_version"],
                terrain_build_version=terrain_version,
                assessment_date=options["assessment_date"],
                cell_key=options["cell"],
            )
        except CommandError:
            raise
        except (ValueError, OSError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report, sort_keys=True))
