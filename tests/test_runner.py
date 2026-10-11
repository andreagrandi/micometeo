"""Tests for the experiment runner, using fake experiments and no network."""

import os
import time
from pathlib import Path

import pytest

from micometeo.config import ConfigError, load_config
from micometeo.runner import run_experiment
from tests.conftest import read_record

COMPLETE_BODY = '''
import random
from pathlib import Path


def run(context):
    source = context.raw_dir / "data.txt"
    source.write_text("hello", encoding="utf-8")
    context.add_source(
        name="fake",
        url="https://example.org",
        licence="CC0",
        version="1",
        downloaded_at="2026-10-10T10:00:00Z",
        query={"a": 1},
    )
    context.add_input(source)
    out = context.output_dir / "out.txt"
    out.write_text(str(random.random()), encoding="utf-8")
    context.add_output(out)
'''

SLEEP_BODY = '''
import os
import time


def run(context):
    (context.raw_dir / "pid.txt").write_text(str(os.getpid()), encoding="utf-8")
    context.add_source(
        name="fake",
        url="https://example.org",
        licence="CC0",
        version="1",
        downloaded_at="2026-10-10T10:00:00Z",
        query={},
    )
    time.sleep(60)
'''

FAIL_BODY = '''
def run(context):
    raise ValueError("something broke")
'''


def process_exists(*, pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_run_stops_at_time_limit_and_writes_record(make_experiment) -> None:
    root = make_experiment(name="slow", body=SLEEP_BODY)
    start = time.monotonic()
    path = run_experiment(name="slow", root=root, time_limit_seconds=1)
    elapsed = time.monotonic() - start
    record = read_record(path=path)
    assert path.is_file()
    assert record["status"] == "timed_out"
    assert "time limit" in record["error"]
    assert 1 <= record["duration_seconds"] < 2.5
    assert elapsed < 10
    assert len(record["sources"]) == 1
    pid = int((root / "data" / "raw" / "slow" / "pid.txt").read_text())
    assert not process_exists(pid=pid)


def test_completed_run_records_everything(make_experiment) -> None:
    root = make_experiment(name="ok", body=COMPLETE_BODY)
    record = read_record(path=run_experiment(name="ok", root=root))
    assert record["status"] == "completed"
    assert record["seed"] == 7
    assert record["config"]["settings"] == {"value": 3}
    assert record["time_limit_seconds"] == 1800
    assert record["sources"][0]["downloaded_at"] == "2026-10-10T10:00:00Z"
    assert record["sources"][0]["query"] == {"a": 1}
    assert len(record["inputs"][0]["sha256"]) == 64
    assert record["inputs"][0]["size_bytes"] == 5
    assert record["inputs"][0]["path"] == "data/raw/ok/data.txt"
    assert len(record["outputs"]) == 1
    assert not Path(record["outputs"][0]).is_absolute()
    assert (root / record["outputs"][0]).is_file()
    assert record["duration_seconds"] > 0
    assert record["cpu_seconds"] > 0
    # Any Python child process needs more than 10 MB.
    assert record["peak_memory_bytes"] > 10_000_000
    assert record["started_at"].endswith("Z")
    assert record["finished_at"].endswith("Z")
    assert record["computer"]["cpu_count"]
    assert "hostname" not in record["computer"]
    assert record["versions"]["python"]
    assert record["versions"]["micometeo"]
    assert "pytest" in record["versions"]["packages"]
    assert "commit" in record["git"]


def test_same_seed_gives_same_random_output(make_experiment) -> None:
    root = make_experiment(name="seeded", body=COMPLETE_BODY)
    first = read_record(path=run_experiment(name="seeded", root=root))
    second = read_record(path=run_experiment(name="seeded", root=root))
    assert first["run_id"] != second["run_id"]
    first_output = (root / first["outputs"][0]).read_text()
    assert first_output == (root / second["outputs"][0]).read_text()


def test_failed_run_records_error_message(make_experiment) -> None:
    root = make_experiment(name="bad", body=FAIL_BODY)
    record = read_record(path=run_experiment(name="bad", root=root))
    assert record["status"] == "failed"
    assert "ValueError: something broke" in record["error"]


def test_default_time_limit_is_30_minutes(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("seed = 1\n", encoding="utf-8")
    assert load_config(path=path).time_limit_minutes * 60 == 1800


@pytest.mark.parametrize("value", ["31", "0", "-5"])
def test_invalid_time_limit_is_rejected(tmp_path: Path, value: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(f"seed = 1\ntime_limit_minutes = {value}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="time_limit_minutes"):
        load_config(path=path)


def test_missing_seed_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('description = "x"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="seed"):
        load_config(path=path)
