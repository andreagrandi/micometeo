"""Prepare the JRC files used by local estimate workers."""

import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from micometeo.host_trees import prepare_sources


class Command(BaseCommand):
    help = "Download and verify JRC files once, without populating national grid values."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--directory", default=settings.MICOMETEO_JRC_DIRECTORY)

    def handle(self, *args, **options) -> None:
        started = time.monotonic()
        try:
            manifest = prepare_sources(directory=Path(options["directory"]))
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"Prepared {len(manifest['files'])} JRC species in {time.monotonic() - started:.2f} seconds. "
            "No national grid rows were populated."
        )
