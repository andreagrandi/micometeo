"""Helpers to build fake experiments in a temporary repository."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def make_experiment(tmp_path: Path):
    """Return a function that writes a fake experiment under tmp_path."""

    def _make(*, name: str, body: str, config_extra: str = "") -> Path:
        folder = tmp_path / "experiments" / name
        folder.mkdir(parents=True)
        (folder / "config.toml").write_text(
            f'description = "fake"\nseed = 7\n{config_extra}\n[settings]\nvalue = 3\n',
            encoding="utf-8",
        )
        (folder / "run.py").write_text(body, encoding="utf-8")
        return tmp_path

    return _make


def read_record(*, path: Path) -> dict:
    """Read a run record."""
    return json.loads(path.read_text(encoding="utf-8"))
