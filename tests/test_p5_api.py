"""Tests for the demo API in apps/api."""

import gzip
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from micometeo_api import demo
from micometeo_api.server import DemoServer

TODAY = date(2026, 10, 11)
NOTICE = "Made-up demo data. These scores do not describe real mushrooms or real weather."
BBOX = "10.85,43.90,10.98,44.05"


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    """Run the server on a free port with a fixed date."""
    server = DemoServer(address=("127.0.0.1", 0), today=lambda: TODAY, quiet=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def call(
    url: str, method: str = "GET", headers: dict[str, str] | None = None
) -> tuple[int, Any, bytes]:
    """Send a request and return status, headers and the raw body."""
    request = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


def get_json(url: str) -> tuple[int, Any, dict[str, Any]]:
    """Send a GET request and decode the JSON body."""
    status, headers, body = call(url=url)
    return status, headers, json.loads(body)


def squares_url(base_url: str, **overrides: str | None) -> str:
    """Build a valid squares address, with optional changed parameters."""
    params: dict[str, str | None] = {
        "species": "porcini",
        "assessment_date": "2026-10-11",
        "target_date": "2026-10-12",
        "bbox": BBOX,
    }
    params.update(overrides)
    query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    return f"{base_url}/api/v1/squares?{query}"


def assert_demo_body(body: dict[str, Any]) -> None:
    """Check the two fields every body must carry."""
    assert body["demo_data"] is True
    assert body["notice"] == NOTICE


def test_health_returns_ok_with_demo_fields(base_url: str) -> None:
    status, headers, body = get_json(url=f"{base_url}/api/v1/health")
    assert status == 200
    assert body["status"] == "ok"
    assert_demo_body(body=body)
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert headers["X-Demo-Data"] == "true"
    assert headers["Access-Control-Allow-Origin"] == "*"


def test_info_lists_species_dates_and_limits(base_url: str) -> None:
    status, headers, body = get_json(url=f"{base_url}/api/v1/info")
    assert status == 200
    assert_demo_body(body=body)
    assert [item["id"] for item in body["species"]] == ["porcini", "ovolo"]
    assert body["species"][0]["scientific_names"] == [
        "Boletus edulis",
        "Boletus aereus",
        "Boletus reticulatus",
        "Boletus pinophilus",
    ]
    assert body["species"][1]["scientific_names"] == ["Amanita caesarea"]
    assert len(body["assessment_dates"]) == 14
    assert body["assessment_dates"][0] == "2026-10-11"
    assert body["assessment_dates"][-1] == "2026-09-28"
    assert body["max_days_ahead"] == 7
    assert body["area"] == {"west": 10.62, "south": 43.72, "east": 11.05, "north": 44.18}
    assert body["max_squares_per_request"] == 4000
    assert body["min_zoom"] == 11
    assert headers["Cache-Control"] == "public, max-age=300"


def test_squares_returns_every_field_on_every_square(base_url: str) -> None:
    status, headers, body = get_json(url=squares_url(base_url=base_url))
    assert status == 200
    assert_demo_body(body=body)
    assert headers["X-Demo-Data"] == "true"
    assert headers["Cache-Control"] == "public, max-age=300"
    assert body["type"] == "FeatureCollection"
    assert body["species"] == "porcini"
    assert body["assessment_date"] == "2026-10-11"
    assert body["target_date"] == "2026-10-12"
    assert body["days_ahead"] == 1
    assert body["square_count"] == len(body["features"]) > 0
    for feature in body["features"]:
        assert feature["type"] == "Feature"
        assert feature["id"].startswith("500m_E")
        assert feature["geometry"]["type"] == "Polygon"
        ring = feature["geometry"]["coordinates"][0]
        assert len(ring) == 5
        assert ring[0] == ring[-1]
        properties = feature["properties"]
        assert properties["cell_id"] == feature["id"]
        assert properties["species"] == "porcini"
        assert properties["assessment_date"] == "2026-10-11"
        assert properties["target_date"] == "2026-10-12"
        assert properties["days_ahead"] == 1
        assert properties["score_type"] == "forecast"
        assert isinstance(properties["score"], int)
        assert properties["reliability"] == "high"
        assert properties["sources"] == ["Made-up demo weather", "Made-up demo habitat"]
        assert properties["demo_data"] is True


def test_gzip_is_used_only_when_asked(base_url: str) -> None:
    url = squares_url(base_url=base_url)
    _, plain_headers, plain = call(url=url)
    _, zipped_headers, zipped = call(url=url, headers={"Accept-Encoding": "gzip"})
    assert "Content-Encoding" not in plain_headers
    assert zipped_headers["Content-Encoding"] == "gzip"
    assert zipped_headers["Vary"] == "Accept-Encoding"
    assert plain_headers["Vary"] == "Accept-Encoding"
    assert len(zipped) < len(plain)
    assert gzip.decompress(zipped) == plain


@pytest.mark.parametrize(
    "overrides",
    [
        {"species": None},
        {"assessment_date": None},
        {"target_date": None},
        {"bbox": None},
    ],
)
def test_missing_parameter_gives_400(base_url: str, overrides: dict[str, None]) -> None:
    status, headers, body = get_json(url=squares_url(base_url=base_url, **overrides))
    assert status == 400
    assert_demo_body(body=body)
    assert "required" in body["error"]
    assert headers["X-Demo-Data"] == "true"


@pytest.mark.parametrize(
    "overrides",
    [
        {"species": "truffle"},
        {"assessment_date": "11-10-2026"},
        {"target_date": "2026-13-01"},
        {"assessment_date": "2026-09-27"},
        {"assessment_date": "2026-10-12", "target_date": "2026-10-12"},
        {"target_date": "2026-10-10"},
        {"target_date": "2026-10-19"},
        {"bbox": "10.85,43.90,10.98"},
        {"bbox": "a,b,c,d"},
        {"bbox": "10.98,43.90,10.85,44.05"},
        {"bbox": "10.85,44.05,10.98,43.90"},
        {"bbox": "10.85,43.90,10.85,44.05"},
        {"bbox": "10.62,43.72,11.05,44.18"},
    ],
)
def test_invalid_request_gives_400_with_plain_error(
    base_url: str, overrides: dict[str, str]
) -> None:
    status, _, body = get_json(url=squares_url(base_url=base_url, **overrides))
    assert status == 400
    assert_demo_body(body=body)
    assert isinstance(body["error"], str) and body["error"].endswith(".")


def test_too_many_squares_error_gives_count_and_asks_to_zoom_in(base_url: str) -> None:
    status, _, body = get_json(url=squares_url(base_url=base_url, bbox="10.62,43.72,11.05,44.18"))
    assert status == 400
    assert "Zoom in" in body["error"]
    assert str(len(demo.load_grid(path=demo.GRID_PATH)[1])) in body["error"]


def test_last_available_assessment_date_and_seven_days_ahead_work(base_url: str) -> None:
    status, _, body = get_json(
        url=squares_url(base_url=base_url, assessment_date="2026-09-28", target_date="2026-10-05")
    )
    assert status == 200
    assert body["days_ahead"] == 7


@pytest.mark.parametrize(
    ("days_ahead", "score_type", "reliability"),
    [
        (0, "conditions_today", "high"),
        (1, "forecast", "high"),
        (2, "forecast", "high"),
        (3, "forecast", "medium"),
        (5, "forecast", "medium"),
        (6, "forecast", "low"),
        (7, "forecast", "low"),
    ],
)
def test_score_type_and_reliability_follow_days_ahead(
    base_url: str, days_ahead: int, score_type: str, reliability: str
) -> None:
    target = date(2026, 10, 4 + days_ahead).isoformat()
    _, _, body = get_json(
        url=squares_url(base_url=base_url, assessment_date="2026-10-04", target_date=target, bbox="10.9,43.95,10.92,43.97")
    )
    assert body["days_ahead"] == days_ahead
    for feature in body["features"]:
        assert feature["properties"]["score_type"] == score_type
        assert feature["properties"]["reliability"] == reliability


def test_scores_are_in_range_repeatable_and_vary_by_day_and_species(base_url: str) -> None:
    def scores(**overrides: str) -> dict[str, int]:
        _, _, body = get_json(url=squares_url(base_url=base_url, **overrides))
        return {f["id"]: f["properties"]["score"] for f in body["features"]}

    first = scores()
    assert first == scores()
    assert all(0 <= value <= 100 for value in first.values())
    assert len(set(first.values())) > 10
    assert first != scores(target_date="2026-10-13")
    assert first != scores(species="ovolo")


def test_neighbouring_squares_have_similar_scores(base_url: str) -> None:
    _, _, body = get_json(url=squares_url(base_url=base_url))
    scores = {f["id"]: f["properties"]["score"] for f in body["features"]}
    differences = []
    for cell_id, score in scores.items():
        east, north = cell_id.split("_")[1:]
        neighbour = f"500m_E{int(east[1:]) + 500}_{north}"
        if neighbour in scores:
            differences.append(abs(score - scores[neighbour]))
    assert differences
    assert sum(differences) / len(differences) < 10


def test_bbox_returns_only_overlapping_squares(base_url: str) -> None:
    west, south, east, north = 10.85, 43.90, 10.98, 44.05
    _, _, body = get_json(url=squares_url(base_url=base_url))
    expected = {
        square.cell_id
        for square in demo.load_grid(path=demo.GRID_PATH)[1]
        if square.east >= west
        and square.west <= east
        and square.north >= south
        and square.south <= north
    }
    assert {f["id"] for f in body["features"]} == expected
    for feature in body["features"]:
        ring = feature["geometry"]["coordinates"][0]
        lons = [point[0] for point in ring]
        lats = [point[1] for point in ring]
        assert max(lons) >= west and min(lons) <= east
        assert max(lats) >= south and min(lats) <= north


def test_bbox_outside_the_area_returns_no_squares(base_url: str) -> None:
    status, _, body = get_json(url=squares_url(base_url=base_url, bbox="0,0,1,1"))
    assert status == 200
    assert body["square_count"] == 0
    assert body["features"] == []


def test_unknown_path_gives_404_json(base_url: str) -> None:
    status, headers, body = get_json(url=f"{base_url}/api/v1/nothing")
    assert status == 404
    assert_demo_body(body=body)
    assert "error" in body
    assert headers["X-Demo-Data"] == "true"


def test_other_methods_give_405_json(base_url: str) -> None:
    status, headers, body = call(url=f"{base_url}/api/v1/health", method="POST")[0:3]
    decoded = json.loads(body)
    assert status == 405
    assert_demo_body(body=decoded)
    assert "error" in decoded
    assert headers["X-Demo-Data"] == "true"


def test_options_gives_204_with_cors_headers(base_url: str) -> None:
    status, headers, body = call(url=f"{base_url}/api/v1/squares", method="OPTIONS")
    assert status == 204
    assert body == b""
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert "GET" in headers["Access-Control-Allow-Methods"]
