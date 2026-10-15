"""P1c: compare weekly Google Trends interest in porcini in Tuscany with weekly porcini finds."""

import csv
import random
import statistics
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyarrow.parquet as pq

from sporameteo.context import RunContext
from sporameteo.finds.counts import in_stage

ROOT = Path(__file__).resolve().parent.parent.parent
SIGNS = ["porcini_searches", "funghi_porcini_searches"]
FIRST_WEEK = date(2014, 12, 28)
LAST_WEEK = date(2026, 10, 4)
PEAK_START = (6, 1)
PEAK_END = (11, 30)
WEEKLY_COLUMNS = [
    "week_start",
    "year",
    *SIGNS,
    "reliable_finds",
    "timing_finds",
    "all_finds",
]
BY_YEAR_COLUMNS = [
    "sign",
    "year",
    "finds",
    "correlation",
    "calendar_correlation",
    "peak_week",
    "median_find_date",
    "peak_minus_median_days",
    "lines_up",
    "calendar_peak_week",
    "calendar_peak_minus_median_days",
    "calendar_lines_up",
]
SUMMARY_COLUMNS = [
    "sign",
    "years_compared",
    "years_lining_up",
    "calendar_years_lining_up",
    "mean_correlation",
    "mean_correlation_low",
    "mean_correlation_high",
    "mean_calendar_correlation",
    "mean_calendar_correlation_low",
    "mean_calendar_correlation_high",
    "best_shift_days",
    "best_shift_low_days",
    "best_shift_high_days",
    "median_peak_minus_median_days",
    "median_abs_peak_gap_days",
    "median_abs_calendar_peak_gap_days",
]
SHIFT_COLUMNS = ["sign", "shift_days", "mean_correlation"]


def write_csv(*, rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def resolve(*, path: str | Path) -> Path:
    """Return an absolute path, reading relative paths from the repository root."""
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def parse_export(*, path: Path) -> dict[date, tuple[int, int]]:
    """Read one Trends export into week start dates with the two search values.

    The value "<1" means less than one and is read as 0.
    """
    weeks: dict[date, tuple[int, int]] = {}
    started = False
    for row in csv.reader(path.read_text(encoding="utf-8-sig").splitlines()):
        if not started:
            started = bool(row) and row[0] == "Week"
            continue
        if not row:
            continue
        values = [0 if cell.strip() == "<1" else int(cell) for cell in row[1:3]]
        weeks[date.fromisoformat(row[0])] = (values[0], values[1])
    return weeks


def merge_exports(*, exports: list[dict[date, tuple[int, int]]]) -> dict[date, tuple[int, int]]:
    """Join the exports in date order. Where two files share a week, the earlier file wins."""
    merged: dict[date, tuple[int, int]] = {}
    for export in exports:
        for week, values in export.items():
            merged.setdefault(week, values)
    return merged


def week_start(*, day: date) -> date:
    """Return the Sunday that starts the week of a day."""
    return day - timedelta(days=(day.weekday() + 1) % 7)


def week_year(*, week: date) -> int:
    """Return the year of the Thursday in a week."""
    return (week + timedelta(days=3)).year


def read_table(*, path: Path, columns: list[str]) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Find table not found: {path}")
    return pq.read_table(path, columns=columns).to_pylist()


def collect_finds(
    *, reliable: list[dict[str, Any]], timing: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Keep home finds with a day date, once per record_id, flagged by the table they came from."""
    finds: dict[str, dict[str, Any]] = {}
    for rows, kind in ((reliable, "reliable"), (timing, "timing")):
        for row in rows:
            if row["area"] != "home" or row.get("date_precision", "day") != "day":
                continue
            if kind == "reliable" and not in_stage(record=row, stage="eligible"):
                continue
            try:
                day = date.fromisoformat(row["event_date"])
            except (TypeError, ValueError):
                continue
            find = finds.setdefault(row["record_id"], {"date": day, "reliable": False, "timing": False})
            find[kind] = True
    return finds


def weekly_rows(
    *, trends: dict[date, tuple[int, int]], finds: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Build one row per Trends week with the search values and the three find counts."""
    reliable: Counter[date] = Counter()
    timing: Counter[date] = Counter()
    both: Counter[date] = Counter()
    for find in finds.values():
        week = week_start(day=find["date"])
        reliable[week] += find["reliable"]
        timing[week] += find["timing"]
        both[week] += 1
    rows = []
    for week in sorted(trends):
        if not FIRST_WEEK <= week <= LAST_WEEK:
            continue
        rows.append(
            {
                "week_start": week,
                "year": week_year(week=week),
                "porcini_searches": trends[week][0],
                "funghi_porcini_searches": trends[week][1],
                "reliable_finds": reliable[week],
                "timing_finds": timing[week],
                "all_finds": both[week],
            }
        )
    return rows


def rank(*, values: list[float]) -> np.ndarray:
    """Rank values from 1, giving tied values the average of their ranks."""
    array = np.asarray(values, dtype=float)
    order = np.argsort(array, kind="stable")
    ranks = np.empty(len(array))
    position = 0
    while position < len(array):
        end = position
        while end + 1 < len(array) and array[order[end + 1]] == array[order[position]]:
            end += 1
        ranks[order[position : end + 1]] = (position + end) / 2 + 1
        position = end + 1
    return ranks


def spearman(*, first: list[float], second: list[float]) -> float | None:
    """Return the rank correlation, or None when it is undefined."""
    if len(first) < 3 or len(first) != len(second):
        return None
    if len(set(first)) < 2 or len(set(second)) < 2:
        return None
    return float(np.corrcoef(rank(values=first), rank(values=second))[0, 1])


def iso_week(*, week: date) -> int:
    # The ISO week of the Thursday matches week_year, so a week never mixes two years.
    return (week + timedelta(days=3)).isocalendar().week


def calendar_guess(*, rows: list[dict[str, Any]], sign: str, year: int) -> dict[date, float]:
    """For each week of a year, average the sign in the same ISO week of all other years.

    Week 53 has no other year in most cases, so it uses week 52.
    """
    by_week: dict[int, list[float]] = {}
    for row in rows:
        if row["year"] != year:
            by_week.setdefault(iso_week(week=row["week_start"]), []).append(row[sign])
    guess = {}
    for row in rows:
        if row["year"] == year:
            number = iso_week(week=row["week_start"])
            values = by_week.get(number) or by_week.get(52)
            if values:
                guess[row["week_start"]] = statistics.mean(values)
    return guess


def year_correlation(
    *, rows: list[dict[str, Any]], sign: str, year: int, shift_weeks: int = 0
) -> float | None:
    """Correlate the finds of a year with the sign shifted by shift_weeks weeks later."""
    sign_by_week = {row["week_start"]: row[sign] for row in rows}
    finds, signs = [], []
    for row in rows:
        if row["year"] != year:
            continue
        later = row["week_start"] + timedelta(weeks=shift_weeks)
        if later in sign_by_week:
            finds.append(row["all_finds"])
            signs.append(sign_by_week[later])
    return spearman(first=signs, second=finds)


def find_year_dates(*, finds: dict[str, dict[str, Any]]) -> dict[int, list[date]]:
    """Group find dates by the year of their week."""
    grouped: dict[int, list[date]] = {}
    for find in finds.values():
        week = week_start(day=find["date"])
        if FIRST_WEEK <= week <= LAST_WEEK:
            grouped.setdefault(week_year(week=week), []).append(find["date"])
    return grouped


def peak_week(*, rows: list[dict[str, Any]], sign: str, year: int) -> date | None:
    """Return the first week with the highest sign value between 1 June and 30 November."""
    return highest_week(values={row["week_start"]: row[sign] for row in rows if row["year"] == year})


def highest_week(*, values: dict[date, float]) -> date | None:
    """Return the first week with the highest value between 1 June and 30 November."""
    candidates = {
        week: value for week, value in values.items() if PEAK_START <= (week.month, week.day) <= PEAK_END
    }
    if not candidates:
        return None
    return max(candidates, key=lambda week: (candidates[week], -week.toordinal()))


def year_row(
    *,
    rows: list[dict[str, Any]],
    sign: str,
    year: int,
    dates: list[date],
    lines_up_days: int,
) -> dict[str, Any]:
    guess = calendar_guess(rows=rows, sign=sign, year=year)
    weeks = [row for row in rows if row["year"] == year and row["week_start"] in guess]
    calendar = spearman(
        first=[guess[row["week_start"]] for row in weeks],
        second=[row["all_finds"] for row in weeks],
    )
    peak = peak_week(rows=rows, sign=sign, year=year)
    median_day = date.fromordinal(round(statistics.median(day.toordinal() for day in dates)))
    difference = (peak + timedelta(days=3) - median_day).days if peak else None
    calendar_peak = highest_week(values=guess)
    calendar_difference = (
        (calendar_peak + timedelta(days=3) - median_day).days if calendar_peak else None
    )
    return {
        "sign": sign,
        "year": year,
        "finds": len(dates),
        "correlation": year_correlation(rows=rows, sign=sign, year=year),
        "calendar_correlation": calendar,
        "peak_week": peak,
        "median_find_date": median_day,
        "peak_minus_median_days": difference,
        "lines_up": difference is not None and abs(difference) <= lines_up_days,
        "calendar_peak_week": calendar_peak,
        "calendar_peak_minus_median_days": calendar_difference,
        "calendar_lines_up": calendar_difference is not None and abs(calendar_difference) <= lines_up_days,
    }


def percentile_range(*, values: list[float]) -> tuple[float | None, float | None]:
    """Return the 2.5 and 97.5 percentiles of the sorted values."""
    if not values:
        return None, None
    values = sorted(values)
    low, high = int(len(values) * 0.025), int(len(values) * 0.975) - 1
    return values[low], values[max(low, high)]


def mean_without_gaps(*, values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return statistics.mean(present) if present else None


def best_shift(*, curve: dict[int, float | None]) -> int | None:
    """Return the shift with the highest mean correlation, the smaller shift winning a tie."""
    present = {shift: value for shift, value in curve.items() if value is not None}
    if not present:
        return None
    return max(present, key=lambda shift: (present[shift], -abs(shift)))


def summarise_sign(
    *,
    sign: str,
    year_rows: list[dict[str, Any]],
    shift_values: dict[int, list[float | None]],
    rng: random.Random,
    repeats: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Summarise one sign over its compared years, with uncertainty ranges from redrawing years."""
    count = len(year_rows)
    correlations: list[float | None] = [row["correlation"] for row in year_rows]
    calendars: list[float | None] = [row["calendar_correlation"] for row in year_rows]
    differences = [row["peak_minus_median_days"] for row in year_rows if row["peak_minus_median_days"] is not None]
    calendar_differences = [
        row["calendar_peak_minus_median_days"]
        for row in year_rows
        if row["calendar_peak_minus_median_days"] is not None
    ]
    means, calendar_means, bests = [], [], []
    for _ in range(repeats if count else 0):
        picks = [rng.randrange(count) for _ in range(count)]
        mean = mean_without_gaps(values=[correlations[pick] for pick in picks])
        calendar = mean_without_gaps(values=[calendars[pick] for pick in picks])
        if mean is not None:
            means.append(mean)
        if calendar is not None:
            calendar_means.append(calendar)
        best = best_shift(
            curve={
                shift: mean_without_gaps(values=[values[pick] for pick in picks])
                for shift, values in shift_values.items()
            }
        )
        if best is not None:
            bests.append(best * 7)
    curve = {shift: mean_without_gaps(values=values) for shift, values in shift_values.items()}
    chosen = best_shift(curve=curve)
    mean_low, mean_high = percentile_range(values=means)
    calendar_low, calendar_high = percentile_range(values=calendar_means)
    best_low, best_high = percentile_range(values=bests)
    summary = {
        "sign": sign,
        "years_compared": count,
        "years_lining_up": sum(row["lines_up"] for row in year_rows),
        "calendar_years_lining_up": sum(row["calendar_lines_up"] for row in year_rows),
        "mean_correlation":mean_without_gaps(values=correlations),
        "mean_correlation_low": mean_low,
        "mean_correlation_high": mean_high,
        "mean_calendar_correlation": mean_without_gaps(values=calendars),
        "mean_calendar_correlation_low": calendar_low,
        "mean_calendar_correlation_high": calendar_high,
        "best_shift_days": None if chosen is None else chosen * 7,
        "best_shift_low_days": best_low,
        "best_shift_high_days": best_high,
        "median_peak_minus_median_days": statistics.median(differences) if differences else None,
        "median_abs_peak_gap_days": statistics.median(abs(gap) for gap in differences) if differences else None,
        "median_abs_calendar_peak_gap_days": (
            statistics.median(abs(gap) for gap in calendar_differences) if calendar_differences else None
        ),
    }
    shifts = [
        {"sign": sign, "shift_days": shift * 7, "mean_correlation": value} for shift, value in curve.items()
    ]
    return summary, shifts


def compare(
    *,
    rows: list[dict[str, Any]],
    finds: dict[str, dict[str, Any]],
    min_finds_per_year: int,
    lines_up_days: int,
    max_shift_weeks: int,
    repeats: int,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return the per-year, summary and shift rows for both signs."""
    dates = find_year_dates(finds=finds)
    years = sorted(year for year, days in dates.items() if len(days) >= min_finds_per_year)
    rng = random.Random(seed)
    by_year, summaries, shifts = [], [], []
    for sign in SIGNS:
        year_rows = [
            year_row(rows=rows, sign=sign, year=year, dates=dates[year], lines_up_days=lines_up_days)
            for year in years
        ]
        shift_values = {
            shift: [year_correlation(rows=rows, sign=sign, year=year, shift_weeks=shift) for year in years]
            for shift in range(-max_shift_weeks, max_shift_weeks + 1)
        }
        summary, curve = summarise_sign(
            sign=sign, year_rows=year_rows, shift_values=shift_values, rng=rng, repeats=repeats
        )
        by_year += year_rows
        summaries.append(summary)
        shifts += curve
    return by_year, summaries, shifts


def plot_years(*, rows: list[dict[str, Any]], path: Path) -> None:
    """Plot porcini searches as a line and weekly finds as bars, one panel per year.

    Only "porcini" is drawn to keep the panels readable. "funghi porcini" is in the CSV files.
    """
    figure, axes = plt.subplots(4, 3, figsize=(14, 12))
    for axis, year in zip(axes.flat, range(2015, 2027)):
        weeks = [row for row in rows if row["year"] == year]
        days = [row["week_start"] for row in weeks]
        finds = [row["all_finds"] for row in weeks]
        axis.plot(days, [row["porcini_searches"] for row in weeks], color="tab:blue", linewidth=1.2)
        axis.set_ylim(0, 100)
        axis.set_title(f"{year}: {sum(finds)} finds")
        axis.tick_params(axis="x", labelsize=7, rotation=45)
        finds_axis = axis.twinx()
        finds_axis.bar(days, finds, width=5, color="tab:orange", alpha=0.7)
        finds_axis.set_ylim(0, max(max(finds, default=0), 1) * 1.1)
        if axis in axes[:, 0]:
            axis.set_ylabel("Porcini searches", color="tab:blue")
        if axis in axes[:, -1]:
            finds_axis.set_ylabel("Finds per week", color="tab:orange")
    figure.tight_layout()
    figure.savefig(path, dpi=120)
    plt.close(figure)


def format_row(*, row: dict[str, Any]) -> dict[str, Any]:
    """Round numbers for the CSV files. Empty values stay empty."""
    return {
        key: round(value, 3) if isinstance(value, float) else ("" if value is None else value)
        for key, value in row.items()
    }


def run(context: RunContext) -> None:
    """Read the Trends exports and the finds, compare them week by week and write the CSV files and plot."""
    settings = context.config
    reports_dir = resolve(path=settings.get("reports_dir") or "reports")
    finds_path = resolve(path=settings["finds_path"])
    timing_path = resolve(path=settings["timing_finds_path"])
    for path in (finds_path, timing_path):
        if not path.is_file():
            raise FileNotFoundError(f"Find table not found: {path}")

    exports = []
    for export in settings["exports"]:
        path = resolve(path=export["path"])
        context.add_source(
            name=f"Google Trends export {Path(export['path']).name}",
            url=export["url"],
            licence="Google Trends terms of service",
            version="website export",
            downloaded_at=settings["download_date"],
            query={
                "terms": settings["search_terms"],
                "area": settings["search_area"],
                "start": export["start"],
                "end": export["end"],
                "downloaded_by": "CSV button on the Trends website, in a browser",
            },
        )
        context.add_input(path)
        exports.append(parse_export(path=path))
    context.add_input(finds_path)
    context.add_input(timing_path)

    reliable = read_table(
        path=finds_path,
        columns=["record_id", "area", "event_date", "date_precision", "duplicate_rule", "failed_filter"],
    )
    timing = read_table(path=timing_path, columns=["record_id", "area", "event_date"])
    finds = collect_finds(reliable=reliable, timing=timing)
    rows = weekly_rows(trends=merge_exports(exports=exports), finds=finds)
    by_year, summaries, shifts = compare(
        rows=rows,
        finds=finds,
        min_finds_per_year=settings["min_finds_per_year"],
        lines_up_days=settings["lines_up_days"],
        max_shift_weeks=settings["max_shift_weeks"],
        repeats=settings["repeats"],
        seed=context.seed,
    )

    outputs = {
        "p1c_weekly_series.csv": ([format_row(row=row) for row in rows], WEEKLY_COLUMNS),
        "p1c_by_year.csv": ([format_row(row=row) for row in by_year], BY_YEAR_COLUMNS),
        "p1c_summary.csv": ([format_row(row=row) for row in summaries], SUMMARY_COLUMNS),
        "p1c_shifts.csv": ([format_row(row=row) for row in shifts], SHIFT_COLUMNS),
    }
    for name, (output_rows, columns) in outputs.items():
        write_csv(rows=output_rows, columns=columns, path=reports_dir / name)
        context.add_output(reports_dir / name)
    plot_path = reports_dir / "p1c_flush_signs.png"
    plot_years(rows=rows, path=plot_path)
    context.add_output(plot_path)
