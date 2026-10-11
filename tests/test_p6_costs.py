"""Offline checks of the P6a counts of squares, weather cells, map images and user traffic."""

import importlib.util
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from shapely.geometry import box

ROOT = Path(__file__).resolve().parent.parent


def load_p6():
    spec = importlib.util.spec_from_file_location(
        "p6_run", ROOT / "experiments" / "p6_costs" / "run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p6 = load_p6()


def test_square_centres_counts_only_squares_with_centre_inside() -> None:
    area = box(0, 0, 1000, 1250)
    corner_e, corner_n = p6.square_centres(area_laea=area, size_m=500)
    assert sorted(zip(corner_e.tolist(), corner_n.tolist())) == [
        (0, 0),
        (0, 500),
        (500, 0),
        (500, 500),
    ]


def test_weather_cells_counts_cells_touching_the_area() -> None:
    area = box(10.05, 43.05, 10.3, 43.2)
    assert p6.weather_cells(area=area, cell_degrees=0.25) == 2


def test_tile_count_at_zoom_zero_is_one() -> None:
    assert p6.tile_count(area=box(10, 43, 11, 44), zoom=0) == 1


def test_score_one_day_gives_scores_from_0_to_100_and_lower_reliability_far_ahead() -> None:
    scores = p6.score_one_day(square_count=50, days_ahead=8, rng=np.random.default_rng(1))
    assert scores["score"].shape == (50, 8)
    assert set(np.unique(scores["score"]).tolist()) <= {0, 25, 50, 75, 100}
    assert scores["reliability"][0].tolist() == [2, 2, 2, 1, 1, 1, 0, 0]


def test_write_day_keeps_one_row_per_square_and_day_ahead(tmp_path: Path) -> None:
    corner_e = np.array([0, 500], dtype=np.int64)
    corner_n = np.array([0, 0], dtype=np.int64)
    scores = p6.score_one_day(square_count=2, days_ahead=8, rng=np.random.default_rng(1))
    size = p6.write_day(
        corner_e=corner_e, corner_n=corner_n, scores=scores, path=tmp_path / "day.parquet"
    )
    table = pq.read_table(tmp_path / "day.parquet")
    assert size > 0
    assert table.num_rows == 16
    assert table.column("days_ahead").to_pylist()[:8] == list(range(8))


def test_user_rows_scale_with_active_users() -> None:
    users = {
        "active_users": [10, 100],
        "sessions_per_user_per_day": 2,
        "square_requests_per_session": 10,
        "other_requests_per_session": 2,
        "square_request_kb": 7.4,
        "page_kb": 230,
        "cold_load_share": 0.25,
    }
    rows = p6.user_rows(users=users)
    assert [row["api_requests_per_day"] for row in rows] == [240, 2400]
    assert rows[1]["api_requests_per_month"] == 72000
    assert all(row["kind"] == "estimated" for row in rows)
