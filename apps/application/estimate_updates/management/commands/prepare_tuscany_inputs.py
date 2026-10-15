"""Check and prepare the stored Tuscany inputs before estimates run."""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from estimate_updates.tuscany_inputs import SourceStatus, TuscanyReport, prepare_tuscany_inputs


DEFAULT_TERRAIN_CACHE = Path(settings.BASE_DIR).parent.parent / "data/raw/mvp_terrain"


class Command(BaseCommand):
    help = "Report Tuscany input readiness and store host-tree values for every forest square."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--dry-run", action="store_true", help="Print the inventory without writing or downloading.")
        parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
        parser.add_argument(
            "--allow-forest-only", action="store_true",
            help="Accept missing JRC files and let estimates use forest only.",
        )
        parser.add_argument(
            "--skip-source-files", action="store_true",
            help="Do not check the forest source files and terrain tiles. Use this on a server that only runs the app.",
        )
        parser.add_argument("--terrain-cache-dir", type=Path, default=DEFAULT_TERRAIN_CACHE)

    def handle(self, *args, **options) -> None:
        try:
            report = prepare_tuscany_inputs(
                terrain_cache_dir=options["terrain_cache_dir"], dry_run=options["dry_run"],
                allow_forest_only=options["allow_forest_only"],
                check_source_files=not options["skip_source_files"],
            )
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        if options["json"]:
            self.stdout.write(json.dumps(report.as_dict(), indent=2, sort_keys=True))
        else:
            self._write_text(report=report)
        if report.failures and not options["dry_run"]:
            raise CommandError(
                "Tuscany inputs are not ready: "
                + "; ".join(f"{item.source} is {item.state}" for item in report.failures)
            )

    def _write_text(self, *, report: TuscanyReport) -> None:
        mode = "Dry run" if report.dry_run else "Preparation"
        self.stdout.write(f"{mode} for region {report.region_code}")
        for item in report.sources:
            self._write_source(item=item)
        counts = ", ".join(f"{key}={value}" for key, value in report.counts.items())
        self.stdout.write(f"Counts: {counts}")
        self.stdout.write(f"Elapsed: {report.elapsed_seconds:.2f} seconds")

    def _write_source(self, *, item: SourceStatus) -> None:
        self.stdout.write(f"{item.source}: {item.state}, version {item.version or 'none'}")
        for line in item.detail:
            self.stdout.write(f"  area: {line}")
        if item.counts:
            self.stdout.write("  counts: " + ", ".join(f"{key}={value}" for key, value in item.counts.items()))
        self.stdout.write(f"  action: {item.action}")
