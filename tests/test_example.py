"""Tests for the example experiment parsing, using a canned response."""

import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_example():
    spec = importlib.util.spec_from_file_location(
        "example_run", ROOT / "experiments" / "example" / "run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_example_builds_rows_and_csv(tmp_path: Path) -> None:
    example = load_example()
    response = {
        "daily": {
            "time": ["2025-10-01", "2025-10-02"],
            "precipitation_sum": [0.0, 4.2],
            "temperature_2m_mean": [17.5, 15.1],
        }
    }
    rows = example.rows_from_response(response=response)
    path = tmp_path / "summary.csv"
    example.write_summary(rows=rows, path=path)
    with path.open(encoding="utf-8") as handle:
        read_back = list(csv.DictReader(handle))
    assert list(read_back[0]) == ["date", "precipitation_mm", "mean_temperature_c"]
    assert read_back[1] == {
        "date": "2025-10-02",
        "precipitation_mm": "4.2",
        "mean_temperature_c": "15.1",
    }


def test_example_query_uses_italian_time() -> None:
    example = load_example()
    query = example.build_query(
        settings={
            "latitude": 43.93,
            "longitude": 10.91,
            "start_date": "2025-10-01",
            "end_date": "2025-10-07",
            "timezone": "Europe/Rome",
        }
    )
    assert query["timezone"] == "Europe/Rome"
    assert query["daily"] == "precipitation_sum,temperature_2m_mean"
