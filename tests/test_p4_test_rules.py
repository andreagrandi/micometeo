"""Offline checks of the P4a split into tuning, test and final sets, and of the comparison points."""

import importlib.util
import random
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent


def load_p4():
    spec = importlib.util.spec_from_file_location(
        "p4_run", ROOT / "experiments" / "p4_test_rules" / "run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p4 = load_p4()

SETTINGS = {
    "block_size_m": 100000,
    "tuning_share": 0.6,
    "test_share": 0.2,
    "final_from_year": 2025,
    "test_from_year": 2022,
    "buffer_m": 25000,
}


def cell(*, east: int, north: int) -> str:
    return f"500m_E{east}_N{north}"


def find(record_id: str, *, east: int = 4465500, north: int = 2301000, day: str = "2020-10-01", area: str = "comparison") -> dict[str, Any]:
    return {
        "record_id": record_id,
        "area": area,
        "event_date": day,
        "year": int(day[:4]),
        "latitude": 46.0,
        "longitude": 8.0,
        "cell_id": cell(east=east, north=north),
    }


def case(case_id: str, **values: Any) -> dict[str, Any]:
    row = {
        "case_id": case_id,
        "area": "comparison",
        "cell_id": cell(east=4000000, north=2000000),
        "year": 2020,
        "block_id": "100km_E4000000_N2000000",
        "block_group": "tuning",
        "set": "tuning",
        "record_ids": [case_id],
    }
    return {**row, **values}


def test_finds_on_one_square_and_day_form_one_case() -> None:
    finds = [
        find("a"),
        find("b"),
        find("c", day="2020-10-02"),
        find("d", east=4466000),
    ]

    cases = p4.build_cases(finds=finds, block_size_m=100000)

    assert [c["case_id"] for c in cases] == [
        "500m_E4465500_N2301000_2020-10-01",
        "500m_E4465500_N2301000_2020-10-02",
        "500m_E4466000_N2301000_2020-10-01",
    ]
    assert cases[0]["record_ids"] == ["a", "b"]
    assert cases[0]["find_count"] == 2
    assert cases[0]["assessment_date"] == "2020-10-01"


def test_case_centre_is_in_the_square_in_degrees() -> None:
    cases = p4.build_cases(finds=[find("a")], block_size_m=100000)

    assert 43 < cases[0]["latitude"] < 45
    assert 10 < cases[0]["longitude"] < 12


def test_block_id_uses_the_lower_left_corner_of_the_square() -> None:
    assert p4.block_id_for(cell_id=cell(east=4465500, north=2301000), block_size_m=100000) == "100km_E4400000_N2300000"
    assert p4.block_id_for(cell_id=cell(east=4400000, north=2399500), block_size_m=100000) == "100km_E4400000_N2300000"
    assert p4.block_id_for(cell_id=cell(east=4399500, north=2400000), block_size_m=100000) == "100km_E4300000_N2400000"


def test_block_assignment_is_repeatable_and_depends_on_the_seed() -> None:
    counts = {f"100km_E{4000000 + i * 100000}_N2000000": 10 for i in range(20)}
    kwargs = {"block_counts": counts, "tuning_share": 0.6, "test_share": 0.2}

    first = p4.assign_block_groups(seed=42, **kwargs)
    again = p4.assign_block_groups(seed=42, **kwargs)
    other = p4.assign_block_groups(seed=7, **kwargs)

    assert first == again
    assert first != other
    values = list(first.values())
    assert values.count("tuning") == 12
    assert values.count("test") == 4
    assert values.count("final") == 4


def test_tuning_blocks_reach_the_share_of_cases_and_no_more() -> None:
    counts = {f"100km_E{4000000 + i * 100000}_N2000000": size for i, size in enumerate([30, 25, 20, 10, 8, 7])}

    groups = p4.assign_block_groups(block_counts=counts, seed=3, tuning_share=0.6, test_share=0.2)

    tuning = sum(size for block, size in counts.items() if groups[block] == "tuning")
    tuning_and_test = sum(size for block, size in counts.items() if groups[block] != "final")
    assert tuning >= 60
    assert tuning - min(size for block, size in counts.items() if groups[block] == "tuning") < 60
    assert tuning_and_test >= 80
    assert set(groups.values()) <= {"tuning", "test", "final"}


def rule_kwargs(**values: Any) -> dict[str, Any]:
    base = {
        "held_out_blocks": [],
        "final_from_year": 2025,
        "test_from_year": 2022,
        "buffer_m": 25000,
    }
    return {**base, **values}


def test_final_year_cut_off_beats_a_tuning_block() -> None:
    result = p4.set_for_case(case=case("x", year=2025), block_group="tuning", **rule_kwargs())

    assert result == "final"


def test_final_block_beats_test_year() -> None:
    result = p4.set_for_case(case=case("x", year=2023), block_group="final", **rule_kwargs())

    assert result == "final"


def test_test_year_cut_off_and_test_block_give_test() -> None:
    assert p4.set_for_case(case=case("x", year=2022), block_group="tuning", **rule_kwargs()) == "test"
    assert p4.set_for_case(case=case("x", year=2024), block_group="tuning", **rule_kwargs()) == "test"
    assert p4.set_for_case(case=case("x", year=2020), block_group="test", **rule_kwargs()) == "test"


def test_old_case_in_tuning_block_is_tuning_when_far_from_held_out_blocks() -> None:
    far = ["100km_E4300000_N2000000"]

    result = p4.set_for_case(case=case("x", year=2021), block_group="tuning", **rule_kwargs(held_out_blocks=far))

    assert result == "tuning"


def test_case_within_the_buffer_of_a_held_out_block_is_buffer() -> None:
    # The square centre is at east 4099750, 250 m from the block that starts at 4100000.
    near = case("x", year=2021, cell_id=cell(east=4099500, north=2050000))

    result = p4.set_for_case(case=near, block_group="tuning", **rule_kwargs(held_out_blocks=["100km_E4100000_N2000000"]))

    assert result == "buffer"


def test_case_just_outside_the_buffer_is_tuning() -> None:
    # The centre is 25,250 m west of the block, so it is outside the 25 km buffer.
    outside = case("x", year=2021, cell_id=cell(east=4074500, north=2050000))

    result = p4.set_for_case(case=outside, block_group="tuning", **rule_kwargs(held_out_blocks=["100km_E4100000_N2000000"]))

    assert result == "tuning"


def test_distance_to_block_is_zero_inside_and_diagonal_at_corners() -> None:
    block = "100km_E4000000_N2000000"

    assert p4.distance_to_block(east=4050000, north=2050000, block_id=block) == 0
    assert p4.distance_to_block(east=3997000, north=1996000, block_id=block) == pytest.approx(5000)
    assert p4.distance_to_block(east=4150000, north=2050000, block_id=block) == pytest.approx(50000)


def test_home_cases_are_never_tuning() -> None:
    old = case("x", area="home", year=2018, block_group="home")
    new = case("y", area="home", year=2025, block_group="home")

    assert p4.set_for_case(case=old, block_group="home", **rule_kwargs()) == "home_test"
    assert p4.set_for_case(case=new, block_group="home", **rule_kwargs()) == "home_final"


def test_assign_sets_gives_every_case_a_group_and_passes_the_check() -> None:
    finds = []
    for index in range(30):
        finds.append(find(f"r{index}", east=4000000 + index * 100000 + 500, north=2000000, day="2019-10-01"))
        finds.append(find(f"s{index}", east=4000000 + index * 100000 + 500, north=2000500, day="2023-10-01"))
    finds.append(find("h1", area="home", day="2018-10-01"))
    finds.append(find("h2", area="home", day="2025-10-01"))
    cases = p4.build_cases(finds=finds, block_size_m=100000)

    blocks = p4.assign_sets(cases=cases, settings=SETTINGS, seed=42)

    assert len(blocks) == 30
    assert sum(block["comparison_cases"] for block in blocks) == 60
    assert {c["block_group"] for c in cases if c["area"] == "home"} == {"home"}
    assert {c["set"] for c in cases if c["area"] == "home"} == {"home_test", "home_final"}
    assert all(c["set"] in {"tuning", "test", "final", "buffer", "home_test", "home_final"} for c in cases)
    p4.check_separation(cases=cases, buffer_m=25000)


def test_check_separation_passes_on_good_data() -> None:
    cases = [
        case("a"),
        case("b", set="test", block_group="test", block_id="100km_E4500000_N2000000", cell_id=cell(east=4500000, north=2000000)),
        case("c", set="buffer", cell_id=cell(east=4450000, north=2000000)),
        case("h", area="home", set="home_test", block_group="home"),
    ]

    p4.check_separation(cases=cases, buffer_m=25000)


def test_check_separation_raises_when_a_find_is_in_two_sets() -> None:
    cases = [case("a", record_ids=["shared"]), case("b", set="test", block_group="test", record_ids=["shared"],
                                                    block_id="100km_E4500000_N2000000", cell_id=cell(east=4500000, north=2000000))]

    with pytest.raises(ValueError, match="shared"):
        p4.check_separation(cases=cases, buffer_m=25000)


def test_check_separation_raises_for_tuning_in_a_held_out_block() -> None:
    cases = [case("a", block_group="final")]

    with pytest.raises(ValueError, match="lies in a final block"):
        p4.check_separation(cases=cases, buffer_m=25000)


def test_check_separation_raises_for_tuning_near_a_held_out_block() -> None:
    cases = [
        case("a", cell_id=cell(east=4099500, north=2050000)),
        case("b", set="test", block_group="test", block_id="100km_E4100000_N2000000", cell_id=cell(east=4150000, north=2050000)),
    ]

    with pytest.raises(ValueError, match="within"):
        p4.check_separation(cases=cases, buffer_m=25000)


def test_check_separation_raises_for_home_in_tuning() -> None:
    cases = [case("h", area="home", block_group="home", set="tuning")]

    with pytest.raises(ValueError, match="Home case"):
        p4.check_separation(cases=cases, buffer_m=25000)


def test_count_rows_report_cases_and_finds_per_area_set_and_band() -> None:
    cases = [case("a", find_count=2, year=2020), case("b", find_count=1, year=2023, set="test")]

    rows = p4.count_rows(cases=cases, settings=SETTINGS)

    assert {"area": "comparison", "set": "tuning", "year_band": "all", "cases": 1, "finds": 2} in rows
    assert {"area": "comparison", "set": "test", "year_band": "2022 to 2024", "cases": 1, "finds": 1} in rows


POINT_SETTINGS = {"forest_points_per_case": 5, "known_spots_per_case": 3, "min_known_spots": 2}


def pool_of(*corners: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    return np.array([c[0] for c in corners]), np.array([c[1] for c in corners])


def forest_pool(*, count: int, east: int = 4000000, north: int = 2000000) -> tuple[np.ndarray, np.ndarray]:
    return pool_of(*[(east + i * 500, north) for i in range(count)])


def point_case(case_id: str, day: str, *, east: int, set_name: str = "tuning", group: str = "tuning", area: str = "comparison") -> dict[str, Any]:
    return case(
        f"{cell(east=east, north=2000000)}_{day}",
        area=area,
        cell_id=cell(east=east, north=2000000),
        assessment_date=day,
        set=set_name,
        block_group=group,
    )


def test_forest_share_counts_forest_pixels_among_usable_ones() -> None:
    pixels = np.zeros((5, 10), dtype="uint8")
    pixels[0, :3] = 1
    pixels[1, 0] = 2
    # The second square: 24 unusable pixels and one forest pixel give a share of 1.
    pixels[:, 5:] = 255
    pixels[4, 9] = 1

    shares = p4.square_forest_shares(pixels=pixels)

    assert shares.shape == (1, 2)
    assert shares[0, 0] == pytest.approx(4 / 25)
    assert shares[0, 1] == pytest.approx(1.0)


def test_square_without_usable_pixels_is_not_forest() -> None:
    pixels = np.full((5, 10), 255, dtype="uint8")
    pixels[:, :5] = 0
    pixels[0, 5] = 1
    pixels[1, 5] = 0

    shares = p4.square_forest_shares(pixels=pixels)
    east, north = p4.forest_square_corners(pixels=np.full((5, 5), 254, dtype="uint8"), west=4000000, north=2100000, from_share=0.1)

    assert shares[0, 0] == 0
    assert shares[0, 1] == pytest.approx(0.5)
    assert len(east) == 0 and len(north) == 0


def test_forest_square_needs_the_share_and_gets_the_right_corner() -> None:
    pixels = np.zeros((10, 10), dtype="uint8")
    pixels[:2, :5] = 1
    pixels[5:6, 5:10] = 2
    pixels[7, 0] = 1

    east, north = p4.forest_square_corners(pixels=pixels, west=4000000, north=2100000, from_share=0.2)

    # Ten forest pixels in the top-left square and five in the bottom-right one. The bottom-left has one.
    assert list(zip(east.tolist(), north.tolist())) == [(4000000, 2099500), (4000500, 2099000)]


def test_tiles_cover_the_aligned_bounds_in_pieces_of_at_most_the_tile_size() -> None:
    bounds = p4.align_bounds(bounds=(4030120.4, 2553999.0, 4870001.0, 2947000.0))

    boxes = p4.tile_boxes(bounds=bounds, tile_m=400000)

    assert bounds == (4030000, 2553500, 4870500, 2947000)
    assert len(boxes) == 3
    assert boxes[0] == (4030000, 2553500, 4430000, 2947000)
    assert boxes[-1] == (4830000, 2553500, 4870500, 2947000)
    assert all(b[2] - b[0] <= 400000 and b[3] - b[1] <= 400000 for b in boxes)
    assert p4.tile_query(box=boxes[-1], pixel_m=100)["size"] == "405,3935"


def test_forest_points_are_on_the_case_day_in_area_and_group_and_never_on_a_find_square() -> None:
    cases = [
        point_case("a", "2020-10-01", east=4000000),
        point_case("b", "2020-10-01", east=4000500),
        point_case("c", "2020-10-02", east=4000500),
    ]
    pools = {("comparison", "tuning", True): forest_pool(count=40)}

    points, _ = p4.build_points(cases=cases, pools=pools, settings=POINT_SETTINGS, rng=random.Random(1))

    forest = [p for p in points if p["point_kind"] == "forest"]
    assert len(forest) == 15
    day_one = {p["cell_id"] for p in forest if p["assessment_date"] == "2020-10-01"}
    assert cell(east=4000000, north=2000000) not in day_one
    assert cell(east=4000500, north=2000000) not in day_one
    assert len({p["cell_id"] for p in forest if p["case_id"] == cases[0]["case_id"]}) == 5
    assert {(p["area"], p["set"]) for p in forest} == {("comparison", "tuning")}
    day_two = {p["cell_id"] for p in forest if p["assessment_date"] == "2020-10-02"}
    assert cell(east=4000500, north=2000000) not in day_two


def test_points_use_the_pool_of_the_case_area_and_block_group() -> None:
    home = point_case("h", "2020-10-01", east=4000000, area="home", group="home", set_name="home_test")
    test_case = point_case("t", "2020-10-01", east=4000500, set_name="test", group="test")
    pools = {
        ("home", "home", False): forest_pool(count=10, east=4100000),
        ("comparison", "test", False): forest_pool(count=10, east=4200000),
    }

    points, _ = p4.build_points(cases=[home, test_case], pools=pools, settings=POINT_SETTINGS, rng=random.Random(1))

    for point in points:
        east, _ = p4.parse_cell_id(cell_id=point["cell_id"])
        assert point["point_kind"] == "forest"
        assert (4100000 <= east < 4105000) == (point["area"] == "home")
        assert (4200000 <= east < 4205000) == (point["area"] == "comparison")


def test_tuning_pool_drops_squares_near_held_out_blocks() -> None:
    squares = {
        "home": pool_of((4000000, 2000000)),
        "comparison": pool_of((4000000, 2000000), (4074500, 2050000), (4075000, 2050000), (4100000, 2050000), (4300000, 2000000)),
    }
    groups = {
        "100km_E4000000_N2000000": "tuning",
        "100km_E4100000_N2000000": "test",
        "100km_E4300000_N2000000": "tuning",
    }

    pools = p4.build_pools(squares=squares, groups=groups, block_size_m=100000, buffer_m=25000)

    kept = set(zip(*[a.tolist() for a in pools[("comparison", "tuning", True)]]))
    assert kept == {(4000000, 2000000), (4074500, 2050000), (4300000, 2000000)}
    assert len(pools[("comparison", "tuning", False)][0]) == 4
    assert len(pools[("comparison", "test", False)][0]) == 1
    assert len(pools[("comparison", "final", False)][0]) == 0
    assert len(pools[("home", "home", False)][0]) == 1


def test_known_spots_come_from_the_same_set_on_other_days() -> None:
    cases = [
        point_case("a", "2020-10-01", east=4000000),
        point_case("b", "2020-10-02", east=4000500),
        point_case("c", "2020-10-03", east=4001000),
        point_case("d", "2020-10-04", east=4001500, set_name="test", group="test"),
        point_case("e", "2020-10-01", east=4002000, set_name="test", group="tuning"),
        point_case("f", "2020-10-05", east=4002500, area="home", group="home", set_name="home_test"),
    ]
    pools = {("comparison", "tuning", True): forest_pool(count=10), ("comparison", "test", False): forest_pool(count=10),
             ("home", "home", False): forest_pool(count=10), ("comparison", "tuning", False): forest_pool(count=10)}

    points, without_known = p4.build_points(cases=cases, pools=pools, settings={**POINT_SETTINGS, "min_known_spots": 1}, rng=random.Random(2))

    known = {p["case_id"]: p for p in points if p["point_kind"] == "known_spot"}
    spots = {p["cell_id"] for p in points if p["point_kind"] == "known_spot" and p["case_id"] == cases[0]["case_id"]}
    assert spots == {cell(east=4000500, north=2000000), cell(east=4001000, north=2000000)}
    assert cell(east=4001500, north=2000000) not in spots
    assert cell(east=4002000, north=2000000) not in spots
    assert cases[0]["case_id"] in known
    assert cases[5]["case_id"] in {c["case_id"] for c in without_known}


def test_known_spots_on_the_case_day_are_left_out() -> None:
    cases = [
        point_case("a", "2020-10-01", east=4000000),
        point_case("b", "2020-10-02", east=4000500),
        point_case("c", "2020-10-02", east=4001000),
        point_case("d", "2020-10-01", east=4001000),
    ]
    pools = {("comparison", "tuning", True): forest_pool(count=10)}

    points, _ = p4.build_points(cases=cases, pools=pools, settings={**POINT_SETTINGS, "min_known_spots": 1}, rng=random.Random(2))

    spots = {p["cell_id"] for p in points if p["point_kind"] == "known_spot" and p["case_id"] == cases[0]["case_id"]}
    assert spots == {cell(east=4000500, north=2000000)}


def test_fewer_than_min_known_spots_gives_none_and_is_counted() -> None:
    cases = [point_case("a", "2020-10-01", east=4000000), point_case("b", "2020-10-02", east=4000500)]
    pools = {("comparison", "tuning", True): forest_pool(count=10)}

    points, without_known = p4.build_points(cases=cases, pools=pools, settings=POINT_SETTINGS, rng=random.Random(2))

    assert [p for p in points if p["point_kind"] == "known_spot"] == []
    assert len(without_known) == 2
    rows = p4.point_count_rows(points=points, without_known=without_known)
    assert {"area": "comparison", "set": "tuning", "point_kind": "known_spot", "cases_with_points": 0, "points": 0, "cases_without_known_spots": 2} in rows
    assert {"area": "comparison", "set": "tuning", "point_kind": "forest", "cases_with_points": 2, "points": 10, "cases_without_known_spots": 0} in rows


def test_buffer_cases_get_no_points() -> None:
    cases = [point_case("a", "2020-10-01", east=4000000, set_name="buffer")]

    points, without_known = p4.build_points(cases=cases, pools={}, settings=POINT_SETTINGS, rng=random.Random(2))

    assert points == []
    assert without_known == []


def test_same_seed_gives_the_same_points() -> None:
    cases = [point_case(str(i), f"2020-10-0{i + 1}", east=4000000 + i * 500) for i in range(6)]
    pools = {("comparison", "tuning", True): forest_pool(count=200)}

    def draw(seed: int) -> list[tuple[str, str]]:
        points, _ = p4.build_points(cases=cases, pools=pools, settings=POINT_SETTINGS, rng=random.Random(seed))
        return [(p["case_id"], p["cell_id"]) for p in points]

    assert draw(42) == draw(42)
    assert draw(42) != draw(43)
