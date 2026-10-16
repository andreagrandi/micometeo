"""Keep automated tests independent of downloaded local tree files."""

import pytest


@pytest.fixture(autouse=True)
def isolated_jrc_directory(settings, tmp_path) -> None:
    settings.SPORAMETEO_JRC_DIRECTORY = str(tmp_path / "jrc")


@pytest.fixture(autouse=True)
def plain_static_names(settings) -> None:
    """Render pages without running collectstatic first.

    The fingerprinted names need the list of files that collectstatic writes.
    """
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }
