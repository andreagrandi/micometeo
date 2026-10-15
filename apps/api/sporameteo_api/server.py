"""HTTP handling for the demo API, built on the standard library."""

import gzip
import json
import math
import re
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from sporameteo_api import demo

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ApiError(Exception):
    """An error that becomes a JSON response with a plain sentence."""

    def __init__(self, status: int, message: str) -> None:
        """Store the status code and the message."""
        super().__init__(message)
        self.status = status
        self.message = message


class DemoServer(ThreadingHTTPServer):
    """Threaded server that holds the grid and a function for today's date."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        today: Callable[[], date] = demo.today_in_rome,
        quiet: bool = False,
    ) -> None:
        """Load the grid and set up the handler."""
        super().__init__(address, Handler)
        self.today = today
        self.quiet = quiet
        self.box, self.squares = demo.load_grid(path=demo.GRID_PATH)


def parse_date(value: str, name: str) -> date:
    """Read a YYYY-MM-DD date or raise a plain error."""
    if not DATE_PATTERN.match(value):
        raise ApiError(status=400, message=f"The parameter {name} must look like 2026-10-11.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ApiError(status=400, message=f"The parameter {name} is not a real date.") from None


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    """Read west,south,east,north or raise a plain error."""
    message = "The parameter bbox must be four numbers: west,south,east,north."
    parts = value.split(",")
    if len(parts) != 4:
        raise ApiError(status=400, message=message)
    try:
        west, south, east, north = (float(part) for part in parts)
    except ValueError:
        raise ApiError(status=400, message=message) from None
    if not all(math.isfinite(number) for number in (west, south, east, north)):
        raise ApiError(status=400, message=message)
    if west >= east or south >= north:
        raise ApiError(status=400, message="The parameter bbox needs west smaller than east and south smaller than north."
        )
    return west, south, east, north


class Handler(BaseHTTPRequestHandler):
    """Answer the demo API requests."""

    server: DemoServer
    server_version = "SporaMeteoDemoApi"

    def log_message(self, format: str, *args: Any) -> None:
        """Write one short line per request to stderr."""
        if not self.server.quiet:
            sys.stderr.write(f"{self.command} {self.path} {args[1] if len(args) > 1 else ''}\n")

    def _send(self, status: int, body: dict[str, Any] | None, cache: bool = False) -> None:
        """Send a JSON body, gzipped if the client accepts it."""
        self.send_response(status)
        self.send_header("X-Demo-Data", "true")
        self.send_header("Access-Control-Allow-Origin", "*")
        if body is None:
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        payload = {"demo_data": True, "notice": demo.NOTICE, **body}
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Vary", "Accept-Encoding")
        if cache:
            self.send_header("Cache-Control", "public, max-age=300")
        if "gzip" in self.headers.get("Accept-Encoding", "").lower():
            data = gzip.compress(data, compresslevel=6)
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _error(self, status: int, message: str) -> None:
        """Send an error body."""
        self._send(status=status, body={"error": message})

    def do_GET(self) -> None:
        """Route a GET request."""
        parts = urlsplit(self.path)
        try:
            if parts.path == "/api/v1/health":
                self._send(status=200, body={"status": "ok"})
            elif parts.path == "/api/v1/info":
                self._send(status=200, body=self._info(), cache=True)
            elif parts.path == "/api/v1/squares":
                self._send(
                    status=200,
                    body=self._squares(query=parse_qs(parts.query)),
                    cache=True,
                )
            else:
                raise ApiError(status=404, message="This address does not exist.")
        except ApiError as error:
            self._error(status=error.status, message=error.message)

    def do_OPTIONS(self) -> None:
        """Answer a CORS preflight request."""
        self._send(status=204, body=None)

    def _not_allowed(self) -> None:
        """Answer methods other than GET and OPTIONS."""
        self.send_response(405)
        self.send_header("Allow", "GET, OPTIONS")
        self.send_header("X-Demo-Data", "true")
        self.send_header("Access-Control-Allow-Origin", "*")
        data = json.dumps(
            {"demo_data": True, "notice": demo.NOTICE, "error": "Only GET is allowed."},
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_POST = do_PUT = do_DELETE = do_PATCH = _not_allowed

    def _info(self) -> dict[str, Any]:
        """Build the info body."""
        today = self.server.today()
        return {
            "species": demo.SPECIES,
            "assessment_dates": [
                day.isoformat() for day in demo.assessment_dates(today=today)
            ],
            "max_days_ahead": demo.MAX_DAYS_AHEAD,
            "area": self.server.box,
            "max_squares_per_request": demo.MAX_SQUARES_PER_REQUEST,
            "min_zoom": demo.MIN_ZOOM,
        }

    def _squares(self, query: dict[str, list[str]]) -> dict[str, Any]:
        """Validate the query and build the GeoJSON body."""
        values = {}
        for name in ("species", "assessment_date", "target_date", "bbox"):
            if not query.get(name) or not query[name][0]:
                raise ApiError(status=400, message=f"The parameter {name} is required.")
            values[name] = query[name][0]
        species = values["species"]
        if species not in demo.SPECIES_IDS:
            raise ApiError(status=400, message=f"Unknown species. Use one of: {', '.join(demo.SPECIES_IDS)}."
            )
        assessment = parse_date(value=values["assessment_date"], name="assessment_date")
        target = parse_date(value=values["target_date"], name="target_date")
        available = demo.assessment_dates(today=self.server.today())
        if assessment not in available:
            raise ApiError(status=400, message="The assessment_date is not available. Use a day from "
                f"{available[-1].isoformat()} to {available[0].isoformat()}.",
            )
        days_ahead = (target - assessment).days
        if days_ahead < 0:
            raise ApiError(status=400, message="The target_date cannot be before the assessment_date.")
        if days_ahead > demo.MAX_DAYS_AHEAD:
            raise ApiError(status=400, message=f"The target_date can be at most {demo.MAX_DAYS_AHEAD} days after the assessment_date.",
            )
        west, south, east, north = parse_bbox(value=values["bbox"])
        matches = demo.find_squares(
            squares=self.server.squares, west=west, south=south, east=east, north=north
        )
        if len(matches) > demo.MAX_SQUARES_PER_REQUEST:
            raise ApiError(status=400, message=f"The bbox covers {len(matches)} squares and the limit is "
                f"{demo.MAX_SQUARES_PER_REQUEST}. Zoom in and try again.",
            )
        features = [
            demo.build_feature(
                square=square, species=species, assessment=assessment, target=target
            ) for square in matches
        ]
        return {
            "type": "FeatureCollection",
            "species": species,
            "assessment_date": assessment.isoformat(),
            "target_date": target.isoformat(),
            "days_ahead": days_ahead,
            "square_count": len(features),
            "features": features,
        }


def run(host: str, port: int) -> None:
    """Serve until interrupted."""
    server = DemoServer(address=(host, port))
    print(f"Demo API on http://{host}:{server.server_address[1]}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
