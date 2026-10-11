"""Offline checks of the P4b weather and habitat features."""

import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import rasterio

from micometeo.benchmark import features
from micometeo.benchmark.features import (
    DailySeries,
    block_forest_shares,
    build_feature_table,
    daily_values,
    day_number,
    era5_cell,
    local_day_numbers,
    parse_square_id,
    read_cell_file,
    tile_slope,
    window_values,
)


def hours_between(*, start: str, end: str) -> np.ndarray:
    first = int((np.datetime64(start) - np.datetime64("1970-01-01T00:00")) / np.timedelta64(1, "h"))
    last = int((np.datetime64(end) - np.datetime64("1970-01-01T00:00")) / np.timedelta64(1, "h"))
    return np.arange(first, last + 1)


def test_era5_cell_rounds_to_quarter_degrees() -> None:
    assert era5_cell(latitude=42.62, longitude=11.12) == (42.5, 11.0)
    assert era5_cell(latitude=42.63, longitude=11.13) == (42.75, 11.25)
    assert era5_cell(latitude=46.0, longitude=6.07) == (46.0, 6.0)


def test_local_day_uses_summer_offset_of_two_hours() -> None:
    hours = hours_between(start="2020-07-01T21:00", end="2020-07-01T22:00")
    days = local_day_numbers(hours=hours)
    assert days[0] == day_number(text="2020-07-01")
    assert days[1] == day_number(text="2020-07-02")


def test_local_day_uses_winter_offset_of_one_hour() -> None:
    hours = hours_between(start="2020-01-01T22:00", end="2020-01-01T23:00")
    days = local_day_numbers(hours=hours)
    assert days[0] == day_number(text="2020-01-01")
    assert days[1] == day_number(text="2020-01-02")


def test_rain_at_italian_midnight_belongs_to_the_previous_day() -> None:
    hours = hours_between(start="2020-01-08T12:00", end="2020-01-12T12:00")
    values = np.zeros(hours.size)
    midnight = int((np.datetime64("2020-01-10T23:00") - np.datetime64("1970-01-01T00:00")) / np.timedelta64(1, "h"))
    values[midnight - hours[0]] = 2.0  # hour ending 00:00 Italian time on 11 January
    first_day, daily = daily_values(hours=hours, values=values, shift_hours=1, average=False)
    assert daily[day_number(text="2020-01-10") - first_day] == pytest.approx(2.0)
    assert daily[day_number(text="2020-01-11") - first_day] == pytest.approx(0.0)


def test_day_with_a_missing_hour_is_nan() -> None:
    hours = hours_between(start="2020-01-08T12:00", end="2020-01-12T12:00")
    keep = hours != hours_between(start="2020-01-10T05:00", end="2020-01-10T05:00")[0]
    first_day, daily = daily_values(hours=hours[keep], values=np.ones(keep.sum()), shift_hours=0, average=True)
    assert np.isnan(daily[day_number(text="2020-01-10") - first_day])
    assert daily[day_number(text="2020-01-09") - first_day] == pytest.approx(1.0)
    assert daily[day_number(text="2020-01-11") - first_day] == pytest.approx(1.0)


def test_days_at_the_start_and_end_of_the_file_are_nan_when_partial() -> None:
    hours = hours_between(start="2020-01-08T12:00", end="2020-01-12T12:00")
    first_day, daily = daily_values(hours=hours, values=np.ones(hours.size), shift_hours=0, average=True)
    assert np.isnan(daily[0])
    assert np.isnan(daily[-1])
    assert not np.isnan(daily[1])


def test_day_of_a_clock_change_needs_all_of_its_23_hours() -> None:
    hours = hours_between(start="2020-03-27T00:00", end="2020-04-01T00:00")
    first_day, daily = daily_values(hours=hours, values=np.full(hours.size, 3.0), shift_hours=0, average=False)
    assert daily[day_number(text="2020-03-29") - first_day] == pytest.approx(23 * 3.0)
    assert daily[day_number(text="2020-03-28") - first_day] == pytest.approx(24 * 3.0)


def make_series() -> DailySeries:
    first = day_number(text="2020-06-01")
    rain = np.arange(1.0, 41.0)  # 1 mm on 1 June, 2 mm on 2 June, and so on
    temp = np.full(40, 15.0)
    return DailySeries(first_day=first, rain_mm=rain, temp_c=temp)


def test_window_ends_on_the_day_before_the_assessment_date() -> None:
    series = make_series()
    day = np.array([day_number(text="2020-06-11")])
    rain = window_values(series=series, day_numbers=day, days=7, kind="rain")
    assert rain[0] == pytest.approx(sum(range(4, 11)))  # 4 to 10 June, not 11 June
    temp = window_values(series=series, day_numbers=day, days=7, kind="temp")
    assert temp[0] == pytest.approx(15.0)


def test_window_is_nan_when_one_day_is_missing() -> None:
    series = make_series()
    series.rain_mm[7] = np.nan  # 8 June
    days = np.array([day_number(text="2020-06-11"), day_number(text="2020-06-16")])
    rain = window_values(series=series, day_numbers=days, days=7, kind="rain")
    assert np.isnan(rain[0])
    assert rain[1] == pytest.approx(sum(range(9, 16)))


def test_window_is_nan_outside_the_series() -> None:
    series = make_series()
    days = np.array([day_number(text="2020-06-05"), day_number(text="2020-07-15")])
    rain = window_values(series=series, day_numbers=days, days=7, kind="rain")
    assert np.isnan(rain).all()


def test_forest_shares_on_a_tiny_pixel_array() -> None:
    pixels = np.zeros((5, 10), dtype="uint8")
    pixels[:, :5] = 1
    pixels[:2, :5] = 2  # first square: 10 conifer, 15 broadleaf, no empty pixels
    pixels[:, 5:] = 0
    pixels[0, 5] = 255  # second square: one unusable pixel, no forest
    forest, broadleaf = block_forest_shares(pixels=pixels)
    assert forest.shape == (1, 2)
    assert forest[0, 0] == pytest.approx(1.0)
    assert broadleaf[0, 0] == pytest.approx(15 / 25)
    assert forest[0, 1] == pytest.approx(0.0)
    assert np.isnan(broadleaf[0, 1])


def test_square_fully_unusable_has_no_forest_share() -> None:
    forest, broadleaf = block_forest_shares(pixels=np.full((5, 5), 254, dtype="uint8"))
    assert np.isnan(forest[0, 0])
    assert np.isnan(broadleaf[0, 0])


def test_square_id_gives_lower_left_corner() -> None:
    assert parse_square_id(cell_id="500m_E4465500_N2301000") == (4465500, 2301000)
    with pytest.raises(ValueError):
        parse_square_id(cell_id="100km_E4000000_N2500000")


def test_slope_of_a_plane_rising_to_the_east() -> None:
    columns = np.arange(20, dtype="float32")
    latitude_step = 3 / 3600
    step_east = latitude_step * features.METRES_PER_DEGREE_LATITUDE * np.cos(np.radians(45.0))
    altitude = np.tile(columns * step_east, (20, 1)).astype("float32")  # 45 degrees at about 45 N
    slope = tile_slope(altitude=altitude, top=45.0, latitude_step=latitude_step)
    assert slope[10, 10] == pytest.approx(45.0, abs=1.0)


def write_cell_zip(*, path: Path, start: str, end: str) -> None:
    hours = hours_between(start=start, end=end)
    lines = ["valid_time,t2m,tp,latitude,longitude"]
    for hour in hours:
        moment = datetime(1970, 1, 1) + timedelta(hours=int(hour))
        lines.append(f"{moment:%Y-%m-%d %H:%M:%S},{273.15 + 10.0},0.001,42.5,11.0")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("data.csv", "\n".join(lines) + "\n")


def test_read_cell_file_gives_daily_mm_and_celsius(tmp_path: Path) -> None:
    path = tmp_path / "era5_lat42.50_lon11.00.zip"
    write_cell_zip(path=path, start="2020-06-01T00:00", end="2020-06-05T00:00")
    series = read_cell_file(path=path)
    day = day_number(text="2020-06-03") - series.first_day
    assert series.rain_mm[day] == pytest.approx(24.0)
    assert series.temp_c[day] == pytest.approx(10.0)


def test_feature_table_rows_and_columns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    weather_dir = tmp_path / "weather"
    weather_dir.mkdir()
    write_cell_zip(path=weather_dir / "era5_lat42.50_lon11.00.zip", start="2020-06-01T00:00", end="2020-07-20T00:00")
    (weather_dir / "era5_lat42.50_lon11.00.zip.download.json").write_text(
        '{"downloaded_at": "2026-10-11T08:00:00+00:00", "url": "u", "query": {}}', encoding="utf-8"
    )

    def case(case_id: str, *, year: int, group: str, date_text: str) -> dict:
        return {
            "case_id": case_id, "area": "home", "cell_id": "500m_E4465500_N2301000", "assessment_date": date_text,
            "year": year, "block_id": "100km_E4400000_N2300000", "block_group": group, "set": group,
            "record_ids": ["a"], "find_count": 1, "latitude": 42.51, "longitude": 11.01,
        }  # fmt: skip

    cases = [
        case("keep_a", year=2020, group="tuning", date_text="2020-07-10"),
        case("keep_b", year=2020, group="test", date_text="2020-07-15"),
        case("old", year=2016, group="tuning", date_text="2016-07-10"),
        case("buffered", year=2020, group="buffer", date_text="2020-07-10"),
    ]
    pq.write_table(pa.Table.from_pylist(cases), run_dir / "cases.parquet")
    points = [
        {
            "case_id": case_id, "set": group, "area": "home", "point_kind": "forest", "cell_id": "500m_E4466000_N2301000",
            "latitude": 42.52, "longitude": 11.02, "assessment_date": date_text,
        }  # fmt: skip
        for case_id, group, date_text in (
            ("keep_a", "tuning", "2020-07-10"),
            ("keep_a", "tuning", "2020-07-10"),
            ("keep_b", "test", "2020-07-15"),
            ("old", "tuning", "2016-07-10"),
            ("buffered", "buffer", "2020-07-10"),
        )
    ]
    pq.write_table(pa.Table.from_pylist(points), run_dir / "comparison_points.parquet")
    monkeypatch.setattr(
        features,
        "forest_features",
        lambda *, east, north, tile_paths: (np.full(east.size, 0.5), np.full(east.size, 0.25), []),
    )
    monkeypatch.setattr(
        features,
        "terrain_features",
        lambda *, east, north, latitudes, longitudes, dem_dir: (np.full(east.size, 300.0), np.full(east.size, 5.0), []),
    )
    table, missing, sources = build_feature_table(
        run_dir=run_dir, weather_dir=weather_dir, forest_tiles=[], dem_dir=tmp_path / "dem"
    )
    assert table.column_names == features.OUTPUT_COLUMNS
    assert table.num_rows == 5
    assert table["point_kind"].to_pylist().count("find") == 2
    assert set(table["case_id"].to_pylist()) == {"keep_a", "keep_b"}
    assert set(table["year"].to_pylist()) == {2020}
    assert missing == []
    assert len(sources) == 1
    assert table["rain_7d_mm"].to_pylist() == pytest.approx([168.0] * 5)
    assert table["temp_30d_c"].to_pylist() == pytest.approx([10.0] * 5)
    assert table["forest_share"][0].as_py() == 0.5


def test_cells_without_a_file_give_nan_and_are_listed(tmp_path: Path) -> None:
    weather, missing, sources = features.weather_features(
        latitudes=np.array([42.5]),
        longitudes=np.array([11.0]),
        dates=["2020-07-10"],
        weather_dir=tmp_path,
    )
    assert missing == [(42.5, 11.0)]
    assert sources == []
    assert np.isnan(weather["rain_7d_mm"]).all()


def test_temperature_moves_to_the_height_of_the_square() -> None:
    # Two cells with centres at 46.0 N, 8.0 E and 8.25 E, at 500 m and 1,500 m.
    heights = np.array([[500.0, 1500.0]])
    transform = rasterio.Affine(0.25, 0.0, 7.875, 0.0, -0.25, 46.125)
    table = {
        "latitude": np.array([46.0, 46.0]),
        "longitude": np.array([8.0, 8.3]),
        "altitude_m": np.array([1500.0, 1500.0]),
        **{f"temp_{days}d_c": np.array([10.0, 10.0]) for days in (7, 14, 30)},
    }
    corrected = features.correct_temperatures(table=table, heights=heights, transform=transform)
    assert np.allclose(corrected["temp_14d_c"], [3.5, 10.0])
    assert np.allclose(table["temp_14d_c"], [10.0, 10.0])
