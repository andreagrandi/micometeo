"""Measure map response sizes and database timings from a benchmark database."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use YYYY-MM-DD for the assessment date.") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure three saved map views without making weather requests."
    )
    parser.add_argument("--database-name", required=True)
    parser.add_argument("--assessment-date", required=True, type=_parse_date)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def _load_django(*, database_name: str) -> None:
    root = Path(__file__).resolve().parents[2]
    application = root / "apps" / "application"
    if str(application) not in sys.path:
        sys.path.insert(0, str(application))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    os.environ["SPORAMETEO_DB_NAME"] = database_name

    import django

    django.setup()


def _response_body(response: Any) -> tuple[dict[str, Any], bytes]:
    raw = response.content
    if response.get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    return json.loads(s=raw), raw


def _stored_weather(*, assessment: date, cells: Sequence[Any]) -> SimpleNamespace:
    from weather_summaries.models import WeatherSnapshot

    rows = WeatherSnapshot.objects.filter(
        assessment_date=assessment,
        status=WeatherSnapshot.Status.READY,
        cell_key__in=[cell.key for cell in cells],
    )
    by_cell = {row.cell_key: row for row in rows}
    missing = sorted({cell.key for cell in cells} - set(by_cell))
    if missing:
        raise RuntimeError(
            "Missing ready weather snapshots for the exact assessment date: "
            + ", ".join(missing)
        )
    return SimpleNamespace(
        by_cell={
            cell.key: SimpleNamespace(
                state="ready",
                snapshot_id=by_cell[cell.key].id,
                assessment_date=assessment,
            )
            for cell in cells
        }
    )


def main() -> None:
    """Measure response sizes and timings for three fixed map views."""
    args = _parser().parse_args()
    if "estimate_benchmark" not in args.database_name:
        raise SystemExit(
            "The response measurement needs an estimate benchmark database name."
        )
    _load_django(database_name=args.database_name)

    from django.core.cache import cache
    from django.db import connection
    from django.test import Client, override_settings
    from django.test.utils import CaptureQueriesContext
    from map_api.api import GEOD, _bbox_size_m
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    weather_calls = 0

    def stored_weather(*, cells: Sequence[Any], **_kwargs: Any) -> SimpleNamespace:
        nonlocal weather_calls
        weather_calls += 1
        return _stored_weather(
            assessment=args.assessment_date,
            cells=cells,
        )

    views = (
        ("northern_apennines", 10.6, 44.15),
        ("alps", 11.5, 46.15),
        ("calabria", 16.4, 39.1),
    )
    with override_settings(ALLOWED_HOSTS=["testserver"]), patch(
        "map_api.api._today", return_value=args.assessment_date
    ), patch(
        "map_api.api.weather_services.request_weather", side_effect=stored_weather
    ):
        client = Client()
        for name, longitude, latitude in views:
            west, _, _ = GEOD.fwd(longitude, latitude, 270, 29600)
            east, _, _ = GEOD.fwd(longitude, latitude, 90, 29600)
            _, south, _ = GEOD.fwd(longitude, latitude, 180, 29600)
            _, north, _ = GEOD.fwd(longitude, latitude, 0, 29600)
            bbox = (west, south, east, north)
            width, height = _bbox_size_m(bbox=bbox)
            if width >= 60000 or height >= 60000:
                raise RuntimeError(f"The {name} view exceeds the 60 km map limit.")
            cache.clear()
            samples: list[dict[str, object]] = []
            body: dict[str, object] | None = None
            raw = b""
            for _ in range(3):
                before = time.perf_counter()
                with CaptureQueriesContext(connection) as queries:
                    response = client.get(
                        "/api/v1/squares",
                        {
                            "bbox": ",".join(str(value) for value in bbox),
                            "target_date": args.assessment_date.isoformat(),
                        },
                        HTTP_ACCEPT_ENCODING="gzip",
                    )
                elapsed = time.perf_counter() - before
                if response.status_code != 200:
                    raise RuntimeError(
                        f"The {name} view returned HTTP {response.status_code}: "
                        f"{response.content[:500]!r}"
                    )
                body, raw = _response_body(response)
                samples.append(
                    {
                        "seconds": round(elapsed, 4),
                        "queries": len(queries),
                        "database_seconds": round(
                            sum(float(query["time"]) for query in queries), 4
                        ),
                        "gzip_bytes": len(response.content)
                        if response.get("Content-Encoding") == "gzip"
                        else None,
                        "raw_bytes": len(raw),
                    }
                )
            assert body is not None
            output = args.output_dir / f"sporameteo-map-{name}.geojson"
            output.write_bytes(data=raw)
            results.append(
                {
                    "name": name,
                    "bbox": bbox,
                    "width_m": width,
                    "height_m": height,
                    "square_count": body["square_count"],
                    "forest_squares": sum(
                        feature["properties"]["state"] == "available"
                        for feature in body["features"]
                    ),
                    "samples": samples,
                    "data_path": str(output),
                }
            )
        calls_before_broad_view = weather_calls
        response = client.get(
            "/api/v1/squares",
            {
                "bbox": "6,35,19,48",
                "target_date": args.assessment_date.isoformat(),
            },
        )
        if response.status_code != 400 or response.json().get("code") != "view_too_large":
            raise RuntimeError("The broad map view did not return view_too_large.")
        if weather_calls != calls_before_broad_view:
            raise RuntimeError("The broad map view attempted a weather lookup.")

    report = {
        "source": "real national habitat and synthetic-benchmark-29dweather estimates",
        "weather_acquisition": "replaced by exact stored snapshot lookup; no HTTP",
        "assessment_date": args.assessment_date.isoformat(),
        "views": results,
        "broad_view_weather_calls": 0,
    }
    report_path = args.output_dir / "sporameteo-map-measurements.json"
    report_path.write_text(data=json.dumps(obj=report, indent=2) + "\n")
    print(json.dumps(obj=report, indent=2))
    print(f"Saved measurement report to {report_path}")


if __name__ == "__main__":
    main()
