import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ...services import build_national_forest


class Command(BaseCommand):
    """Build or resume the national forest account."""

    help = "Build or resume forest values from the Copernicus HRL Forest Type 2018 map."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--grid-build-version", required=True)
        parser.add_argument("--build-version", required=True)
        parser.add_argument("--cache-dir", type=Path, required=True)
        parser.add_argument("--output-dir", type=Path, required=True)
        parser.add_argument("--max-source-chunk-m", type=int, default=40_000)
        parser.add_argument("--max-chunks", type=int, default=None)
        parser.add_argument("--output-format", choices=["jsonl"], default="jsonl")

    def handle(self, *args, **options) -> None:
        try:
            result = build_national_forest(
                grid_build_version=options["grid_build_version"],
                build_version=options["build_version"],
                cache_dir=options["cache_dir"],
                output_dir=options["output_dir"],
                max_source_chunk_m=options["max_source_chunk_m"],
                max_chunks=options["max_chunks"],
                output_format=options["output_format"],
            )
        except (ValueError, OSError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result.as_dict(), sort_keys=True))
