"""iNaturalist observations of porcini, downloaded page by page through the public API."""

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from sporameteo.finds.grid import cell_id
from sporameteo.finds.records import licence_code, season

API_URL = "https://api.inaturalist.org/v1/observations"
USER_AGENT = "sporameteo-experiments/0.1 (research prototype)"
TIMEOUT_SECONDS = 60
PAGE_SIZE = 200
PAUSE_SECONDS = 1.0
BLURRING_PRIVACY = ("obscured", "private")


def build_query(
    *, settings: dict[str, Any], place_id: int, id_above: int = 0
) -> dict[str, Any]:
    """Build the query settings for one page of observations in one place."""
    return {
        "taxon_id": ",".join(str(taxon) for taxon in settings["inat_taxon_ids"]),
        "place_id": place_id,
        "quality_grade": "any",
        "per_page": PAGE_SIZE,
        "order_by": "id",
        "order": "asc",
        "id_above": id_above,
    }


def download_place(
    *, settings: dict[str, Any], place_name: str, place_id: int, raw_dir: Path
) -> list[Path]:
    """Save every page of observations for one place, reusing pages already saved."""
    paths: list[Path] = []
    id_above = 0
    page = 1
    while True:
        path = raw_dir / f"inat_{place_name}_{page:03d}.json"
        if path.exists():
            body = path.read_bytes()
        else:
            query = build_query(settings=settings, place_id=place_id, id_above=id_above)
            url = f"{API_URL}?{urllib.parse.urlencode(query)}"
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as reply:
                body = reply.read()
            path.write_bytes(body)
            time.sleep(PAUSE_SECONDS)
        paths.append(path)
        results = json.loads(body)["results"]
        if len(results) < PAGE_SIZE:
            return paths
        id_above = results[-1]["id"]
        page += 1


def is_blurred(*, observation: dict[str, Any]) -> bool:
    """Return True if iNaturalist hides or blurs the exact position."""
    return (
        bool(observation.get("obscured"))
        or observation.get("geoprivacy") in BLURRING_PRIVACY
        or observation.get("taxon_geoprivacy") in BLURRING_PRIVACY
    )


def parse_observation(
    *,
    observation: dict[str, Any],
    area: str,
    settings: dict[str, Any],
    retrieved_at: str,
) -> dict[str, Any]:
    """Turn one iNaturalist observation into a find record.

    A blurred position goes to published_latitude and published_longitude, not latitude and longitude.
    """
    observed_on = observation.get("observed_on") or ""
    obscured = is_blurred(observation=observation)
    latitude, longitude = None, None
    published_latitude, published_longitude = None, None
    location = observation.get("location")
    if location:
        point = tuple(float(part) for part in location.split(","))
        if obscured:
            published_latitude, published_longitude = point
        else:
            latitude, longitude = point
    taxon = observation.get("taxon") or {}
    user = (observation.get("user") or {}).get("login", "")
    accuracy = observation.get("public_positional_accuracy")
    month = int(observed_on[5:7]) if observed_on else None

    return {
        "record_id": f"inat:{observation['id']}",
        "source": "iNaturalist",
        "source_record_id": str(observation["id"]),
        "dataset_key": "",
        "taxon_name": taxon.get("name", ""),
        "taxon_key": taxon.get("id"),
        "event_date": observed_on,
        "latitude": latitude,
        "longitude": longitude,
        "coordinate_uncertainty_m": float(accuracy) if accuracy is not None else None,
        "coordinates_obscured": obscured,
        "identification_quality": f"inat_{observation.get('quality_grade', 'casual')}",
        "licence": licence_code(value=observation.get("license_code")),
        "rights_holder": user,
        "cell_id": (
            cell_id(latitude=latitude, longitude=longitude)
            if latitude is not None and longitude is not None
            else ""
        ),
        "retrieved_at": retrieved_at,
        "duplicate_of": "",
        "area": area,
        "in_pistoia": settings["inat_pistoia_place_id"]
        in (observation.get("place_ids") or []),
        "date_precision": "day" if observed_on else "none",
        "year": int(observed_on[:4]) if observed_on else None,
        "season": season(month=month) if month else "",
        "recorded_by": user,
        "basis_of_record": "HUMAN_OBSERVATION",
        "gbif_issues": "",
        "inat_id": str(observation["id"]),
        "published_latitude": published_latitude,
        "published_longitude": published_longitude,
    }


def parse_pages(
    *,
    paths: list[Path],
    area: str,
    settings: dict[str, Any],
    retrieved_at: str,
    max_latitude: float | None = None,
) -> list[dict[str, Any]]:
    """Read saved pages into find records, keeping only points south of max_latitude."""
    records = []
    for path in paths:
        for observation in json.loads(path.read_text(encoding="utf-8"))["results"]:
            if max_latitude is not None and not _south_of(observation, max_latitude):
                continue
            records.append(
                parse_observation(
                    observation=observation,
                    area=area,
                    settings=settings,
                    retrieved_at=retrieved_at,
                )
            )
    return records


def _south_of(observation: dict[str, Any], max_latitude: float) -> bool:
    location = observation.get("location")
    if not location:
        return False
    return float(location.split(",")[0]) < max_latitude
