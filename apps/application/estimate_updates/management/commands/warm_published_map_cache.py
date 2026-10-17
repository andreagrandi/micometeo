"""Fill the shared map cache for the published Tuscany run."""

from argparse import ArgumentParser

from django.core.management.base import BaseCommand, CommandError

from map_api.published import MapCacheError, warm_published_map_cache
from weather_requests.eligibility import TUSCANY_ISTAT_CODE


class Command(BaseCommand):
    help = "Build the square and result tiles of the published Tuscany run into the map cache."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--region-code", default=TUSCANY_ISTAT_CODE, help="Only 09, Tuscany, is allowed.")

    def handle(self, *args, **options) -> None:
        try:
            counts = warm_published_map_cache(region_code=options["region_code"])
        except MapCacheError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Prepared the overview of {counts["squares"]} squares of the published run")
