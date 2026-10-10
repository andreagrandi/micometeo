"""Shared helpers that turn source fields into find record values."""

import re

FIND_COLUMNS = [
    "record_id",
    "source",
    "source_record_id",
    "dataset_key",
    "taxon_name",
    "taxon_key",
    "event_date",
    "latitude",
    "longitude",
    "coordinate_uncertainty_m",
    "coordinates_obscured",
    "identification_quality",
    "licence",
    "rights_holder",
    "cell_id",
    "retrieved_at",
    "duplicate_of",
    "area",
    "in_pistoia",
    "date_precision",
    "year",
    "season",
    "recorded_by",
    "basis_of_record",
    "gbif_issues",
    "inat_id",
]

INAT_URL_PATTERN =re.compile(r"inaturalist\.org/observations/(\d+)")
LICENCE_PATTERN = re.compile(r"(?:licenses/|^cc[-_])(by(?:[-_](?:nc|sa|nd))*)")


def licence_code(*, value: str | None) -> str:
    """Map a licence URL or code to a short code such as CC0, CC-BY or CC-BY-NC.

    Anything that is not a Creative Commons licence becomes "other".
    """
    text = (value or "").strip().lower()
    if "cc0" in text or "publicdomain/zero" in text:
        return "CC0"
    match = LICENCE_PATTERN.search(text)
    if match is None:
        return "other"
    return "CC-" + match.group(1).replace("_", "-").upper()


def inat_id_from_url(*, url: str | None) -> str:
    """Return the iNaturalist observation ID inside a URL, or an empty string."""
    match = INAT_URL_PATTERN.search(url or "")
    return match.group(1) if match else ""


def season(*, month: int) -> str:
    """Return the season of a month, with winter from December to February."""
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"
