import json

from django.core.management.base import BaseCommand, CommandError

from ...lookups import lookup_national_grid


class Command(BaseCommand):
    """Look up one completed national-grid cell."""

    help = "Look up a national-grid cell by ID or WGS84 coordinates."

    def add_arguments(self, parser) -> None:
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--cell-id")
        group.add_argument("--latitude", type=float)
        parser.add_argument("--longitude", type=float)
        parser.add_argument("--build-version")

    def handle(self, *args, **options) -> None:
        if options["cell_id"] is None and options["longitude"] is None:
            raise CommandError("--longitude is required with --latitude.")
        result = lookup_national_grid(
            cell_id=options["cell_id"],
            latitude=options["latitude"],
            longitude=options["longitude"],
            build_version=options["build_version"],
        )
        self.stdout.write(json.dumps(result.as_dict(), sort_keys=True))
