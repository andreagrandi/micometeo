"""Check the queued weather path or verify an existing completed live result."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from collections.abc import Sequence
from datetime import date, datetime
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
        description="Queue a live weather check or verify its existing completed result."
    )
    parser.add_argument("action", choices=("queue", "verify"))
    parser.add_argument("--database-name", required=True)
    parser.add_argument("--assessment-date", required=True, type=_parse_date)
    parser.add_argument("--bbox", required=True)
    parser.add_argument("--output", required=True, type=Path)
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


def _body(response: Any) -> dict[str, Any]:
    raw = response.content
    if response.get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    return json.loads(s=raw)


def _bbox(value: str) -> tuple[float, float, float, float]:
    values = tuple(float(part.strip()) for part in value.split(","))
    if len(values) != 4:
        raise ValueError("The bbox must contain west,south,east,north.")
    west, south, east, north = values
    if not west < east or not south < north:
        raise ValueError("The bbox needs west smaller than east and south smaller than north.")
    return values


def main() -> None:
    """Run the bounded live queue or existing-result verification."""
    args = _parser().parse_args()
    try:
        _bbox(args.bbox)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    _load_django(database_name=args.database_name)

    from django.core.cache import cache
    from django.db import connection
    from django.test import Client, override_settings
    from estimate_updates.models import EstimateResult, EstimateUpdate
    from weather_on_demand.services import italian_assessment_date
    from weather_on_demand.models import WeatherFetch
    from weather_requests.models import WeatherRequestAttempt
    from weather_summaries.models import WeatherSnapshot

    if connection.settings_dict["NAME"] != args.database_name:
        raise RuntimeError("Django connected to a different database than --database-name.")
    if args.action == "queue" and args.assessment_date != italian_assessment_date():
        raise SystemExit(
            "Queue mode requires the current Italian assessment date. "
            "Use verify for a historical date."
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cache.clear()
    attempts_before = WeatherRequestAttempt.objects.count()
    fetches_before = WeatherFetch.objects.count()
    report: dict[str, object] = {
        "action": args.action,
        "checked_at": datetime.now().astimezone().isoformat(),
        "bbox": args.bbox,
        "target_date": args.assessment_date.isoformat(),
        "database_name": args.database_name,
        "attempts_before": attempts_before,
        "fetches_before": fetches_before,
    }

    def stored_weather(*, cells: Sequence[Any], **_kwargs: Any) -> SimpleNamespace:
        rows = WeatherSnapshot.objects.filter(
            assessment_date=args.assessment_date,
            status=WeatherSnapshot.Status.READY,
            cell_key__in=[cell.key for cell in cells],
        )
        by_cell = {row.cell_key: row for row in rows}
        missing = sorted({cell.key for cell in cells} - set(by_cell))
        if missing:
            raise RuntimeError("A verification snapshot disappeared: " + ", ".join(missing))
        return SimpleNamespace(
            by_cell={
                cell.key: SimpleNamespace(
                    state="ready",
                    snapshot_id=by_cell[cell.key].id,
                    assessment_date=args.assessment_date,
                )
                for cell in cells
            }
        )

    with override_settings(ALLOWED_HOSTS=["testserver"]), patch(
        "map_api.api._today", return_value=args.assessment_date
    ):
        client = Client()
        if args.action == "queue":
            response = client.get(
                "/api/v1/squares",
                {"bbox": args.bbox, "target_date": args.assessment_date.isoformat()},
                HTTP_ACCEPT_ENCODING="gzip",
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"The queue request returned HTTP {response.status_code}: {response.content[:500]!r}"
                )
            body = _body(response)
            report.update(
                {
                    "square_count": body["square_count"],
                    "states": sorted({feature["properties"]["state"] for feature in body["features"]}),
                    "weather_acquisition": "not measured by the queue check",
                }
            )
        else:
            with patch(
                "map_api.api.weather_services.request_weather", side_effect=stored_weather
            ):
                response = client.get(
                    "/api/v1/squares",
                    {"bbox": args.bbox, "target_date": args.assessment_date.isoformat()},
                    HTTP_ACCEPT_ENCODING="gzip",
                )
                if response.status_code != 200:
                    raise RuntimeError(
                        f"The verification request returned HTTP {response.status_code}: "
                        f"{response.content[:500]!r}"
                    )
                body = _body(response)
                available = [
                    feature
                    for feature in body["features"]
                    if feature["properties"]["state"] == "available"
                ]
                if not available:
                    raise RuntimeError("The verified map response has no available square.")
                selected = available[0]
                properties = selected["properties"]
                update = EstimateUpdate.objects.get(public_id=properties["update_id"])
                snapshot = WeatherSnapshot.objects.get(id=update.snapshot_id)
                day_count = snapshot.days.count()
                summary_count = snapshot.summaries.count()
                result_count = EstimateResult.objects.filter(update=update).count()
                if day_count != 38 or summary_count != 8:
                    raise RuntimeError("The saved snapshot needs 38 days and eight summaries.")
                if result_count != update.row_count:
                    raise RuntimeError("The saved estimate row count does not match its update.")
                detail_response = client.get(
                    f"/api/v1/areas/{selected['id']}",
                    {
                        "target_date": args.assessment_date.isoformat(),
                        "update_id": properties["update_id"],
                    },
                )
                if detail_response.status_code != 200:
                    raise RuntimeError(
                        f"The detail request returned HTTP {detail_response.status_code}: "
                        f"{detail_response.content[:500]!r}"
                    )
                detail = _body(detail_response)
                if detail["estimate"]["whole_percentage"] != properties["percentage"]:
                    raise RuntimeError("The detail estimate does not match the map percentage.")
                if detail["selection"]["update_id"] != properties["update_id"]:
                    raise RuntimeError("The detail update does not match the map update.")
                second = client.get(
                    "/api/v1/squares",
                    {"bbox": args.bbox, "target_date": args.assessment_date.isoformat()},
                )
                if second.status_code != 200:
                    raise RuntimeError("The repeated map request failed.")
                attempts_after_repeat = WeatherRequestAttempt.objects.count()
                fetches_after_repeat = WeatherFetch.objects.count()
                if attempts_after_repeat != attempts_before:
                    raise RuntimeError("The repeated map request created a provider attempt.")
                if fetches_after_repeat != fetches_before:
                    raise RuntimeError("The repeated map request created a weather fetch.")
                fetch_count_before_broad = WeatherFetch.objects.count()
                broad = client.get(
                    "/api/v1/squares",
                    {"bbox": "6,35,19,48", "target_date": args.assessment_date.isoformat()},
                )
                if broad.status_code != 400 or broad.json().get("code") != "view_too_large":
                    raise RuntimeError("The broad map view did not return view_too_large.")
                if WeatherFetch.objects.count() != fetch_count_before_broad:
                    raise RuntimeError("The broad map view created a weather fetch.")
                if WeatherRequestAttempt.objects.count() != attempts_after_repeat:
                    raise RuntimeError("The broad map view created a provider attempt.")
                report.update(
                    {
                        "square_count": body["square_count"],
                        "states": sorted({feature["properties"]["state"] for feature in body["features"]}),
                        "selected_square": selected["id"],
                        "percentage": properties["percentage"],
                        "update_id": properties["update_id"],
                        "snapshot_id": str(snapshot.id),
                        "source_ids": snapshot.source_ids,
                        "source_attempt_ids": snapshot.source_attempt_ids,
                        "source_retrieval": snapshot.latest_retrieval.isoformat(),
                        "stored_snapshot_days": day_count,
                        "stored_snapshot_summaries": summary_count,
                        "stored_cell_result_rows": result_count,
                        "detail_matches_map": True,
                        "repeat_provider_calls": attempts_after_repeat - attempts_before,
                        "broad_view_provider_calls": 0,
                        "weather_acquisition": "saved ready snapshots only; no provider request",
                        "weather_source": detail["sources"]["weather"],
                    }
                )
    report["attempts_after"] = WeatherRequestAttempt.objects.count()
    report["fetches_after"] = WeatherFetch.objects.count()
    args.output.write_text(data=json.dumps(obj=report, indent=2, default=str) + "\n")
    print(json.dumps(obj=report, indent=2, default=str))
    print(f"Saved live pipeline report to {args.output}")


if __name__ == "__main__":
    main()
