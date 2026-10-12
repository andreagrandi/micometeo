"""Download JRC rasters once and sample local files for requested squares.

Runtime sampling never contacts the provider or scans the national grid.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import urllib.request
import zipfile
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import rasterio

from micometeo.forecast_method import HOST_GROUPS, HostTrees


GROUP_SPECIES = {
    "beech": ("Fagus-sylvatica",),
    "chestnut": ("Castanea-sativa",),
    "oaks": (
        "Quercus-cerris", "Quercus-frainetto", "Quercus-ilex", "Quercus-petraea",
        "Quercus-pubescens", "Quercus-robur", "Quercus-suber",
    ),
    "pines": (
        "Pinus-cembra", "Pinus-halepensis", "Pinus-mugo", "Pinus-nigra",
        "Pinus-pinaster", "Pinus-pinea", "Pinus-sylvestris",
    ),
    "spruce_fir": ("Picea-abies", "Abies-alba"),
}
SPECIES = tuple(species for group in GROUP_SPECIES.values() for species in group)
BASE_URL = "https://ies-ows.jrc.ec.europa.eu/efdac/download/Atlas"
MAX_ARCHIVE_BYTES = 30_000_000
MAX_RASTER_BYTES = 60_000_000
SAMPLING_VERSION = "jrc-centre-max-complete-groups-v1"
CREDIT = "JRC; de Rigo, Caudullo and San-Miguel-Ayanz; European Atlas of Forest Tree Species, 2016"
LICENCE = "European Commission reuse notice; acknowledge source and applicable dataset notices"


def checksum(*, path: Path) -> str:
    with path.open(mode="rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _atomic_write(*, path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            temporary.replace(target=path)
        finally:
            temporary.unlink(missing_ok=True)


def _check_raster(*, path: Path) -> None:
    with rasterio.open(fp=path) as dataset:
        if (
            dataset.crs is None or dataset.crs.to_epsg() != 3035
            or dataset.res != (1000.0, 1000.0) or dataset.count != 1
            or dataset.scales != (1.0,) or dataset.offsets != (0.0,)
            or dataset.nodata is None or dataset.nodata >= 0
        ):
            raise ValueError("JRC raster does not match the expected 1 km occurrence data")


def prepare_sources(*, directory: Path) -> dict[str, Any]:
    """Prepare a complete source set with resumable downloads.

    Publish the manifest only after every selected raster passes validation.
    """
    directory.mkdir(parents=True, exist_ok=True)
    files = []
    for species in SPECIES:
        archive_path = directory / f"{species}_rpp.zip"
        raster_path = directory / f"{species}.tif"
        record_path = directory / f"{species}.json"
        url = f"{BASE_URL}/{species}_rpp.zip"
        record = None
        if record_path.exists():
            record = json.loads(record_path.read_text())
            for path, key in ((archive_path, "archive_sha256"), (raster_path, "sha256")):
                if path.exists() and checksum(path=path) != record[key]:
                    raise ValueError(f"Cached file changed: {path}. Use a new source directory.")
        if not archive_path.exists():
            with urllib.request.urlopen(url=url, timeout=30) as response:
                data = response.read(MAX_ARCHIVE_BYTES + 1)
            if len(data) > MAX_ARCHIVE_BYTES:
                raise ValueError(f"{species} exceeds the 30 MB archive limit")
            if record is not None and hashlib.sha256(data).hexdigest() != record["archive_sha256"]:
                raise ValueError(f"The provider changed {species}. Use a new source directory.")
            _atomic_write(path=archive_path, data=data)
        if not raster_path.exists() or record is None:
            with zipfile.ZipFile(file=archive_path) as archive:
                members = [item for item in archive.infolist() if item.filename.lower().endswith(".tif")]
                if len(members) != 1 or members[0].file_size > MAX_RASTER_BYTES:
                    raise ValueError(f"Unexpected raster content in {archive_path.name}")
                data = archive.read(name=members[0].filename)
            _atomic_write(path=raster_path, data=data)
        _check_raster(path=raster_path)
        if record is None:
            record = {
                "species": species, "filename": raster_path.name, "url": url,
                "sha256": checksum(path=raster_path),
                "archive_sha256": checksum(path=archive_path),
                "archive_bytes": archive_path.stat().st_size,
                "raster_bytes": raster_path.stat().st_size,
                "downloaded_at": datetime.now(tz=UTC).isoformat(),
            }
            _atomic_write(path=record_path, data=json.dumps(record, sort_keys=True).encode())
        files.append(record)
    manifest = {
        "files": files, "source_year": 2006, "resolution_m": 1000,
        "credit": CREDIT, "licence": LICENCE,
        "source_url": "https://forest.jrc.ec.europa.eu/en/european-atlas/atlas-data-and-metadata/",
        "sampling_version": SAMPLING_VERSION,
    }
    _atomic_write(path=directory / "manifest.json", data=json.dumps(manifest, sort_keys=True).encode())
    return manifest


def read_manifest(*, directory: Path) -> tuple[dict[str, Any], str] | None:
    path = directory / "manifest.json"
    if not path.exists():
        return None
    manifest = json.loads(path.read_text())
    if (
        manifest["sampling_version"] != SAMPLING_VERSION
        or tuple(item["species"] for item in manifest["files"]) != SPECIES
        or manifest["source_year"] != 2006 or manifest["resolution_m"] != 1000
        or any(item["filename"] != f"{item['species']}.tif" for item in manifest["files"])
    ):
        raise ValueError("Unexpected JRC manifest")
    version = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    return manifest, version


@lru_cache(maxsize=64)
def _verified_file(*, path: Path, expected: str, size: int, modified: int) -> None:
    if checksum(path=path) != expected:
        raise ValueError(f"JRC file checksum changed: {path}")
    _check_raster(path=path)


def sample_squares(
    *, directory: Path, manifest: dict[str, Any], version: str,
    centres: dict[str, tuple[float, float]],
) -> dict[str, HostTrees]:
    """Read the native pixel at each square centre from local files.

    A group stays missing if any selected species in that group is missing.
    """
    if not centres:
        return {}
    samples: dict[str, list[float | None]] = {}
    for record in manifest["files"]:
        path = directory / record["filename"]
        stat = path.stat()
        _verified_file(path=path, expected=record["sha256"], size=stat.st_size, modified=stat.st_mtime_ns)
        with rasterio.open(fp=path) as dataset:
            values = []
            for sample in dataset.sample(xy=list(centres.values()), indexes=1, masked=True):
                value = None if np.ma.is_masked(sample[0]) else float(sample[0])
                # JRC also uses -1 outside model coverage without marking it as nodata.
                if value is not None and value < 0:
                    value = None
                if value is not None and (not math.isfinite(value) or value > 1):
                    raise ValueError("JRC occurrence value is outside zero to one")
                values.append(value)
            samples[record["species"]] = values
    results = {}
    for index, key in enumerate(centres):
        groups = []
        for group in HOST_GROUPS:
            values = [samples[species][index] for species in GROUP_SPECIES[group]]
            groups.append(None if any(value is None for value in values) else max(values))
        results[key] = HostTrees(
            values=tuple(groups), source_id=f"jrc:{version}", source_year=2006, resolution_m=1000,
            metadata={
                "credit": manifest["credit"], "licence": manifest["licence"],
                "source_url": manifest["source_url"], "sampling_version": SAMPLING_VERSION,
                "species_files": manifest["files"],
            },
        )
    return results
