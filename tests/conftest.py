"""Keep automated tests independent of downloaded local tree files."""

import pytest


@pytest.fixture(autouse=True)
def isolated_jrc_directory(settings, tmp_path) -> None:
    settings.SPORAMETEO_JRC_DIRECTORY = str(tmp_path / "jrc")
