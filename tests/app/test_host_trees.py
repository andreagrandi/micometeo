"""Check bounded JRC setup, masked sampling and cache reuse."""

import io
import zipfile
from pathlib import Path

import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from micometeo.host_trees import SPECIES, prepare_sources, read_manifest, sample_squares


@pytest.fixture
def jrc_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, list[str]]:
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff", height=2, width=3, count=1, dtype="float32",
            crs="EPSG:3035", transform=from_origin(west=0, north=2000, xsize=1000, ysize=1000),
            nodata=-9999.0,
        ) as dataset:
            dataset.write(np.array([[0.0, 0.8, -1.0], [-9999.0, 0.2, -9999.0]], dtype="float32"), indexes=1)
        raster = memory.read()
    buffer = io.BytesIO()
    with zipfile.ZipFile(file=buffer, mode="w") as archive:
        archive.writestr(zinfo_or_arcname="source.tif", data=raster)
    requests = []

    def download(*, url: str, timeout: int) -> io.BytesIO:
        requests.append(url)
        return io.BytesIO(initial_bytes=buffer.getvalue())

    monkeypatch.setattr("urllib.request.urlopen", download)
    directory = tmp_path / "rasters"
    prepare_sources(directory=directory)
    return directory, requests


def test_jrc_setup_reuses_verified_files_and_preserves_manifest(jrc_files) -> None:
    directory, requests = jrc_files
    first = read_manifest(directory=directory)
    prepare_sources(directory=directory)
    assert len(requests) == len(SPECIES)
    assert read_manifest(directory=directory) == first


def test_jrc_sampling_preserves_zero_missing_and_outside_coverage(jrc_files) -> None:
    directory, _ = jrc_files
    manifest, version = read_manifest(directory=directory)
    sampled = sample_squares(
        directory=directory, manifest=manifest, version=version,
        centres={"zero": (250, 1750), "host": (1250, 1750), "missing": (250, 750),
                 "negative": (2250, 1750), "outside": (5000, 5000)},
    )
    assert sampled["zero"].values == (0.0,) * 5
    assert sampled["host"].values == pytest.approx((0.8,) * 5)
    assert sampled["missing"].values == (None,) * 5
    assert sampled["outside"].values == (None,) * 5
    assert sampled["negative"].values == (None,) * 5
    assert sampled["host"].source_id == f"jrc:{version}"


def test_jrc_setup_rejects_changed_cached_file(jrc_files) -> None:
    directory, requests = jrc_files
    (directory / f"{SPECIES[0]}.tif").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="Cached file changed"):
        prepare_sources(directory=directory)
    assert len(requests) == len(SPECIES)


def test_failed_jrc_setup_does_not_publish_an_incomplete_manifest(tmp_path, monkeypatch) -> None:
    def fail(*, url: str, timeout: int) -> None:
        raise TimeoutError("source timeout")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(TimeoutError):
        prepare_sources(directory=tmp_path)
    assert read_manifest(directory=tmp_path) is None


def test_jrc_setup_resumes_without_redownloading_completed_species(jrc_files, tmp_path, monkeypatch) -> None:
    directory, _ = jrc_files
    archive = (directory / f"{SPECIES[0]}_rpp.zip").read_bytes()
    requests = []

    def download(*, url: str, timeout: int) -> io.BytesIO:
        requests.append(url)
        if len(requests) == 3:
            raise TimeoutError("interrupted")
        return io.BytesIO(initial_bytes=archive)

    monkeypatch.setattr("urllib.request.urlopen", download)
    destination = tmp_path / "interrupted"
    with pytest.raises(TimeoutError):
        prepare_sources(directory=destination)
    assert read_manifest(directory=destination) is None
    prepare_sources(directory=destination)
    assert len(requests) == len(SPECIES) + 1
    assert requests.count(requests[0]) == 1
    assert requests.count(requests[1]) == 1
    assert read_manifest(directory=destination) is not None


def test_jrc_manifest_rejects_paths_outside_source_directory(jrc_files) -> None:
    import json

    directory, _ = jrc_files
    manifest, _ = read_manifest(directory=directory)
    manifest["files"][0]["filename"] = "../elsewhere.tif"
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Unexpected JRC manifest"):
        read_manifest(directory=directory)
