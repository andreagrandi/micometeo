"""GBIF bulk download of porcini records and parsing of the Darwin Core archive."""

import base64
import csv
import io
import json
import os
import time
import urllib.request
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from micometeo.finds.grid import cell_id
from micometeo.finds.records import inat_id_from_url, licence_code, season

API_URL = "https://api.gbif.org/v1"
USER_AGENT = "micometeo-experiments/0.1 (research prototype)"
TIMEOUT_SECONDS = 60
LOGIN_VARIABLES = ("GBIF_USERNAME", "GBIF_PASSWORD", "GBIF_EMAIL")
# Public GBIF ID of the iNaturalist research-grade dataset, not a secret.
INAT_DATASET_KEY = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"  # gitleaks:allow


def read_login() -> dict[str, str]:
    """Read the GBIF login from the environment, set through .envrc."""
    missing = [name for name in LOGIN_VARIABLES if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            f"Missing {', '.join(missing)}. Copy .envrc.example to .envrc, "
            "fill it in and run direnv allow."
        )
    return {name: os.environ[name] for name in LOGIN_VARIABLES}


def box_wkt(*, west: float, south: float, east: float, north: float) -> str:
    """Return a WKT polygon for a box, corners listed counter-clockwise."""
    corners = [(west, south), (east, south), (east, north), (west, north), (west, south)]
    return "POLYGON((" + ",".join(f"{lon} {lat}" for lon, lat in corners) + "))"


def build_predicate(*, settings: dict[str, Any]) -> dict[str, Any]:
    """Build the GBIF download filter for the species and both study areas."""
    emilia = settings["emilia_apennines"]
    return {
        "type": "and",
        "predicates": [
            {
                "type": "in",
                "key": "TAXON_KEY",
                "values": [str(key) for key in settings["gbif_taxon_keys"]],
            },
            {"type": "equals", "key": "HAS_COORDINATE", "value": "true"},
            {
                "type": "or",
                "predicates": [
                    {"type": "equals", "key": "GADM_GID", "value": settings["tuscany_gid"]},
                    {
                        "type": "and",
                        "predicates": [
                            {"type": "equals", "key": "GADM_GID", "value": emilia["gid"]},
                            {
                                "type": "within",
                                "geometry": box_wkt(
                                    west=emilia["west"],
                                    south=emilia["south"],
                                    east=emilia["east"],
                                    north=emilia["north"],
                                ),
                            },
                        ],
                    },
                    {
                        "type": "in",
                        "key": "COUNTRY",
                        "values": settings["comparison_countries"],
                    },
                ],
            },
        ],
    }


def _call(
    *, url: str, login: dict[str, str] | None = None, body: bytes | None = None
) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    if login is not None:
        token = f"{login['GBIF_USERNAME']}:{login['GBIF_PASSWORD']}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(token).decode()
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as reply:
        return reply.read()


def request_download(*, predicate: dict[str, Any], login: dict[str, str]) -> str:
    """Ask GBIF to prepare a Darwin Core archive and return its download key."""
    body = {
        "creator": login["GBIF_USERNAME"],
        "notificationAddresses": [login["GBIF_EMAIL"]],
        "sendNotification": False,
        "format": "DWCA",
        "predicate": predicate,
    }
    reply = _call(
        url=f"{API_URL}/occurrence/download/request",
        login=login,
        body=json.dumps(body).encode(),
    )
    return reply.decode().strip()


def wait_for_download(
    *, key: str, poll_seconds: float = 30, max_wait_seconds: float = 1200
) -> dict[str, Any]:
    """Poll GBIF until the download is ready and return its metadata."""
    waited = 0.0
    while True:
        status = json.loads(_call(url=f"{API_URL}/occurrence/download/{key}"))
        if status["status"] == "SUCCEEDED":
            return status
        if status["status"] in ("FAILED", "KILLED", "CANCELLED", "FILE_ERASED"):
            raise RuntimeError(f"GBIF download {key} ended with {status['status']}.")
        if waited >= max_wait_seconds:
            raise RuntimeError(
                f"GBIF download {key} is not ready after {max_wait_seconds} s. "
                "Set gbif_download_key in config.toml and run again later."
            )
        time.sleep(poll_seconds)
        waited += poll_seconds


def fetch_download(*, key: str, raw_dir: Path) -> tuple[Path, dict[str, Any]]:
    """Download the archive of a finished GBIF download, reusing a saved copy."""
    status = wait_for_download(key=key)
    zip_path = raw_dir / f"gbif_{key}.zip"
    if not zip_path.exists():
        temp_path = zip_path.with_suffix(".part")
        temp_path.write_bytes(_call(url=status["downloadLink"]))
        temp_path.replace(zip_path)
    return zip_path, status


def _text(row: dict[str, str], name: str) -> str:
    return (row.get(name) or "").strip()


def _area(row: dict[str, str], settings: dict[str, Any]) -> str:
    if _text(row, "countryCode") in settings["comparison_countries"]:
        return "comparison"
    return "home"


def parse_row(
    *, row: dict[str, str], settings: dict[str, Any], retrieved_at: str
) -> dict[str, Any]:
    """Turn one occurrence.txt row into a find record.

    A blurred position goes to published_latitude and published_longitude, not latitude and longitude.
    """
    year = int(_text(row, "year")) if _text(row, "year") else None
    month = int(_text(row, "month")) if _text(row, "month") else None
    day = int(_text(row, "day")) if _text(row, "day") else None
    if year and month and day:
        event_date, precision = date(year, month, day).isoformat(), "day"
    elif year and month:
        event_date, precision = "", "month"
    elif year:
        event_date, precision = "", "year"
    else:
        event_date, precision = "", "none"

    obscured = bool(_text(row, "informationWithheld") or _text(row, "dataGeneralizations"))
    latitude = float(_text(row, "decimalLatitude")) if _text(row, "decimalLatitude") else None
    longitude = float(_text(row, "decimalLongitude")) if _text(row, "decimalLongitude") else None
    published_latitude, published_longitude = None, None
    if obscured:
        published_latitude, published_longitude = latitude, longitude
        latitude, longitude = None, None
    uncertainty = _text(row, "coordinateUncertaintyInMeters")
    dataset_key = _text(row, "datasetKey")
    gbif_id = _text(row, "gbifID")

    return {
        "record_id": f"gbif:{gbif_id}",
        "source": "GBIF",
        "source_record_id": gbif_id,
        "dataset_key": dataset_key,
        "taxon_name": _text(row, "scientificName"),
        "taxon_key": int(_text(row, "taxonKey")) if _text(row, "taxonKey") else None,
        "event_date": event_date,
        "latitude": latitude,
        "longitude": longitude,
        "coordinate_uncertainty_m": float(uncertainty) if uncertainty else None,
        "coordinates_obscured": obscured,
        "identification_quality": (
            "inat_research" if dataset_key == INAT_DATASET_KEY else "gbif_other_source"
        ),
        "licence": licence_code(value=_text(row, "license")),
        "rights_holder": _text(row, "rightsHolder"),
        "cell_id": (
            cell_id(latitude=latitude, longitude=longitude)
            if latitude is not None and longitude is not None
            else ""
        ),
        "retrieved_at": retrieved_at,
        "duplicate_of": "",
        "area": _area(row, settings),
        "in_pistoia": _text(row, "level2Gid") == settings["pistoia_gid"],
        "date_precision": precision,
        "year": year,
        "season": season(month=month) if month else "",
        "recorded_by": _text(row, "recordedBy"),
        "basis_of_record": _text(row, "basisOfRecord"),
        "gbif_issues": _text(row, "issue"),
        "inat_id": inat_id_from_url(url=_text(row, "occurrenceID")),
        "published_latitude": published_latitude,
        "published_longitude": published_longitude,
    }


def parse_archive(
    *, zip_path: Path, settings: dict[str, Any], retrieved_at: str
) -> list[dict[str, Any]]:
    """Read occurrence.txt from a GBIF Darwin Core archive into find records."""
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open("occurrence.txt") as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8", newline="")
            reader = csv.DictReader(text, delimiter="\t", quoting=csv.QUOTE_NONE)
            return [
                parse_row(row=row, settings=settings, retrieved_at=retrieved_at)
                for row in reader
            ]
