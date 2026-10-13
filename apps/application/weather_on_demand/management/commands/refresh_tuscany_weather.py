"""Plan or start the scheduled Tuscany weather preparation."""

import json
from argparse import ArgumentParser
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from weather_requests.eligibility import TUSCANY_ISTAT_CODE, WeatherEligibilityError, tuscany_weather_cells

from ...services import italian_assessment_date, plan_scheduled_weather, start_scheduled_weather_run


class Command(BaseCommand):
    help = "Print the Tuscany weather plan, or start the paced run that stores 38 days of weather."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--dry-run", action="store_true", help="Print the plan without writing or fetching.")
        parser.add_argument(
            "--assessment-date",
            type=date.fromisoformat,
            default=None,
            help="Italian date to prepare, default today in Europe/Rome.",
        )
        parser.add_argument("--region-code", default=TUSCANY_ISTAT_CODE, help="Only 09, Tuscany, is allowed.")
        parser.add_argument(
            "--forest-build-version",
            default=str(getattr(settings, "MICOMETEO_FOREST_BUILD_VERSION", "")),
            help="Forest build that lists the weather cells, default from the app setting.",
        )
        parser.add_argument("--json", action="store_true", help="Print the plan as JSON.")

    def handle(self, *args, **options) -> None:
        assessment_date = options["assessment_date"] or italian_assessment_date()
        version = options["forest_build_version"]
        if not version:
            raise CommandError("Set MICOMETEO_FOREST_BUILD_VERSION or pass --forest-build-version.")
        try:
            if options["dry_run"]:
                cells = tuscany_weather_cells(
                    forest_build_version=version,
                    region_code=options["region_code"],
                )
                plan = plan_scheduled_weather(
                    cells=cells,
                    assessment_date=assessment_date,
                    forest_build_version=version,
                )
                self._write_plan(plan=plan.as_dict(), as_json=options["json"])
                return
            run = start_scheduled_weather_run(
                assessment_date=assessment_date,
                region_code=options["region_code"],
                forest_build_version=version,
            )
        except (WeatherEligibilityError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"run_id={run.id} status={run.status} mode={run.mode} "
            f"assessment_date={run.assessment_date.isoformat()} "
            f"planned_counted_calls={run.planned_counted_calls} "
            f"planned_http_requests={run.planned_http_requests}"
        )

    def _write_plan(self, *, plan: dict, as_json: bool) -> None:
        if as_json:
            self.stdout.write(json.dumps(plan, indent=2, sort_keys=True))
            return
        self.stdout.write(f"Dry run for {plan['assessment_date']}, no data written")
        self.stdout.write(f"Window: {plan['window_start']} through {plan['window_end']}")
        self.stdout.write(f"Mode: {plan['mode']}")
        self.stdout.write(f"Weather cells: {plan['cells_total']}, already ready for the date: {plan['cells_ready']}")
        self.stdout.write(f"Counted calls: {plan['counted_calls']:g}")
        self.stdout.write(f"HTTP requests: {plan['http_requests']}")
        for part in plan["parts"]:
            self.stdout.write(
                f"  {part['kind']} {part['start_date']} through {part['end_date']}: "
                f"{part['cells']} cells, {part['http_requests']} requests, "
                f"{part['counted_calls']:g} counted calls"
            )
