import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ...services import build_national_grid
from ...source import ARCHIVE_SHA256


class Command(BaseCommand):
    """Build or resume the local ISTAT national grid."""

    help = "Build or resume the 500 m national grid from an ISTAT boundary ZIP."

    def add_arguments(self, parser) -> None:
        parser.add_argument("archive", type=Path)
        parser.add_argument("--build-version", required=True)
        parser.add_argument("--expected-sha256", default=ARCHIVE_SHA256)
        parser.add_argument("--downloaded-on", required=True)
        parser.add_argument("--chunk-size-m", type=int, default=25_000)
        parser.add_argument(
            "--stop-after-chunks",
            "--max-chunks",
            dest="max_chunks",
            type=int,
            default=None,
        )
        parser.add_argument("--progress", action="store_true")

    def handle(self, *args, **options) -> None:
        try:
            result = build_national_grid(
                archive_path=options["archive"],
                build_version=options["build_version"],
                expected_sha256=options["expected_sha256"],
                downloaded_on=options["downloaded_on"],
                chunk_size_m=options["chunk_size_m"],
                max_chunks=options["max_chunks"],
                progress_callback=self._write_progress if options["progress"] else None,
            )
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result.as_dict(), sort_keys=True))

    def _write_progress(self, event: dict[str, object]) -> None:
        self.stdout.write(json.dumps(event, sort_keys=True), ending="\n")
