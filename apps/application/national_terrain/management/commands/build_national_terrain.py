"""Build terrain values for every cell in a completed national grid."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from national_terrain.services import build_national_terrain


class Command(BaseCommand):
    """Run one resumable national terrain build."""

    help = "Build or resume bounded terrain chunks for a completed national grid."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--grid-build-version", required=True)
        parser.add_argument("--build-version", required=True)
        parser.add_argument("--cache-dir", required=True, type=Path)
        parser.add_argument("--max-chunks", type=int, default=None)

    def handle(self, *args, **options) -> None:
        max_chunks = options["max_chunks"]
        if max_chunks is not None and max_chunks <= 0:
            raise CommandError("--max-chunks must be positive.")

        def report(event: dict) -> None:
            self.stdout.write(json.dumps(event, sort_keys=True), ending="\n")
            self.stdout.flush()

        try:
            result = build_national_terrain(
                grid_build_version=options["grid_build_version"],
                build_version=options["build_version"],
                cache_dir=options["cache_dir"],
                max_chunks=max_chunks,
                progress_callback=report,
            )
        except (ValueError, OSError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
        output = result.as_dict()
        output["status"] = result.status
        self.stdout.write(json.dumps(output, sort_keys=True), ending="\n")
        self.stdout.flush()
