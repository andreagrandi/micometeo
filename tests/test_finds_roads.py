"""Tests for the road and path distance check, using a tiny OpenStreetMap file."""

import random
from pathlib import Path

import pytest
from shapely.geometry import box

from micometeo.finds import roads

OSM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="test">
  <node id="1" version="1" lat="44.0" lon="10.90"/>
  <node id="2" version="1" lat="44.0" lon="10.92"/>
  <node id="3" version="1" lat="44.01" lon="10.90"/>
  <node id="4" version="1" lat="44.01" lon="10.92"/>
  <node id="5" version="1" lat="44.02" lon="10.90"/>
  <node id="6" version="1" lat="44.02" lon="10.92"/>
  <node id="7" version="1" lat="46.0" lon="8.00"/>
  <node id="8" version="1" lat="46.0" lon="8.01"/>
  <way id="10" version="1">
    <nd ref="1"/><nd ref="2"/><tag k="highway" v="secondary"/>
  </way>
  <way id="11" version="1">
    <nd ref="3"/><nd ref="4"/><tag k="highway" v="track"/>
  </way>
  <way id="12" version="1">
    <nd ref="5"/><nd ref="6"/><tag k="highway" v="proposed"/>
  </way>
  <way id="13" version="1">
    <nd ref="7"/><nd ref="8"/><tag k="highway" v="residential"/>
  </way>
  <way id="14" version="1">
    <nd ref="1"/><nd ref="3"/><tag k="waterway" v="stream"/>
  </way>
</osm>
"""


@pytest.fixture
def osm_file(tmp_path: Path) -> Path:
    path = tmp_path / "test.osm"
    path.write_text(OSM_XML, encoding="utf-8")
    return path


def test_only_nearby_highways_are_kept(osm_file: Path) -> None:
    ways = roads.ways_near_points(paths=[osm_file], points=[(44.005, 10.91)])
    assert sorted(label for label, _ in ways) == ["path", "road"]


def test_nearest_distances_for_roads_and_paths(osm_file: Path) -> None:
    point_near_track = (44.0109, 10.91)
    far_point = (44.5, 10.91)
    ways = roads.ways_near_points(paths=[osm_file], points=[point_near_track])
    near, far = roads.nearest_distances(
        points=[point_near_track, far_point], ways=ways, radius_m=2000
    )
    assert near["road_or_path"] == pytest.approx(100, abs=3)
    assert near["road"] == pytest.approx(1212, abs=10)
    assert far == {"road": 2000.0, "road_or_path": 2000.0}


def test_no_ways_gives_the_cap() -> None:
    result = roads.nearest_distances(points=[(44.0, 10.9)], ways=[], radius_m=2000)
    assert result == [{"road": 2000.0, "road_or_path": 2000.0}]


@pytest.mark.parametrize(
    ("highway", "expected"),
    [("secondary", "road"), ("track", "path"), ("footway", "path"), ("proposed", "")],
)
def test_label_way(highway: str, expected: str) -> None:
    assert roads.label_way(highway=highway) == expected


def test_near_cells_cover_neighbours() -> None:
    cells = roads.near_cells(points=[(44.005, 10.905)])
    assert len(cells) == 9


def test_random_points_fall_inside_the_outline() -> None:
    outline = box(10.0, 43.0, 11.0, 44.0).difference(box(10.0, 43.0, 10.5, 43.5))
    points = roads.random_points(area=outline, count=200, rng=random.Random(1))
    assert len(points) == 200
    assert not any(latitude < 43.5 and longitude < 10.5 for latitude, longitude in points)


def test_summary_gives_median_share_and_range() -> None:
    distances = [10.0, 50.0, 150.0, 400.0, 900.0] * 20
    summary = roads.summarise(distances=distances, near_m=100, rng=random.Random(1), repeats=200)
    assert summary["points"] == 100
    assert summary["median_m"] == 150
    assert summary["share_near"] == 0.4
    assert summary["share_near_low"] <= 0.4 <= summary["share_near_high"]
