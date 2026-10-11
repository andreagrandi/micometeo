"""P4b: check the hand-written weather rules on daily porcini counts that include days with none."""

import csv
import io
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.csv as pacsv

from micometeo.benchmark import features, models, scoring
from micometeo.config import load_config
from micometeo.context import RunContext
from micometeo.habitat.grid import read_download_note, write_download_note

ROOT = Path(__file__).resolve().parent.parent.parent
ZIP_NAME = "Boletus_fruiting_triggers-V1.2.zip"
SET_NAME = "bielefeld"
SCORE_COLUMNS = ["model", "cases", "groups", "top10", "top10_low", "top10_high", "top20", "top20_low", "top20_high"]
RULE_COLUMNS = ["rule", "porcini_days_meeting", "other_days_meeting"]


def write_csv(*, rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def read_counts(*, zip_path: Path, data_file: str, site: str) -> tuple[np.ndarray, np.ndarray]:
    """Return the dates and porcini counts of one site, read from the zip. The file is parsed as plain data."""
    with zipfile.ZipFile(zip_path) as archive:
        names = [name for name in archive.namelist() if name.endswith("/" + data_file)]
        if len(names) != 1:
            raise ValueError(f"Expected one {data_file} in the zip, found {names}")
        content = archive.read(names[0])
    table = pacsv.read_csv(
        io.BytesIO(content),
        convert_options=pacsv.ConvertOptions(
            column_types={"Date": pa.string(), "Mnb": pa.float64(), "site": pa.string()},
            include_columns=["Date", "Mnb", "site"],
        ),
    )
    chosen = table["site"].to_numpy(zero_copy_only=False) == site
    dates = table["Date"].to_numpy(zero_copy_only=False)[chosen].astype("datetime64[D]")
    return dates, table["Mnb"].to_numpy(zero_copy_only=False)[chosen]


def season_mask(*, dates: np.ndarray, start: str, end: str) -> np.ndarray:
    """Return a mask of the dates between two month-day values in each year, both days included."""
    month_day = np.array([text[5:] for text in dates.astype(str)])
    return (month_day >= start) & (month_day <= end)


def weather_for_dates(*, dates: np.ndarray, series: features.DailySeries) -> dict[str, np.ndarray]:
    """Return the six weather columns for each date, from the days before it."""
    days = dates.astype("int64")
    result = {}
    for window in features.WINDOW_DAYS:
        result[f"rain_{window}d_mm"] = features.window_values(series=series, day_numbers=days, days=window, kind="rain")
        result[f"temp_{window}d_c"] = features.window_values(series=series, day_numbers=days, days=window, kind="temp")
    return result


def build_day_table(*, dates: np.ndarray, counts: np.ndarray, weather: dict[str, np.ndarray]) -> scoring.Table:
    """Return a table where each porcini day is a case and the days without porcini of the same year are its comparison days.

    Days with a NaN in any weather column are left out. Habitat columns are 0, since the place does not change.
    """
    complete = np.all([~np.isnan(values) for values in weather.values()], axis=0)
    years = dates.astype("datetime64[Y]").astype(int) + 1970
    rows: list[tuple[int, int, str]] = []
    for year in np.unique(years):
        in_year = np.nonzero(complete & (years == year))[0]
        porcini = in_year[counts[in_year] > 0]
        others = in_year[counts[in_year] <= 0]
        for case in porcini:
            rows.append((case, case, "find"))
            rows.extend((case, other, "other_day") for other in others)
    case_index = np.array([row[0] for row in rows], dtype=int)
    day_index = np.array([row[1] for row in rows], dtype=int)
    size = len(rows)
    table: scoring.Table = {
        "case_id": np.array([str(dates[index]) for index in case_index], dtype=str),
        "set": np.full(size, SET_NAME),
        "block_id": np.full(size, SET_NAME),
        "year": years[case_index],
        "assessment_date": dates[day_index].astype(str),
        "point_kind": np.array([row[2] for row in rows], dtype=str),
    }
    for column in scoring.HABITAT_COLUMNS:
        table[column] = np.zeros(size)
    for column, values in weather.items():
        table[column] = values[day_index]
    return table


def rule_label(*, condition: dict[str, Any]) -> str:
    return f"{condition['column']} {condition['op']} {condition['value']:g}"


def rule_share_rows(*, table: scoring.Table, conditions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return, for each rule and the rain guess, the share of porcini days and of days without porcini that meet it.

    Each day counts once, whichever case it is compared in.
    """
    kinds = table["point_kind"]
    chosen = []
    for kind in ("find", "other_day"):
        selected = np.nonzero(kinds == kind)[0]
        chosen.append(selected[np.unique(table["assessment_date"][selected], return_index=True)[1]])
    chosen_all = np.concatenate(chosen)
    is_porcini = np.arange(len(chosen_all)) < len(chosen[0])
    rows = []
    for condition in conditions:
        meets = models.rule_values(table={key: values[chosen_all] for key, values in table.items()}, conditions=[condition]) > 0
        rows.append(
            {
                "rule": rule_label(condition=condition),
                "porcini_days_meeting": round(float(meets[is_porcini].mean()), 3),
                "other_days_meeting": round(float(meets[~is_porcini].mean()), 3),
            }
        )
    return rows


def download_zip(*, context: RunContext, url: str) -> Path:
    """Save the Zenodo zip unless it is saved, and record it in the run."""
    path = context.raw_dir / ZIP_NAME
    if not path.exists():
        context.raw_dir.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=300) as response:
            content = response.read()
        if content[:2] != b"PK":
            raise ValueError(f"Zenodo did not return a zip file: {content[:200]!r}")
        path.write_bytes(content)
        write_download_note(path=path, details={"url": url, "query": {"record": "20591123"}})
    note = read_download_note(path=path)
    context.add_source(
        name="Daily porcini counts, Brejon Lamartiniere and Hoffman",
        url=note["url"],
        licence="CC BY 4.0",
        version="Zenodo record 20591123, V1.2",
        downloaded_at=note["downloaded_at"],
        query=note["query"],
    )
    context.add_input(path)
    return path


def run(context: RunContext) -> None:
    """Score the weather rules on the days of the German forest and write the report files."""
    settings = context.config
    zip_path = download_zip(context=context, url=settings["data_url"])
    dates, counts = read_counts(zip_path=zip_path, data_file=settings["data_file"], site=settings["site"])
    chosen = season_mask(dates=dates, start=settings["season_start"], end=settings["season_end"])
    dates, counts = dates[chosen], counts[chosen]

    weather_dir = ROOT / settings["weather_dir"]
    cell = features.era5_cell(latitude=settings["latitude"], longitude=settings["longitude"])
    path = features.era5_path(cell=cell, weather_dir=weather_dir)
    features.fetch_cell(cell=cell, weather_dir=weather_dir, end_date=settings["weather_end_date"], start_date=settings["weather_start_date"])
    series = features.read_cell_file(path=path)
    if series.first_day > features.day_number(text=settings["weather_start_date"]):
        raise ValueError(f"{path} starts too late for the 2015 season. Fetch this cell under another name.")
    context.add_source(
        **features.source_record(
            name=f"ERA5 hourly time series {path.name}",
            url=features.ERA5_URL,
            licence=features.ERA5_LICENCE,
            version="ERA5 reconstructed past weather, hourly, one 0.25 degree cell",
            note=read_download_note(path=path),
        )
    )
    # No height correction: the forest lies in lowland, so the ERA5 cell height is close to the forest height.
    weather = weather_for_dates(dates=dates, series=series)
    table = build_day_table(dates=dates, counts=counts, weather=weather)

    conditions = load_config(path=ROOT / settings["rules_config"]).settings["rules_weather"]
    predictions = {
        "random": models.random_values(table=table, seed=context.seed),
        "rain_30d_mm": table["rain_30d_mm"].astype(float),
        "rules_weather": models.rule_values(table=table, conditions=conditions),
    }
    for condition in conditions:
        predictions[f"only {rule_label(condition=condition)}"] = models.rule_values(table=table, conditions=[condition])
    result = scoring.score_models(table=table, predictions=predictions, redraws=settings["redraws"], seed=context.seed)

    entry = result["scores"][(SET_NAME, "other_day")]
    score_rows = [
        {
            "model": model,
            "cases": entry["n_cases"],
            "groups": entry["n_groups"],
            **{
                f"{share}{suffix}": round(value, 3)
                for share in ("top10", "top20")
                for suffix, value in (("", values[share]), ("_low", values[f"{share}_range"][0]), ("_high", values[f"{share}_range"][1]))
            },
        }
        for model, values in entry["models"].items()
    ]
    rule_rows = rule_share_rows(table=table, conditions=conditions)

    reports_dir = ROOT / settings["reports_dir"]
    for filename, rows, columns in (
        ("p4b_bielefeld_scores.csv", score_rows, SCORE_COLUMNS),
        ("p4b_bielefeld_rules.csv", rule_rows, RULE_COLUMNS),
    ):
        report = reports_dir / filename
        write_csv(rows=rows, columns=columns, path=report)
        context.add_output(report)
        print(filename)
        for row in rows:
            print("  " + " | ".join(str(row[column]) for column in columns))
