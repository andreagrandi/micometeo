"""Offline checks of the pure helpers in the P4b experiment script."""

import importlib.util
from pathlib import Path

import numpy as np
import pyarrow as pa

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("p4b_run", ROOT / "experiments" / "p4b_benchmark" / "run.py")
p4b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p4b)


def record(*, name: str, downloaded_at: str) -> dict:
    return {"name": name, "url": "u", "licence": "l", "version": "v", "downloaded_at": downloaded_at, "query": {"cell": name}}


def test_collapse_weather_sources_makes_one_entry_with_latest_date() -> None:
    records = [
        record(name="ERA5 hourly time series a.zip", downloaded_at="2026-10-01T00:00:00Z"),
        record(name="ERA5 hourly time series b.zip", downloaded_at="2026-10-03T00:00:00Z"),
        record(name="Forest tile", downloaded_at="2026-09-01T00:00:00Z"),
    ]
    collapsed = p4b.collapse_weather_sources(records=records)
    assert [item["name"] for item in collapsed] == ["Forest tile", "ERA5 hourly time series, 2 cells of 0.25 degrees"]
    assert collapsed[1]["downloaded_at"] == "2026-10-03T00:00:00Z"
    assert collapsed[1]["query"]["cells"] == 2


def test_drop_final_rows_keeps_them_only_when_asked() -> None:
    table = pa.table({"set": ["tuning", "final", "home_final", "test"], "x": [1, 2, 3, 4]})
    assert p4b.drop_final_rows(table=table, score_final=False)["set"].to_pylist() == ["tuning", "test"]
    assert p4b.drop_final_rows(table=table, score_final=True).num_rows == 4


def test_table_to_arrays_turns_text_into_plain_strings() -> None:
    arrays = p4b.table_to_arrays(table=pa.table({"set": ["a", "b"], "x": [1.0, np.nan]}))
    assert arrays["set"].dtype.kind == "U"
    assert np.isnan(arrays["x"][1])


def test_config_rules_load_with_all_keys() -> None:
    import tomllib

    settings = tomllib.loads((ROOT / "experiments" / "p4b_benchmark" / "config.toml").read_text())["settings"]
    for key in ("rules_weather", "rules_habitat"):
        assert all({"column", "op", "value", "reason"} <= set(rule) for rule in settings[key])
    assert settings["score_final"] is False
