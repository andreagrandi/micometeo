"""Offline checks of the P1c comparison of Trends interest with find counts."""

import importlib.util
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load_p1c():
    spec = importlib.util.spec_from_file_location(
        "p1c_run", ROOT / "experiments" / "p1c_flush_signs" / "run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p1c = load_p1c()


def find(record_id: str, day: str, **values: Any) -> dict[str, Any]:
    row = {
        "record_id": record_id,
        "area": "home",
        "event_date": day,
        "date_precision": "day",
        "duplicate_rule": "",
        "failed_filter": "",
    }
    return {**row, **values}


def weekly(*, signs: list[float], finds: list[int], first: date = date(2020, 1, 5)) -> list[dict[str, Any]]:
    return [
        {
            "week_start": first + timedelta(weeks=index),
            "year": 2020,
            "porcini_searches": sign,
            "funghi_porcini_searches": sign,
            "all_finds": count,
        }
        for index, (sign, count) in enumerate(zip(signs, finds))
    ]


def test_parse_export_reads_less_than_one_as_zero(tmp_path: Path) -> None:
    path = tmp_path / "export.csv"
    path.write_text(
        "Category: All categories\n\nWeek,porcini: (Tuscany),funghi porcini: (Tuscany)\n"
        "2019-12-29,10,<1\n2020-01-05,6,3\n",
        encoding="utf-8",
    )

    assert p1c.parse_export(path=path) == {
        date(2019, 12, 29): (10, 0),
        date(2020, 1, 5): (6, 3),
    }


def test_merge_exports_keeps_the_earlier_file_for_the_overlap_week() -> None:
    earlier = {date(2019, 12, 22): (1, 1), date(2019, 12, 29): (10, 7)}
    later = {date(2019, 12, 29): (100, 100), date(2020, 1, 5): (6, 3)}

    merged = p1c.merge_exports(exports=[earlier, later])

    assert merged[date(2019, 12, 29)] == (10, 7)
    assert merged[date(2020, 1, 5)] == (6, 3)
    assert len(merged) == 3


def test_weeks_start_on_sunday_and_belong_to_the_year_of_their_thursday() -> None:
    assert p1c.week_start(day=date(2020, 1, 4)) == date(2019, 12, 29)
    assert p1c.week_start(day=date(2020, 1, 5)) == date(2020, 1, 5)
    assert p1c.week_year(week=date(2019, 12, 29)) == 2020
    assert p1c.week_year(week=date(2020, 12, 27)) == 2020


def test_collect_finds_counts_a_record_in_both_tables_once() -> None:
    reliable = [find("a", "2020-09-15"), find("b", "2020-09-16")]
    timing = [{"record_id": "b", "area": "home", "event_date": "2020-09-16"}, {"record_id": "c", "area": "home", "event_date": "2020-09-17"}]

    finds = p1c.collect_finds(reliable=reliable, timing=timing)

    assert sorted(finds) == ["a", "b", "c"]
    assert finds["b"]["reliable"] and finds["b"]["timing"]
    assert finds["c"]["timing"] and not finds["c"]["reliable"]


def test_collect_finds_drops_other_areas_duplicates_filtered_and_month_dates() -> None:
    reliable = [
        find("home", "2020-09-15"),
        find("abroad", "2020-09-15", area="comparison"),
        find("duplicate", "2020-09-15", duplicate_rule="same_place"),
        find("filtered", "2020-09-15", failed_filter="low_accuracy"),
        find("month", "2020-09", date_precision="month"),
    ]

    assert list(p1c.collect_finds(reliable=reliable, timing=[])) == ["home"]


def test_weekly_rows_bin_finds_by_sunday_week() -> None:
    finds = p1c.collect_finds(
        reliable=[find("a", "2020-01-05"), find("b", "2020-01-11")],
        timing=[
            {"record_id": "b", "area": "home", "event_date": "2020-01-11"},
            {"record_id": "c", "area": "home", "event_date": "2020-01-12"},
        ],
    )
    trends = {date(2020, 1, 5): (4, 2), date(2020, 1, 12): (6, 3)}

    rows = p1c.weekly_rows(trends=trends, finds=finds)

    assert [(row["week_start"], row["reliable_finds"], row["timing_finds"], row["all_finds"]) for row in rows] == [
        (date(2020, 1, 5), 2, 1, 2),
        (date(2020, 1, 12), 0, 1, 1),
    ]
    assert rows[0]["year"] == 2020
    assert rows[0]["porcini_searches"] == 4
    assert rows[1]["funghi_porcini_searches"] == 3


def test_compare_keeps_only_years_with_enough_finds() -> None:
    finds = {
        f"a{index}": {"date": date(2020, 9, 1) + timedelta(days=index), "reliable": True, "timing": False}
        for index in range(5)
    }
    finds["lone"] = {"date": date(2021, 9, 1), "reliable": True, "timing": False}
    trends = {date(2020, 1, 5) + timedelta(weeks=index): (index % 7, index % 5) for index in range(120)}
    rows = p1c.weekly_rows(trends=trends, finds=finds)

    by_year, summaries, _ = p1c.compare(
        rows=rows, finds=finds, min_finds_per_year=5, lines_up_days=14, max_shift_weeks=2, repeats=20, seed=1
    )

    assert {row["year"] for row in by_year} == {2020}
    assert [summary["years_compared"] for summary in summaries] == [1, 1]


def test_spearman_follows_ranks_and_is_empty_for_a_constant_series() -> None:
    assert p1c.spearman(first=[1, 2, 3, 4], second=[10, 100, 1000, 10000]) == pytest.approx(1.0)
    assert p1c.spearman(first=[1, 2, 3, 4], second=[4, 3, 2, 1]) == pytest.approx(-1.0)
    assert p1c.spearman(first=[1, 2, 3, 4], second=[5, 5, 5, 5]) is None
    assert p1c.spearman(first=[0, 0, 0, 0], second=[1, 2, 3, 4]) is None


def test_year_correlation_is_empty_when_the_finds_are_constant() -> None:
    rows = weekly(signs=[1, 5, 2, 8, 3], finds=[0, 0, 0, 0, 0])

    assert p1c.year_correlation(rows=rows, sign="porcini_searches", year=2020) is None


def test_calendar_guess_leaves_out_the_year_itself() -> None:
    # All three weeks are ISO week 2 of their year.
    rows = [
        {"week_start": first, "year": year, "porcini_searches": value, "all_finds": 0}
        for first, year, value in (
            (date(2020, 1, 5), 2020, 100),
            (date(2021, 1, 10), 2021, 10),
            (date(2022, 1, 9), 2022, 30),
        )
    ]

    guess = p1c.calendar_guess(rows=rows, sign="porcini_searches", year=2020)

    assert guess == {date(2020, 1, 5): 20}


def test_peak_week_looks_only_between_june_and_november() -> None:
    rows = weekly(signs=[99, 5, 7, 6, 99], finds=[0] * 5, first=date(2020, 5, 17))
    # Weeks start 17 May, 24 May, 31 May, 7 June, 14 June. The first three are before 1 June.
    rows = [row for row in rows if row["week_start"] >= date(2020, 5, 31)]

    assert p1c.peak_week(rows=rows, sign="porcini_searches", year=2020) == date(2020, 6, 14)


def test_sign_running_two_weeks_after_the_finds_gives_plus_14_days() -> None:
    finds = [0, 1, 3, 9, 20, 9, 3, 1, 0, 0, 0, 0, 0, 0]
    signs = [0, 0] + finds[:-2]
    rows = weekly(signs=signs, finds=finds, first=date(2020, 8, 2))
    finds_dict = {}
    for row in rows:
        for number in range(row["all_finds"]):
            finds_dict[f"{row['week_start']}-{number}"] = {
                "date": row["week_start"] + timedelta(days=3),
                "reliable": True,
                "timing": False,
            }

    by_year, summaries, shifts = p1c.compare(
        rows=rows, finds=finds_dict, min_finds_per_year=5, lines_up_days=14, max_shift_weeks=4, repeats=50, seed=3
    )

    sign_row = next(row for row in by_year if row["sign"] == "porcini_searches")
    assert sign_row["peak_minus_median_days"] == 14
    assert sign_row["lines_up"] is True
    assert summaries[0]["best_shift_days"] == 14
    assert summaries[0]["median_peak_minus_median_days"] == 14
    curve = {row["shift_days"]: row["mean_correlation"] for row in shifts if row["sign"] == "porcini_searches"}
    assert curve[14] == pytest.approx(1.0)
    assert min(curve) == -28 and max(curve) == 28


def test_missing_find_table_stops_with_a_clear_error(tmp_path: Path) -> None:
    from micometeo.context import RunContext

    context = RunContext(
        config={
            "finds_path": str(tmp_path / "finds.parquet"),
            "timing_finds_path": str(tmp_path / "timing_finds.parquet"),
            "exports": [],
        },
        seed=1,
        run_id="test",
        raw_dir=tmp_path / "raw",
        output_dir=tmp_path / "out",
        state_path=tmp_path / "state.json",
    )

    with pytest.raises(FileNotFoundError, match="Find table not found"):
        p1c.run(context)


def test_year_that_peaks_with_its_finds_beats_a_calendar_that_peaks_six_weeks_later() -> None:
    first = date(2020, 8, 2)
    rows = weekly(signs=[100 if index == 5 else 0 for index in range(14)], finds=[0] * 14, first=first)
    for year in (2021, 2022):
        for index, row in enumerate(weekly(signs=[0] * 14, finds=[0] * 14, first=first)):
            number = (row["week_start"] + timedelta(days=3)).isocalendar().week
            rows.append(
                {
                    **row,
                    "week_start": date.fromisocalendar(year, number, 1) - timedelta(days=1),
                    "year": year,
                    "porcini_searches": 100 if index == 11 else 0,
                }
            )
    dates = [date(2020, 9, 9)] * 5

    row = p1c.year_row(rows=rows, sign="porcini_searches", year=2020, dates=dates, lines_up_days=14)

    assert row["peak_minus_median_days"] == 0
    assert row["lines_up"] is True
    assert row["calendar_peak_minus_median_days"] == 42
    assert row["calendar_lines_up"] is False
