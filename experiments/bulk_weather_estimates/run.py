"""Bulk weather estimates: compare Tuscany estimates from file weather with the published estimates.

The script reads public Open-Meteo files and the local database read-only. It calls no API and writes nothing to the database.
"""

import bisect
import csv
import importlib.util
import json
import math
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from sporameteo.context import RunContext
from sporameteo.weather.evapotranspiration import (
    _sun_position,
    hourly_reference_evapotranspiration,
    top_of_atmosphere_radiation,
)

ROOT = Path(__file__).resolve().parent.parent.parent


def _load_bulk_weather() -> Any:
    """Load the file reader helpers of the bulk_weather experiment."""
    path = ROOT / "experiments" / "bulk_weather" / "run.py"
    spec = importlib.util.spec_from_file_location("bulk_weather_run", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["bulk_weather_run"] = module
    spec.loader.exec_module(module)
    return module


bw = _load_bulk_weather()
db = SimpleNamespace()

IFS_PATH = "data_run/ecmwf_ifs"
ICON_PATH = "data_run/italia_meteo_arpae_icon_2i"
ICON_HEIGHT_FILE = "data/italia_meteo_arpae_icon_2i/static/HSURF.om"
ICON_GRID = {"nx": 761, "ny": 761, "lat_min": 33.7, "lon_min": 3.0, "dx": 0.025, "dy": 0.02}
IFS_VARIABLES = (
    "precipitation",
    "temperature_2m",
    "soil_moisture_0_to_7cm",
    "soil_temperature_0_to_7cm",
    "dew_point_2m",
    "shortwave_radiation",
    "wind_u_component_10m",
    "wind_v_component_10m",
)
# Open-Meteo fills the hours between steps by variable: totals are spread, radiation follows the sun, the rest is a smooth curve.
IFS_RULES = {"precipitation": "sum", "shortwave_radiation": "solar"}
ICON_VARIABLES = ("precipitation", "temperature_2m", "relative_humidity_2m", "shortwave_radiation", "wind_speed_10m")
# Amounts cover the hour before their time stamp. Everything else is a value at the time stamp.
AMOUNTS = ("precipitation", "shortwave_radiation")
HEIGHT_CORRECTED = ("temperature_2m", "dew_point_2m", "soil_temperature_0_to_7cm")
LAPSE_RATE = 0.0065
SOLAR_CONSTANT = 1367.7
DAILY_VARIABLES = ("precipitation", "temperature", "soil_moisture", "soil_temperature", "et0")
TARGET_DAYS = 8
VARIANTS = ("ifs", "icon_2i")

DAYS_COLUMNS = [
    "assessment_date",
    "variant",
    "target_date",
    "days_ahead",
    "squares",
    "squares_compared",
    "squares_one_side_unavailable",
    "squares_both_unavailable",
    "median_abs_difference_points",
    "p90_abs_difference_points",
    "max_abs_difference_points",
    "mean_signed_difference_points",
    "share_5_points_or_more",
]
CELL_COLUMNS = [
    "assessment_date",
    "variant",
    "cell_key",
    "rain_past_30_days_files_mm",
    "rain_past_30_days_stored_mm",
    "rain_past_30_days_difference_mm",
    "rain_8_days_files_mm",
    "rain_8_days_stored_mm",
    "rain_8_days_difference_mm",
    "soil_moisture_past_30_days_files",
    "soil_moisture_past_30_days_stored",
    "soil_moisture_past_30_days_difference",
    "soil_moisture_8_days_files",
    "soil_moisture_8_days_stored",
    "soil_moisture_8_days_difference",
    "evapotranspiration_past_30_days_difference_mm",
    "mean_temperature_8_days_difference_c",
    "squares_compared",
    "median_abs_estimate_difference_points",
    "max_abs_estimate_difference_points",
]
INTERPOLATION_COLUMNS = ["variable", "part", "rule", "values_compared", "median_abs_gap", "max_abs_gap"]


# ---------------------------------------------------------------------------
# Database, read-only
# ---------------------------------------------------------------------------


def start_django() -> None:
    """Start Django and make every query of this session read-only."""
    application = ROOT / "apps" / "application"
    if str(application) not in sys.path:
        sys.path.insert(0, str(application))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")

    from estimate_updates import services as estimate_services
    from estimate_updates.contracts import decode_result_bytes, encode_result_bytes
    from estimate_updates.host_trees import saved_host_trees
    from estimate_updates.models import (
        EstimateResult,
        EstimateUpdate,
        ForecastRun,
        ForecastRunCell,
        PublishedForecastRun,
    )
    from national_forest.models import ForestBuild
    from national_terrain.models import TerrainCell
    from sporameteo.forecast_method import CURRENT_METHOD, calculate_forecast
    from weather_summaries import services as summary_services
    from weather_summaries.aggregation import aggregate_hourly
    from weather_summaries.models import (
        WeatherDaily,
        WeatherSnapshot,
        WeatherSnapshotDay,
        WeatherSummary,
    )

    db.connection = connection
    db.estimate_services = estimate_services
    db.summary_services = summary_services
    db.decode_result_bytes = decode_result_bytes
    db.encode_result_bytes = encode_result_bytes
    db.saved_host_trees = saved_host_trees
    db.EstimateResult = EstimateResult
    db.EstimateUpdate = EstimateUpdate
    db.ForecastRun = ForecastRun
    db.ForecastRunCell = ForecastRunCell
    db.PublishedForecastRun = PublishedForecastRun
    db.ForestBuild = ForestBuild
    db.TerrainCell = TerrainCell
    db.CURRENT_METHOD = CURRENT_METHOD
    db.calculate_forecast = calculate_forecast
    db.aggregate_hourly = aggregate_hourly
    db.WeatherDaily = WeatherDaily
    db.WeatherSnapshot = WeatherSnapshot
    db.WeatherSnapshotDay = WeatherSnapshotDay
    db.WeatherSummary = WeatherSummary


def assert_read_only() -> None:
    """Fail if the database session is not read-only."""
    with db.connection.cursor() as cursor:
        cursor.execute("SHOW transaction_read_only")
        if cursor.fetchone()[0] != "on":
            raise RuntimeError("The database session is not read-only.")


def find_published_run(*, assessment_date: date, region_code: str) -> Any:
    """Return the one published run of a region and date."""
    runs = list(db.ForecastRun.objects.filter(region_code=region_code, assessment_date=assessment_date, status="published"))
    if len(runs) != 1:
        raise RuntimeError(f"Expected one published run for {region_code} on {assessment_date}, found {len(runs)}.")
    return runs[0]


def database_state(*, region_code: str, run_ids: list[Any]) -> dict[str, Any]:
    """Return the published run pointers, the compared runs and the row counts, as text."""
    published = db.PublishedForecastRun.objects.get(region_code=region_code)
    runs = db.ForecastRun.objects.filter(id__in=run_ids).order_by("assessment_date")
    return {
        "published_current_run_id": str(published.current_run_id),
        "published_previous_run_id": None if published.previous_run_id is None else str(published.previous_run_id),
        "compared_runs": {str(run.id): {"assessment_date": run.assessment_date.isoformat(), "status": run.status} for run in runs},
        "row_counts": {
            "ForecastRun": db.ForecastRun.objects.count(),
            "ForecastRunCell": db.ForecastRunCell.objects.count(),
            "EstimateUpdate": db.EstimateUpdate.objects.count(),
            "EstimateResult": db.EstimateResult.objects.count(),
            "WeatherDaily": db.WeatherDaily.objects.count(),
            "WeatherSnapshot": db.WeatherSnapshot.objects.count(),
            "WeatherSnapshotDay": db.WeatherSnapshotDay.objects.count(),
            "WeatherSummary": db.WeatherSummary.objects.count(),
        },
        "row_counts_of_compared_runs": {
            "ForecastRunCell": db.ForecastRunCell.objects.filter(run_id__in=run_ids).count(),
            "EstimateUpdate": db.EstimateUpdate.objects.filter(forecast_run_cells__run_id__in=run_ids).distinct().count(),
            "EstimateResult": db.EstimateResult.objects.filter(update__forecast_run_cells__run_id__in=run_ids).distinct().count(),
            "WeatherSnapshot": db.WeatherSnapshot.objects.filter(forecast_run_cells__run_id__in=run_ids).distinct().count(),
            "WeatherSnapshotDay": db.WeatherSnapshotDay.objects.filter(snapshot__forecast_run_cells__run_id__in=run_ids).distinct().count(),
            "WeatherSummary": db.WeatherSummary.objects.filter(snapshot__forecast_run_cells__run_id__in=run_ids).distinct().count(),
            "WeatherDaily": db.WeatherDaily.objects.filter(snapshot_days__snapshot__forecast_run_cells__run_id__in=run_ids).distinct().count(),
        },
    }


@dataclass
class CellData:
    """Stored weather, published values and forest squares of one weather cell."""

    cell_key: str
    snapshot: Any
    stored_rows: dict[date, Any]
    fetch_time: datetime
    squares: list[tuple[Any, Any, Any]]
    published: dict[int, bytes]
    terrain_build_id: Any


@dataclass
class DateData:
    """Everything the database holds for one published run."""

    assessment_date: date
    run: Any
    cells: list[CellData] = field(default_factory=list)
    cells_without_update: list[str] = field(default_factory=list)


def load_date(*, assessment_date: date, region_code: str) -> DateData:
    """Read the published run, its stored weather and its forest squares."""
    run = find_published_run(assessment_date=assessment_date, region_code=region_code)
    result = DateData(assessment_date=assessment_date, run=run)
    run_cells = list(run.cells.select_related("snapshot", "update").order_by("cell_key"))
    snapshot_ids = [run_cell.snapshot_id for run_cell in run_cells]
    stored: dict[Any, dict[date, Any]] = defaultdict(dict)
    for link in db.WeatherSnapshotDay.objects.filter(snapshot_id__in=snapshot_ids).select_related("daily"):
        stored[link.snapshot_id][link.date] = link.daily
    published: dict[Any, dict[int, bytes]] = defaultdict(dict)
    update_ids = [run_cell.update_id for run_cell in run_cells if run_cell.update_id is not None]
    for update_id, forest_cell_id, values in db.EstimateResult.objects.filter(update_id__in=update_ids).values_list(
        "update_id", "forest_cell_id", "values"
    ):
        published[update_id][forest_cell_id] = bytes(values)
    forest_builds: dict[Any, Any] = {}
    for run_cell in run_cells:
        update = run_cell.update
        if update is None:
            result.cells_without_update.append(run_cell.cell_key)
            continue
        if update.forest_build_id not in forest_builds:
            forest_builds[update.forest_build_id] = db.ForestBuild.objects.get(id=update.forest_build_id)
        forest_cells = db.estimate_services._forest_cells_for_weather_cell(
            forest_build=forest_builds[update.forest_build_id],
            cell_key=run_cell.cell_key,
            batch_size=1000,
            region_code=region_code,
        )
        terrain_cells = {
            row.grid_build_cell_id: row
            for row in db.TerrainCell.objects.filter(
                build_id=update.terrain_build_id,
                grid_build_cell_id__in=[row.grid_build_cell_id for row in forest_cells],
            ).only("id", "build_id", "grid_build_cell_id", "altitude_m")
        }
        squares = [
            (
                forest_cell,
                terrain_cells.get(forest_cell.grid_build_cell_id),
                db.saved_host_trees(tree_inputs=update.tree_inputs, forest_cell_id=forest_cell.id),
            )
            for forest_cell in forest_cells
        ]
        snapshot = run_cell.snapshot
        stand_in = db.WeatherSnapshot(
            id=snapshot.id,
            cell_key=snapshot.cell_key,
            assessment_date=snapshot.assessment_date,
            reference_elevation_m=snapshot.reference_elevation_m,
            pipeline_version=snapshot.pipeline_version,
        )
        rows = stored[snapshot.id]
        forecast_day = rows[assessment_date]
        if "/v1/forecast" not in forecast_day.source_endpoint:
            raise RuntimeError(f"The row of {assessment_date} in cell {run_cell.cell_key} does not come from the forecast API.")
        result.cells.append(
            CellData(
                cell_key=run_cell.cell_key,
                snapshot=stand_in,
                stored_rows=rows,
                fetch_time=forecast_day.retrieved_at,
                squares=squares,
                published=published[update.id],
                terrain_build_id=update.terrain_build_id,
            )
        )
    return result


def estimate_cell(*, cell: CellData, rows: dict[date, Any]) -> dict[int, tuple[bytes, tuple[int | None, ...]]]:
    """Run the app's own summary and estimate code on the given daily rows for every forest square."""
    assessment_date = cell.snapshot.assessment_date
    summaries = {
        target: db.summary_services._make_summary(
            snapshot=cell.snapshot, assessment_date=assessment_date, target_date=target, rows=rows
        )
        for target in (assessment_date + timedelta(days=offset) for offset in range(TARGET_DAYS))
    }
    results: dict[int, tuple[bytes, tuple[int | None, ...]]] = {}
    for forest_cell, terrain_cell, host_trees in cell.squares:
        values: list[int | None] = []
        reasons: list[str | None] = []
        for target in sorted(summaries):
            inputs = db.estimate_services._forecast_inputs(
                snapshot=cell.snapshot,
                summary=summaries[target],
                forest_cell=forest_cell,
                terrain_cell=terrain_cell,
                terrain_build_id=cell.terrain_build_id,
                daily_rows=rows,
                host_trees=host_trees,
            )
            forecast = db.calculate_forecast(inputs=inputs, method=db.CURRENT_METHOD)
            values.append(forecast.whole_percentage)
            reasons.append(None if forecast.whole_percentage is not None else forecast.unavailable_reason)
        encoded = db.encode_result_bytes(percentages=values, unavailable_reasons=reasons)
        results[forest_cell.id] = (bytes(encoded), tuple(values))
    return results


def check_reproduction(*, data: DateData) -> dict[str, Any]:
    """Run the in-memory path on the stored weather and count squares that differ from the published values."""
    squares = 0
    different = 0
    missing = 0
    examples: list[dict[str, Any]] = []
    for cell in data.cells:
        results = estimate_cell(cell=cell, rows=cell.stored_rows)
        squares += len(cell.published)
        missing += len(set(cell.published) ^ set(results))
        for forest_cell_id, published in cell.published.items():
            if forest_cell_id in results and results[forest_cell_id][0] != published:
                different += 1
                if len(examples) < 5:
                    examples.append(
                        {
                            "cell_key": cell.cell_key,
                            "forest_cell_id": forest_cell_id,
                            "published": list(db.decode_result_bytes(values=published)),
                            "recomputed": list(db.decode_result_bytes(values=results[forest_cell_id][0])),
                        }
                    )
    return {
        "assessment_date": data.assessment_date.isoformat(),
        "squares": squares,
        "squares_different": different,
        "squares_missing_or_extra": missing,
        "examples": examples,
    }


# ---------------------------------------------------------------------------
# Bucket runs and the hourly fill, copied from Open-Meteo
# ---------------------------------------------------------------------------


@dataclass
class RunInfo:
    """One model run in the bucket, with the hours its steps cover."""

    reference: datetime
    created_at: datetime
    valid_hours: list[int]
    path: str

    @property
    def first_hour(self) -> int:
        return int(self.reference.timestamp()) // 3600

    @property
    def last_hour(self) -> int:
        return self.first_hour + self.valid_hours[-1]

    @property
    def label(self) -> str:
        return self.reference.strftime("%Y-%m-%dT%H:%MZ")


def parse_hour_text(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)


def read_run_info(*, domain_path: str, reference: datetime, totals: Any) -> RunInfo | None:
    """Read the meta file of one run, or return None when the run is not in the bucket."""
    path = f"{domain_path}/{reference:%Y/%m/%d/%H%MZ}"
    reader = bw.BucketReader(read_ahead_bytes=0)
    try:
        meta = json.loads(reader.cat_file(f"{path}/meta.json"))
    except RuntimeError as error:
        if "404" in str(error) or "403" in str(error):
            return None
        raise
    finally:
        totals.add(reader=reader)
    created_at = datetime.strptime(meta["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    reference_time = datetime.strptime(meta["reference_time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    valid_hours = [int((parse_hour_text(text) - reference_time).total_seconds() // 3600) for text in meta["valid_times"]]
    return RunInfo(reference=reference, created_at=created_at, valid_hours=valid_hours, path=path)


def catalog_runs(*, domain_path: str, step_hours: int, first: datetime, last: datetime, totals: Any) -> dict[datetime, RunInfo]:
    """Read the meta file of every run between two times."""
    catalog: dict[datetime, RunInfo] = {}
    moment = first
    while moment <= last:
        info = read_run_info(domain_path=domain_path, reference=moment, totals=totals)
        if info is not None:
            catalog[moment] = info
        moment += timedelta(hours=step_hours)
    return catalog


def step_offsets(*, run: RunInfo, steps: int) -> list[int]:
    """Return the hours after the run start that the steps of one file hold."""
    if steps == len(run.valid_hours):
        return run.valid_hours
    if steps == len(run.valid_hours) - 1:
        return run.valid_hours[1:]
    raise RuntimeError(f"A file of run {run.label} has {steps} steps but the run lists {len(run.valid_hours)} times.")


def fill_curve(*, values: np.ndarray, offsets: list[int]) -> np.ndarray:
    """Fill the hours between steps with the cubic curve of Open-Meteo's downloader."""
    out = values.copy()
    present = set(offsets)
    width = 0
    for hour in range(out.shape[1]):
        if hour in present:
            continue
        later = offsets[bisect.bisect_right(offsets, hour) :]
        if not later:
            break
        pos_c = later[0]
        if len(later) > 1:
            pos_d = later[1]
            width = pos_d - pos_c
        else:
            pos_d = pos_c
        pos_b = max(pos_c - width, 0)
        pos_a = pos_b - width if pos_b - width >= 0 else pos_b
        a_value, b_value, c_value, d_value = out[:, pos_a], out[:, pos_b], out[:, pos_c], out[:, pos_d]
        a = -a_value / 2 + 3 * b_value / 2 - 3 * c_value / 2 + d_value / 2
        b = a_value - 5 * b_value / 2 + 2 * c_value - d_value / 2
        c = -a_value / 2 + c_value / 2
        fraction = (hour - pos_b) / (pos_c - pos_b)
        out[:, hour] = a * fraction**3 + b * fraction**2 + c * fraction + b_value
    return out


def fill_total(*, values: np.ndarray, offsets: list[int]) -> np.ndarray:
    """Spread the total of a step evenly over the hours since the previous step."""
    out = values.copy()
    present = set(offsets)
    first_valid = offsets[0]
    if len(offsets) > 1:
        first_valid = max(first_valid - (offsets[1] - first_valid - 1), 0)
    previous = first_valid - 1
    hour = first_valid
    while hour < out.shape[1]:
        if hour in present:
            previous = hour
            hour += 1
            continue
        later = offsets[bisect.bisect_right(offsets, hour) :]
        if not later:
            break
        position = later[0]
        out[:, hour : position + 1] = values[:, position : position + 1] / (position - previous)
        previous = position
        hour = position + 1
    return out


def solar_factor(*, latitudes: np.ndarray, longitudes: np.ndarray, first_hour: int, hours: int) -> np.ndarray:
    """Return the clear-sky sun factor of each point for the hour ending at each time, as Open-Meteo's Zensun code does."""
    out = np.zeros((len(latitudes), hours))
    colatitude = np.radians(90 - latitudes)
    for index in range(hours):
        moment = datetime.fromtimestamp((first_hour + index) * 3600, tz=UTC)
        declination, equation_of_time, distance = _sun_position(moment=moment)
        universal_time = moment.hour + moment.minute / 60
        sun_colatitude = math.radians(90 - declination)
        p1 = math.radians(-15.0 * (universal_time - 12.0 + equation_of_time))
        p10 = math.radians(-15.0 * (universal_time - 1.0 - 12.0 + equation_of_time))
        p0 = np.radians(longitudes)
        p0 = np.where(p0 < p1 - math.pi, p0 + 2 * math.pi, p0)
        p0 = np.where(p0 > p1 + math.pi, p0 - 2 * math.pi, p0)
        a = np.cos(colatitude) * math.cos(sun_colatitude)
        b = np.sin(colatitude) * math.sin(sun_colatitude)
        argument = -a / b
        half_day = np.where(argument <= -1, math.pi, np.arccos(np.clip(argument, -1, 1)))
        low = np.maximum(p1, p0 - half_day)
        high = np.minimum(p10, p0 + half_day)
        centre = (low + high) / 2
        half = (high - low) / 2
        offset = half * 0.77459667

        def integrand(position: np.ndarray) -> np.ndarray:
            mu = a + b * np.cos(position - p0)
            return np.where(mu < 0.005, 0.0, mu * np.exp(-0.057 / np.maximum(mu, 0.005)))

        value = half * (5 / 9 * (integrand(centre - offset) + integrand(centre + offset)) + 8 / 9 * integrand(centre)) / (
            distance**2 * (p10 - p1)
        )
        out[:, index] = np.where((argument < 1) & (low < high), value, 0.0)
    return out


def _spline(*, a: float, b: float, c: float, fraction: float) -> float:
    t = max(0.0, min(1.0, fraction))
    start = (a + b) * 0.5
    end = (b + c) * 0.5
    return (1 - t) * (1 - t) * start + 2 * (1 - t) * t * b + t * t * end


def _fill_sun_series(*, series: list[float], sun: list[float], offsets: list[int]) -> list[float]:
    """Fill one point's radiation with Open-Meteo's clearness index curve that keeps the mean of each step."""
    count = len(series)
    radiation_limit = SOLAR_CONSTANT * 0.95
    minimum = 5 / SOLAR_CONSTANT
    first_valid = offsets[0]
    if len(offsets) > 1:
        first_valid = max(first_valid - (offsets[1] - first_valid - 1), 0)
    for hour in range(first_valid, count):
        if not math.isnan(series[hour]):
            continue
        value_c = math.nan
        pos_c = 0
        for later in range(hour + 1, min(hour + 2 + 12, count)):
            if not math.isnan(series[later]):
                value_c = series[later]
                pos_c = later
                break
        if math.isnan(value_c):
            break
        pos_b = hour - 1
        width = pos_c - pos_b
        pos_a = pos_b - width
        pos_d = pos_c + width
        b_valid = pos_a >= 0 and not math.isnan(series[pos_a])
        d_valid = pos_d < count and not math.isnan(series[pos_d])
        sun_c = sum(sun[pos_b + 1 : pos_c + 1]) / (pos_c - pos_b)
        kt_c = math.nan if sun_c <= minimum or value_c <= 0 else min(value_c / sun_c, radiation_limit)
        if b_valid:
            value_b = sum(series[pos_a + 1 : pos_b + 1]) / (pos_b - pos_a)
            sun_b = sum(sun[pos_a + 1 : pos_b + 1]) / (pos_b - pos_a)
            kt_b = kt_c if sun_b <= minimum else min(value_b / sun_b, radiation_limit)
        else:
            kt_b = kt_c
        if d_valid:
            sun_d = sum(sun[pos_c + 1 : pos_d + 1]) / (pos_d - pos_c)
            kt_d = kt_c if sun_d <= minimum else min(series[pos_d] / sun_d, radiation_limit)
        else:
            kt_d = kt_c
        if math.isnan(kt_b) and math.isnan(kt_c) and math.isnan(kt_d):
            for night in range(hour, pos_c):
                series[night] = 0.0
            continue
        use_c = kt_c if math.isfinite(kt_c) else kt_b if math.isfinite(kt_b) else kt_d
        use_b = kt_b if math.isfinite(kt_b) else use_c
        use_d = kt_d if math.isfinite(kt_d) else use_c
        factor = 1.0
        if value_c > 5:
            total = 0.0
            for step in range(hour, pos_c + 1):
                curve = _spline(a=use_b, b=use_c, c=use_d, fraction=(step - pos_b) / (pos_c - pos_b))
                total += max(curve, 0.0) * sun[step]
            factor = 0.0 if total <= 5 else value_c / total * (pos_c - hour + 1)
        for step in range(hour, pos_c + 1):
            curve = _spline(a=use_b, b=use_c, c=use_d, fraction=(step - pos_b) / (pos_c - pos_b))
            series[step] = max(curve, 0.0) * sun[step] * factor
    return series


def fill_sun(*, values: np.ndarray, offsets: list[int], sun: np.ndarray) -> np.ndarray:
    """Fill the radiation of every point between steps."""
    out = values.copy()
    for row in range(out.shape[0]):
        out[row] = _fill_sun_series(series=out[row].tolist(), sun=sun[row].tolist(), offsets=offsets)
    return out


def hourly_from_steps(*, run: RunInfo, variable: str, blocks: np.ndarray, sun: np.ndarray | None) -> np.ndarray:
    """Return one run's values for every hour after its start, filled the way Open-Meteo fills them."""
    offsets = step_offsets(run=run, steps=blocks.shape[1])
    grid = np.full((blocks.shape[0], run.valid_hours[-1] + 1), np.nan)
    grid[:, offsets] = blocks
    rule = IFS_RULES.get(variable, "curve")
    if rule == "sum":
        return fill_total(values=grid, offsets=offsets)
    if rule == "solar":
        return fill_sun(values=grid, offsets=offsets, sun=sun)
    return fill_curve(values=grid, offsets=offsets)


def read_ifs_run(*, run: RunInfo, points: list[int], settings: dict[str, Any], totals: Any) -> dict[str, np.ndarray]:
    """Read the eight variables of one ecmwf_ifs run for grid points and return them hourly."""
    runs = bw.point_runs(points=points, merge_gap=settings["merge_gap_points"])
    coordinates = np.array([bw.point_coordinates(point=point) for point in points])
    sun = solar_factor(
        latitudes=coordinates[:, 0], longitudes=coordinates[:, 1], first_hour=run.first_hour, hours=run.valid_hours[-1] + 1
    )

    def read_one(variable: str) -> tuple[str, np.ndarray]:
        blocks = bw.read_points(
            path=f"{run.path}/{variable}.om", runs=runs, read_ahead_bytes=settings["read_ahead_bytes"], totals=totals
        )
        stacked = np.stack([blocks[point] for point in points]).astype(np.float64)
        return variable, hourly_from_steps(run=run, variable=variable, blocks=stacked, sun=sun)

    with ThreadPoolExecutor(max_workers=settings["threads"]) as pool:
        return dict(pool.map(read_one, IFS_VARIABLES))


# ---------------------------------------------------------------------------
# File weather for one assessment date
# ---------------------------------------------------------------------------


@dataclass
class Newest:
    """The saved values of the newest ecmwf_ifs files and the grid point matches."""

    points: list[int]
    first_hour: int
    values: dict[str, np.ndarray]
    matches: dict[str, Any]
    run: datetime


def load_newest(*, settings: dict[str, Any], context: RunContext) -> Newest:
    directory = ROOT / settings["newest_files_dir"]
    context.add_input(directory / "values.npz")
    context.add_input(directory / "read.json")
    saved = np.load(directory / "values.npz")
    read = json.loads((directory / "read.json").read_text(encoding="utf-8"))
    return Newest(
        points=[int(point) for point in saved["points"]],
        first_hour=int(saved["first_hour"]),
        values={variable: saved[variable].astype(np.float64) for variable in IFS_VARIABLES},
        matches={key: bw.Match(**value) for key, value in read["matches"].items()},
        run=parse_hour_text(settings["newest_run"]),
    )


def window_hours(*, assessment_date: date, settings: dict[str, Any]) -> tuple[int, int]:
    """Return the first hour and the closing hour of the window, both inside the window."""
    first, end = bw.local_window_hours(
        first_day=assessment_date - timedelta(days=settings["past_days"]),
        last_day=assessment_date + timedelta(days=settings["days_ahead"]),
    )
    return first, end


def choose_run(*, catalog: dict[datetime, RunInfo], fetch_time: datetime, delay_hours: int) -> RunInfo:
    """Return the newest run that the files held when the API answered."""
    ready = [info for info in catalog.values() if info.created_at + timedelta(hours=delay_hours) <= fetch_time]
    if not ready:
        raise RuntimeError(f"No run was ready at {fetch_time}.")
    return max(ready, key=lambda info: info.reference)


def overlay(
    *, arrays: dict[str, np.ndarray], hourly: dict[str, np.ndarray], cell_rows: list[int], point_rows: list[int],
    run_first_hour: int, window_first: int, window_hours_count: int, from_hour: int,
) -> None:
    """Put the hourly values of a run over the window arrays, where the run has a value."""
    for variable, grid in hourly.items():
        start = max(run_first_hour, from_hour, window_first)
        stop = min(run_first_hour + grid.shape[1], window_first + window_hours_count)
        if stop <= start:
            continue
        source = grid[point_rows][:, start - run_first_hour : stop - run_first_hour]
        target = arrays[variable][cell_rows, start - window_first : stop - window_first]
        arrays[variable][cell_rows, start - window_first : stop - window_first] = np.where(np.isnan(source), target, source)


def build_ifs_weather(
    *, assessment_date: date, data: DateData, newest: Newest, catalog: dict[datetime, RunInfo],
    settings: dict[str, Any], totals: Any,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Build hourly weather of the whole window for every cell from the ecmwf_ifs files."""
    first, end = window_hours(assessment_date=assessment_date, settings=settings)
    count = end - first + 1
    point_index = {point: row for row, point in enumerate(newest.points)}
    matches = [newest.matches[cell.cell_key] for cell in data.cells]
    rows = [point_index[match.point] for match in matches]
    base = {
        variable: newest.values[variable][rows][:, first - newest.first_hour : end + 1 - newest.first_hour].copy()
        for variable in IFS_VARIABLES
    }
    chosen = [choose_run(catalog=catalog, fetch_time=cell.fetch_time, delay_hours=settings["file_delay_hours"]) for cell in data.cells]
    groups: dict[datetime, list[int]] = defaultdict(list)
    for index, run in enumerate(chosen):
        groups[run.reference].append(index)
    run_report: list[dict[str, Any]] = []
    filled_from_older = 0
    for reference, cell_rows in sorted(groups.items()):
        run = catalog[reference]
        fetched = [data.cells[index].fetch_time for index in cell_rows]
        entry = {
            "run": run.label,
            "created_at": run.created_at.isoformat(),
            "cells": len(cell_rows),
            "first_fetch": min(fetched).isoformat(),
            "last_fetch": max(fetched).isoformat(),
            "source": "saved newest files" if reference == newest.run else "run files",
        }
        run_report.append(entry)
        if reference == newest.run:
            continue
        run_points = sorted({matches[index].point for index in cell_rows})
        hourly = read_ifs_run(run=run, points=run_points, settings=settings, totals=totals)
        point_rows = [run_points.index(matches[index].point) for index in cell_rows]
        overlay(
            arrays=base, hourly=hourly, cell_rows=cell_rows, point_rows=point_rows, run_first_hour=run.first_hour,
            window_first=first, window_hours_count=count, from_hour=run.first_hour,
        )
        if run.last_hour < end:
            older = catalog.get(reference - timedelta(hours=6))
            if older is None or older.last_hour < end:
                raise RuntimeError(f"Run {run.label} ends before the window and no earlier run covers the rest.")
            older_hourly = read_ifs_run(run=older, points=run_points, settings=settings, totals=totals)
            overlay(
                arrays=base, hourly=older_hourly, cell_rows=cell_rows, point_rows=point_rows, run_first_hour=older.first_hour,
                window_first=first, window_hours_count=count, from_hour=run.last_hour + 1,
            )
            filled_from_older += len(cell_rows)
            entry["rest_from"] = older.label
    corrections = np.array([match.correction for match in matches])[:, None]
    arrays = {
        "precipitation": base["precipitation"],
        "temperature": base["temperature_2m"] + corrections,
        "dew_point": base["dew_point_2m"] + corrections,
        "soil_moisture": base["soil_moisture_0_to_7cm"],
        "soil_temperature": base["soil_temperature_0_to_7cm"] + corrections,
        "shortwave_radiation": base["shortwave_radiation"],
        "wind_speed": np.hypot(base["wind_u_component_10m"], base["wind_v_component_10m"]),
    }
    return arrays, {"runs": run_report, "cells_with_rest_from_older_run": filled_from_older}


def icon_grid_xy(*, latitude: float, longitude: float) -> tuple[int, int]:
    """Return the nearest ICON-2I grid column and row, rounding like Open-Meteo."""
    x = bw.swift_round(np.float32(np.float32(longitude) - np.float32(ICON_GRID["lon_min"])) / np.float32(ICON_GRID["dx"]))
    y = bw.swift_round(np.float32(np.float32(latitude) - np.float32(ICON_GRID["lat_min"])) / np.float32(ICON_GRID["dy"]))
    return x, y


def icon_point_coordinates(*, x: int, y: int) -> tuple[float, float]:
    latitude = np.float32(ICON_GRID["lat_min"]) + np.float32(y) * np.float32(ICON_GRID["dy"])
    longitude = np.float32(ICON_GRID["lon_min"]) + np.float32(x) * np.float32(ICON_GRID["dx"])
    return float(latitude), float(longitude)


@dataclass
class IconPoint:
    """The ICON-2I grid point chosen for one cell and its height."""

    x: int
    y: int
    height_m: float
    correction_c: float


def choose_icon_points(
    *, cells: list[tuple[float, float]], place_heights: list[float], settings: dict[str, Any], totals: Any
) -> list[IconPoint]:
    """Pick the ICON-2I grid point of each cell with Open-Meteo's terrain-aware choice and its temperature correction."""
    reader = bw.BucketReader(read_ahead_bytes=settings["read_ahead_bytes"])
    heights_file = bw.open_file(reader=reader, path=ICON_HEIGHT_FILE)
    nx, ny = ICON_GRID["nx"], ICON_GRID["ny"]
    chosen: list[IconPoint] = []
    for (latitude, longitude), place_height in zip(cells, place_heights, strict=True):
        x, y = icon_grid_xy(latitude=latitude, longitude=longitude)
        x_range = range(max(x - 1, 0), min(x + 2, nx))
        y_range = range(max(y - 1, 0), min(y + 2, ny))
        block = np.asarray(
            heights_file.read_array((slice(y_range.start, y_range.stop), slice(x_range.start, x_range.stop)))
        ).astype(np.float32)
        flat = block.reshape(-1)
        centre_height = float(flat[len(flat) // 2])
        best_x, best_y, best_height = x, y, centre_height
        if not math.isnan(place_height) and abs(centre_height - place_height) > 100:
            best_delta = abs(np.float32(centre_height) - np.float32(place_height))
            moved_height = math.nan
            for index, height in enumerate(flat):
                if math.isnan(height) or height <= -999:
                    continue
                point_x = x_range.start + index % len(x_range)
                point_y = y_range.start + index // len(x_range)
                point_lat, point_lon = icon_point_coordinates(x=point_x, y=point_y)
                distance_squared = np.float32(
                    (np.float32(point_lat) - np.float32(latitude)) ** 2 + (np.float32(point_lon) - np.float32(longitude)) ** 2
                )
                distance_km = np.sqrt(distance_squared) * np.float32(111)
                penalty = distance_km * np.float32(30)
                delta = (np.float32(0) if height >= 9999 else abs(np.float32(height) - np.float32(place_height))) + penalty
                if delta < best_delta and distance_km < 50:
                    best_delta = delta
                    best_x, best_y, moved_height = point_x, point_y, float(height)
            if math.isnan(moved_height) or best_delta > 1500:
                best_x, best_y, best_height = x, y, centre_height
            else:
                best_height = moved_height
        model_height = 0.0 if best_height <= -999 else math.nan if best_height >= 9999 else best_height
        if math.isnan(place_height) or math.isnan(model_height) or place_height == model_height:
            correction = 0.0
        else:
            correction = (model_height - place_height) * LAPSE_RATE
        chosen.append(IconPoint(x=best_x, y=best_y, height_m=best_height, correction_c=correction))
    totals.add(reader=reader)
    return chosen


def read_icon_run(
    *, run: RunInfo, points: list[tuple[int, int]], settings: dict[str, Any], totals: Any
) -> dict[str, np.ndarray]:
    """Read the five ICON-2I variables of one run for grid points, hourly from the run start."""

    def read_one(variable: str) -> tuple[str, np.ndarray]:
        reader = bw.BucketReader(read_ahead_bytes=settings["read_ahead_bytes"])
        file = bw.open_file(reader=reader, path=f"{run.path}/{variable}.om")
        rows = []
        for x, y in points:
            rows.append(np.asarray(file.read_array((slice(y, y + 1), slice(x, x + 1), slice(None)))).reshape(-1))
        totals.add(reader=reader)
        stacked = np.stack(rows).astype(np.float64)
        offsets = step_offsets(run=run, steps=stacked.shape[1])
        grid = np.full((len(points), run.valid_hours[-1] + 1), np.nan)
        grid[:, offsets] = stacked
        return variable, grid

    with ThreadPoolExecutor(max_workers=settings["threads"]) as pool:
        return dict(pool.map(read_one, ICON_VARIABLES))


def dew_point(*, temperature: float, humidity: float) -> float:
    """Return the dew point in Celsius from temperature and relative humidity, as Open-Meteo derives it."""
    beta = 17.625
    lam = 243.04
    if humidity <= 0:
        return math.nan
    log_humidity = math.log(humidity / 100)
    term = beta * temperature / (lam + temperature)
    return lam * (log_humidity + term) / (beta - log_humidity - term)


def build_icon_weather(
    *, assessment_date: date, data: DateData, place_heights: list[float], settings: dict[str, Any], totals: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the ICON-2I values of every cell for the first hours and return them with a report."""
    start, _ = bw.local_window_hours(first_day=assessment_date, last_day=assessment_date)
    hours = settings["icon_hours"]
    fetch_times = [cell.fetch_time for cell in data.cells]
    first_reference = datetime.fromtimestamp((start - 36) * 3600, tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    last_reference = max(fetch_times)
    catalog = {
        reference: info
        for reference, info in catalog_runs(
            domain_path=ICON_PATH, step_hours=12, first=first_reference, last=last_reference.replace(hour=12, minute=0, second=0, microsecond=0), totals=totals
        ).items()
        if info.created_at <= last_reference
    }
    cell_positions = [tuple(float(part) for part in cell.cell_key.split(",")) for cell in data.cells]
    icon_points = choose_icon_points(cells=cell_positions, place_heights=place_heights, settings=settings, totals=totals)
    unique = sorted({(point.x, point.y) for point in icon_points}, key=lambda xy: (xy[1], xy[0]))
    unique_row = {xy: row for row, xy in enumerate(unique)}
    runs = {reference: read_icon_run(run=info, points=unique, settings=settings, totals=totals) for reference, info in catalog.items()}
    timestamps = list(range(start, start + hours + 1))
    values = {variable: np.full((len(data.cells), len(timestamps)), np.nan) for variable in ICON_VARIABLES}
    missing = 0
    for index, cell in enumerate(data.cells):
        row = unique_row[(icon_points[index].x, icon_points[index].y)]
        allowed = sorted(
            (info for info in catalog.values() if info.created_at <= cell.fetch_time), key=lambda info: info.reference, reverse=True
        )
        for variable in ICON_VARIABLES:
            for position, hour in enumerate(timestamps):
                for info in allowed:
                    offset = hour - info.first_hour
                    if 0 <= offset <= info.valid_hours[-1]:
                        value = runs[info.reference][variable][row, offset]
                        if not math.isnan(value):
                            values[variable][index, position] = value
                            break
                else:
                    missing += 1
    temperature = values["temperature_2m"] + np.array([point.correction_c for point in icon_points])[:, None]
    dew = np.array(
        [[dew_point(temperature=t, humidity=h) for t, h in zip(t_row, h_row, strict=True)] for t_row, h_row in zip(temperature, values["relative_humidity_2m"], strict=True)]
    )
    result = {
        "start_hour": start,
        "hours": hours,
        "precipitation": values["precipitation"],
        "temperature": temperature,
        "dew_point": dew,
        "shortwave_radiation": values["shortwave_radiation"],
        "wind_speed": values["wind_speed_10m"],
        "points": icon_points,
    }
    report = {
        "runs": [
            {"run": info.label, "created_at": info.created_at.isoformat()} for info in sorted(catalog.values(), key=lambda info: info.reference)
        ],
        "cell_hours_without_value": missing,
        "cells_with_height_correction": sum(1 for point in icon_points if point.correction_c != 0.0),
    }
    return result, report


def top_of_atmosphere_series(*, latitude: float, longitude: float, first_hour: int, count: int) -> np.ndarray:
    """Return the sun power above the atmosphere for every hour of the window."""
    return np.array(
        [
            top_of_atmosphere_radiation(
                latitude=latitude, longitude=longitude, hour_end=datetime.fromtimestamp((first_hour + index) * 3600, tz=UTC)
            )
            for index in range(count)
        ]
    )


def evapotranspiration_series(
    *, arrays: dict[str, np.ndarray], row: int, elevation: float, toa: np.ndarray, hours: range
) -> np.ndarray:
    """Return hourly evapotranspiration for some hours of one cell, with NaN where an input is missing."""
    result = np.full(arrays["temperature"].shape[1], np.nan)
    for hour in hours:
        inputs = (
            arrays["temperature"][row, hour],
            arrays["dew_point"][row, hour],
            arrays["shortwave_radiation"][row, hour],
            arrays["wind_speed"][row, hour],
        )
        if any(math.isnan(value) for value in inputs):
            continue
        result[hour] = hourly_reference_evapotranspiration(
            temperature_c=inputs[0],
            dew_point_c=inputs[1],
            shortwave_radiation_w_m2=inputs[2],
            wind_speed_10m_m_s=inputs[3],
            elevation_m=elevation,
            top_of_atmosphere_w_m2=float(toa[hour]),
        )
    return result


def add_evapotranspiration(
    *, arrays: dict[str, np.ndarray], elevations: list[float], coordinates: list[tuple[float, float]], first_hour: int
) -> None:
    """Add hourly evapotranspiration to the arrays, from the place height and the grid point position of each cell."""
    count = arrays["temperature"].shape[1]
    cache: dict[tuple[float, float], np.ndarray] = {}
    arrays["et0"] = np.full(arrays["temperature"].shape, np.nan)
    for row, (elevation, position) in enumerate(zip(elevations, coordinates, strict=True)):
        if position not in cache:
            cache[position] = top_of_atmosphere_series(latitude=position[0], longitude=position[1], first_hour=first_hour, count=count)
        arrays["et0"][row] = evapotranspiration_series(
            arrays=arrays, row=row, elevation=elevation, toa=cache[position], hours=range(count)
        )


def apply_icon(
    *, arrays: dict[str, np.ndarray], icon: dict[str, Any], elevations: list[float], first_hour: int
) -> dict[str, np.ndarray]:
    """Return a copy of the arrays with the ICON-2I hours replaced and evapotranspiration recomputed for them."""
    result = {name: values.copy() for name, values in arrays.items()}
    start = icon["start_hour"] - first_hour
    stop = start + icon["hours"]
    for name in ("temperature", "dew_point", "wind_speed"):
        # Values at a time stamp: the hours that start between midnight and midnight plus 60 hours.
        result[name][:, start:stop] = np.where(np.isnan(icon[name][:, :-1]), result[name][:, start:stop], icon[name][:, :-1])
    for name in ("precipitation", "shortwave_radiation"):
        # Amounts cover the hour before their time stamp: the hours that end after midnight, up to midnight plus 60 hours.
        result[name][:, start + 1 : stop + 1] = np.where(
            np.isnan(icon[name][:, 1:]), result[name][:, start + 1 : stop + 1], icon[name][:, 1:]
        )
    count = result["temperature"].shape[1]
    for row, point in enumerate(icon["points"]):
        latitude, longitude = icon_point_coordinates(x=point.x, y=point.y)
        toa = top_of_atmosphere_series(latitude=latitude, longitude=longitude, first_hour=first_hour, count=count)
        result["et0"][row, start + 1 : stop + 1] = evapotranspiration_series(
            arrays=result, row=row, elevation=elevations[row], toa=toa, hours=range(start + 1, stop + 1)
        )[start + 1 : stop + 1]
    return result


def daily_rows(*, arrays: dict[str, np.ndarray], row: int, cell: CellData, first_hour: int, settings: dict[str, Any]) -> dict[date, Any]:
    """Build in-memory stand-ins for the daily rows of one cell with the app's own aggregation."""
    assessment_date = cell.snapshot.assessment_date
    count = arrays["temperature"].shape[1]
    timestamps = tuple((first_hour + index) * 3600 for index in range(count))

    def clean(values: np.ndarray) -> tuple[float | None, ...]:
        return tuple(None if math.isnan(value) else float(value) for value in values)

    days = db_aggregate(
        timestamps=timestamps,
        variables={
            "precipitation": clean(arrays["precipitation"][row]),
            "temperature": clean(arrays["temperature"][row]),
            "soil_moisture": clean(arrays["soil_moisture"][row]),
            "soil_temperature": clean(arrays["soil_temperature"][row]),
            "et0": clean(arrays["et0"][row]),
        },
        start=assessment_date - timedelta(days=settings["past_days"]),
        end=assessment_date + timedelta(days=settings["days_ahead"]),
    )
    return {
        day.date: SimpleNamespace(
            id=f"files:{cell.cell_key}:{day.date.isoformat()}",
            source_id="files:bulk_weather_estimates",
            attempt_id="files",
            date=day.date,
            rain_mm=day.rain_mm,
            mean_temperature_c=day.mean_temperature_c,
            min_temperature_c=day.min_temperature_c,
            et0_mm=day.et0_mm,
            mean_soil_temperature_c=day.mean_soil_temperature_c,
            mean_soil_moisture=day.mean_soil_moisture,
            status=day.status,
            metadata=day.metadata,
        )
        for day in days
    }


def db_aggregate(*, timestamps: tuple[int, ...], variables: dict[str, tuple[float | None, ...]], start: date, end: date) -> Any:
    return db.aggregate_hourly(hourly_timestamps=timestamps, variables=variables, start=start, end=end)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def to_array(*, values: dict[int, tuple[int | None, ...]], order: list[int]) -> np.ndarray:
    """Return percentages as an array with -1 where the estimate is unavailable."""
    out = np.full((len(order), TARGET_DAYS), -1, dtype=np.int16)
    for row, forest_cell_id in enumerate(order):
        out[row] = [-1 if value is None else value for value in values[forest_cell_id]]
    return out


def published_values(*, cell: CellData, order: list[int]) -> np.ndarray:
    out = np.full((len(order), TARGET_DAYS), -1, dtype=np.int16)
    for row, forest_cell_id in enumerate(order):
        decoded = db.decode_result_bytes(values=cell.published[forest_cell_id])
        out[row] = [value if isinstance(value, int) else -1 for value in decoded]
    return out


def difference_row(*, label: dict[str, Any], mine: np.ndarray, other: np.ndarray, large: int) -> dict[str, Any]:
    """Summarise the difference of two estimate columns, mine minus other, in percentage points."""
    mine_ok = mine >= 0
    other_ok = other >= 0
    both = mine_ok & other_ok
    difference = (mine[both] - other[both]).astype(float)
    absolute = np.abs(difference)
    row = {
        **label,
        "squares": len(mine),
        "squares_compared": int(both.sum()),
        "squares_one_side_unavailable": int((mine_ok ^ other_ok).sum()),
        "squares_both_unavailable": int((~mine_ok & ~other_ok).sum()),
    }
    if len(difference):
        row.update(
            {
                "median_abs_difference_points": round(float(np.median(absolute)), 3),
                "p90_abs_difference_points": round(float(np.percentile(absolute, 90)), 3),
                "max_abs_difference_points": round(float(absolute.max()), 3),
                "mean_signed_difference_points": round(float(difference.mean()), 3),
                "share_5_points_or_more": round(float((absolute >= large).mean()), 4),
            }
        )
    else:
        row.update({name: "" for name in DAYS_COLUMNS[8:]})
    return row


def total_or_none(*, rows: dict[date, Any], days: list[date], name: str, mean: bool) -> float | None:
    values = [getattr(rows[day], name) if day in rows else None for day in days]
    if any(value is None for value in values):
        return None
    return sum(values) / len(values) if mean else sum(values)


def difference_or_blank(*, files: float | None, stored: float | None, digits: int) -> float | str:
    return "" if files is None or stored is None else round(files - stored, digits) + 0.0


def cell_row(
    *, assessment_date: date, variant: str, cell: CellData, rows: dict[date, Any], estimate_gap: np.ndarray, settings: dict[str, Any]
) -> dict[str, Any]:
    """Compare the daily weather of one cell with the stored weather, and add its estimate gaps."""
    past = [assessment_date - timedelta(days=offset) for offset in range(settings["past_days"], 0, -1)]
    ahead = [assessment_date + timedelta(days=offset) for offset in range(settings["days_ahead"] + 1)]
    row: dict[str, Any] = {"assessment_date": assessment_date.isoformat(), "variant": variant, "cell_key": cell.cell_key}
    for label, days, name, mean, digits in (
        ("rain_past_30_days", past, "rain_mm", False, 2),
        ("rain_8_days", ahead, "rain_mm", False, 2),
        ("soil_moisture_past_30_days", past, "mean_soil_moisture", True, 6),
        ("soil_moisture_8_days", ahead, "mean_soil_moisture", True, 6),
    ):
        files = total_or_none(rows=rows, days=days, name=name, mean=mean)
        stored = total_or_none(rows=cell.stored_rows, days=days, name=name, mean=mean)
        suffix = "_mm" if name == "rain_mm" else ""
        row[f"{label}_files{suffix}"] = "" if files is None else round(files, digits)
        row[f"{label}_stored{suffix}"] = "" if stored is None else round(stored, digits)
        row[f"{label}_difference{suffix}"] = difference_or_blank(files=files, stored=stored, digits=digits)
    row["evapotranspiration_past_30_days_difference_mm"] = difference_or_blank(
        files=total_or_none(rows=rows, days=past, name="et0_mm", mean=False),
        stored=total_or_none(rows=cell.stored_rows, days=past, name="et0_mm", mean=False),
        digits=2,
    )
    row["mean_temperature_8_days_difference_c"] = difference_or_blank(
        files=total_or_none(rows=rows, days=ahead, name="mean_temperature_c", mean=True),
        stored=total_or_none(rows=cell.stored_rows, days=ahead, name="mean_temperature_c", mean=True),
        digits=2,
    )
    row["squares_compared"] = int(estimate_gap.size)
    row["median_abs_estimate_difference_points"] = "" if not estimate_gap.size else round(float(np.median(estimate_gap)), 3)
    row["max_abs_estimate_difference_points"] = "" if not estimate_gap.size else round(float(estimate_gap.max()), 3)
    return row


def write_csv(*, rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def check_interpolation(*, newest: Newest, settings: dict[str, Any], totals: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fill the newest run from its run file and compare it with the saved newest files."""
    run = read_run_info(domain_path=IFS_PATH, reference=newest.run, totals=totals)
    if run is None:
        return [], {"skipped": f"Run {newest.run} is not in the bucket."}
    hourly = read_ifs_run(run=run, points=newest.points, settings=settings, totals=totals)
    hourly["wind_speed"] = np.hypot(hourly["wind_u_component_10m"], hourly["wind_v_component_10m"])
    saved = dict(newest.values)
    saved["wind_speed"] = np.hypot(saved["wind_u_component_10m"], saved["wind_v_component_10m"])
    hours = hourly["temperature_2m"].shape[1]
    start = run.first_hour - newest.first_hour
    rows: list[dict[str, Any]] = []
    for variable, grid in hourly.items():
        rule = IFS_RULES.get(variable, "curve")
        names = {"sum": "total spread evenly", "solar": "clearness index curve", "curve": "cubic curve"}
        for part, low, high in (("first 90 hours, hourly steps", 0, 91), ("after 90 hours, filled", 91, hours)):
            gap = np.abs(grid[:, low:high] - saved[variable][:, start + low : start + high])
            gap = gap[~np.isnan(gap)]
            rows.append(
                {
                    "variable": variable,
                    "part": part,
                    "rule": names[rule],
                    "values_compared": int(gap.size),
                    "median_abs_gap": "" if not gap.size else round(float(np.median(gap)), 4),
                    "max_abs_gap": "" if not gap.size else round(float(gap.max()), 4),
                }
            )
    return rows, {"run": run.label, "points": len(newest.points), "hours": hours}


def run(context: RunContext) -> None:
    """Compare the estimates from file weather with the published estimates and write the results."""
    settings = context.config
    started = time.monotonic()
    reports_dir = ROOT / "reports"
    dates = [date.fromisoformat(text) for text in settings["assessment_dates"]]
    region_code = settings["region_code"]
    totals = bw.ReadTotals()
    summary: dict[str, Any] = {"assessment_dates": [day.isoformat() for day in dates], "phases_seconds": {}}
    summary_path = context.output_dir / "summary.json"

    def save_summary() -> None:
        summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    start_django()
    assert_read_only()
    newest = load_newest(settings=settings, context=context)
    context.add_source(
        name="Open-Meteo open data on AWS, ecmwf_ifs and italia_meteo_arpae_icon_2i runs",
        url=bw.BUCKET_URL + "data_run",
        licence="CC BY 4.0",
        version=f"newest files run {settings['newest_run']}",
        downloaded_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        query={"assessment_dates": summary["assessment_dates"], "variables": list(IFS_VARIABLES), "icon_variables": list(ICON_VARIABLES)},
    )

    published_runs = {day: find_published_run(assessment_date=day, region_code=region_code) for day in dates}
    run_ids = [published_runs[day].id for day in dates]
    summary["database_before"] = database_state(region_code=region_code, run_ids=run_ids)
    save_summary()

    # Stored weather, published values and forest squares, then the required reproduction check.
    phase = time.monotonic()
    data_by_date: dict[date, DateData] = {}
    summary["reproduction_check"] = []
    for day in dates:
        data = load_date(assessment_date=day, region_code=region_code)
        data_by_date[day] = data
        print(f"{day}: loaded {len(data.cells)} cells and {sum(len(cell.squares) for cell in data.cells)} squares", flush=True)
        check = check_reproduction(data=data)
        check["cells_without_update"] = data.cells_without_update
        summary["reproduction_check"].append(check)
        save_summary()
        print(f"{day}: reproduction check, {check['squares_different']} of {check['squares']} squares differ", flush=True)
        if check["squares_different"] or check["squares_missing_or_extra"]:
            raise RuntimeError(
                f"The stored weather does not reproduce the published estimates for {day}: "
                f"{check['squares_different']} squares differ and {check['squares_missing_or_extra']} are missing or extra."
            )
    summary["phases_seconds"]["load_and_reproduce"] = round(time.monotonic() - phase, 1)

    # The saved newest files against the run file of the same run.
    phase = time.monotonic()
    interpolation_rows, interpolation_info = check_interpolation(newest=newest, settings=settings, totals=totals)
    summary["interpolation_check"] = interpolation_info
    interpolation_path = reports_dir / "bulk_weather_estimates_interpolation.csv"
    write_csv(rows=interpolation_rows, columns=INTERPOLATION_COLUMNS, path=interpolation_path)
    context.add_output(interpolation_path)
    summary["phases_seconds"]["interpolation_check"] = round(time.monotonic() - phase, 1)
    save_summary()

    day_rows: list[dict[str, Any]] = []
    cell_rows: list[dict[str, Any]] = []
    published_by_date: dict[date, dict[int, np.ndarray]] = {}
    summary["dates"] = {}
    for day in dates:
        phase = time.monotonic()
        data = data_by_date[day]
        info: dict[str, Any] = {}
        summary["dates"][day.isoformat()] = info
        first_hour, end_hour = window_hours(assessment_date=day, settings=settings)
        catalog = catalog_runs(
            domain_path=IFS_PATH,
            step_hours=6,
            first=datetime.combine(day - timedelta(days=3), datetime.min.time(), tzinfo=UTC),
            last=max(cell.fetch_time for cell in data.cells).replace(minute=0, second=0, microsecond=0),
            totals=totals,
        )
        arrays, ifs_report = build_ifs_weather(
            assessment_date=day, data=data, newest=newest, catalog=catalog, settings=settings, totals=totals
        )
        info["ifs"] = ifs_report
        matches = [newest.matches[cell.cell_key] for cell in data.cells]
        elevations = [match.place_height if not math.isnan(match.place_height) else match.point_height for match in matches]
        add_evapotranspiration(
            arrays=arrays,
            elevations=elevations,
            coordinates=[bw.point_coordinates(point=match.point) for match in matches],
            first_hour=first_hour,
        )
        print(f"{day}: ifs weather built from {len(ifs_report['runs'])} runs", flush=True)
        icon, icon_report = build_icon_weather(
            assessment_date=day, data=data, place_heights=elevations, settings=settings, totals=totals
        )
        info["icon_2i"] = icon_report
        variants = {"ifs": arrays, "icon_2i": apply_icon(arrays=arrays, icon=icon, elevations=elevations, first_hour=first_hour)}
        hourly_path = context.output_dir / f"hourly_weather_{day.isoformat()}.npz"
        np.savez_compressed(
            hourly_path,
            first_hour=first_hour,
            cells=np.array([cell.cell_key for cell in data.cells]),
            **{f"{variant}_{name}": values.astype(np.float32) for variant, arrays_of in variants.items() for name, values in arrays_of.items()},
        )
        context.add_output(hourly_path)
        info["seconds_weather"] = round(time.monotonic() - phase, 1)
        print(f"{day}: icon weather built, {icon_report['cell_hours_without_value']} cell hours without a value", flush=True)

        # Estimates on the file weather and comparison with the published values.
        phase = time.monotonic()
        file_values: dict[str, list[np.ndarray]] = {variant: [] for variant in VARIANTS}
        published_list: list[np.ndarray] = []
        cell_index: list[int] = []
        order_ids: list[int] = []
        published_by_date[day] = {}
        for index, cell in enumerate(data.cells):
            order = sorted(cell.published)
            published = published_values(cell=cell, order=order)
            published_list.append(published)
            cell_index.extend([index] * len(order))
            order_ids.extend(order)
            for forest_cell_id, row in zip(order, published, strict=True):
                published_by_date[day][forest_cell_id] = row
            for variant in VARIANTS:
                rows = daily_rows(arrays=variants[variant], row=index, cell=cell, first_hour=first_hour, settings=settings)
                results = estimate_cell(cell=cell, rows=rows)
                mine = to_array(values={key: value[1] for key, value in results.items()}, order=order)
                file_values[variant].append(mine)
                both = (mine >= 0) & (published >= 0)
                gap = np.abs(mine[both] - published[both]).astype(float)
                cell_rows.append(
                    cell_row(assessment_date=day, variant=variant, cell=cell, rows=rows, estimate_gap=gap, settings=settings)
                )
            if index % 50 == 0:
                print(f"{day}: estimates for {index + 1} of {len(data.cells)} cells", flush=True)
        published_all = np.concatenate(published_list)
        arrays_to_save: dict[str, np.ndarray] = {
            "forest_cell_id": np.array(order_ids),
            "cell_index": np.array(cell_index),
            "published": published_all,
        }
        for variant in VARIANTS:
            files_all = np.concatenate(file_values[variant])
            arrays_to_save[variant] = files_all
            for offset in range(TARGET_DAYS):
                day_rows.append(
                    difference_row(
                        label={
                            "assessment_date": day.isoformat(),
                            "variant": variant,
                            "target_date": (day + timedelta(days=offset)).isoformat(),
                            "days_ahead": offset,
                        },
                        mine=files_all[:, offset],
                        other=published_all[:, offset],
                        large=settings["large_difference_points"],
                    )
                )
        estimates_path = context.output_dir / f"estimates_{day.isoformat()}.npz"
        np.savez_compressed(estimates_path, **arrays_to_save)
        context.add_output(estimates_path)
        info["seconds_estimates"] = round(time.monotonic() - phase, 1)
        info["squares"] = int(published_all.shape[0])
        summary["phases_seconds"][f"date_{day.isoformat()}"] = round(time.monotonic() - phase, 1)
        save_summary()
        print(f"{day}: estimates compared for {info['squares']} squares", flush=True)

    # The night-to-night yardstick: the published run of the latest date against the published run of the earliest date.
    if len(dates) >= 2:
        first_day, last_day = dates[0], dates[-1]
        shared = sorted(set(published_by_date[first_day]) & set(published_by_date[last_day]))
        shift = (last_day - first_day).days
        older = np.stack([published_by_date[first_day][key] for key in shared])
        newer = np.stack([published_by_date[last_day][key] for key in shared])
        for offset in range(TARGET_DAYS - shift):
            day_rows.append(
                difference_row(
                    label={
                        "assessment_date": last_day.isoformat(),
                        "variant": f"published_{last_day.day}_vs_{first_day.day}",
                        "target_date": (last_day + timedelta(days=offset)).isoformat(),
                        "days_ahead": offset,
                    },
                    mine=newer[:, offset],
                    other=older[:, offset + shift],
                    large=settings["large_difference_points"],
                )
            )

    days_path = reports_dir / "bulk_weather_estimates_days.csv"
    write_csv(rows=day_rows, columns=DAYS_COLUMNS, path=days_path)
    context.add_output(days_path)
    cells_path = reports_dir / "bulk_weather_estimates_cells.csv"
    write_csv(rows=cell_rows, columns=CELL_COLUMNS, path=cells_path)
    context.add_output(cells_path)

    summary["bucket_reads"] = {"megabytes": round(totals.bytes / 1e6, 2), "requests": totals.requests, "files": len(totals.files)}
    summary["database_after"] = database_state(region_code=region_code, run_ids=run_ids)
    summary["database_unchanged"] = summary["database_before"] == summary["database_after"]
    summary["seconds_total"] = round(time.monotonic() - started, 1)
    save_summary()
    context.add_output(summary_path)
    assert_read_only()
    if not summary["database_unchanged"]:
        raise RuntimeError("The published run pointers or the row counts changed during the run. See summary.json.")
