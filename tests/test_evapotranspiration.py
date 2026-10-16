"""Checks of the evapotranspiration formulas against FAO-56 worked examples."""

import math
from datetime import UTC, datetime

import pytest

from sporameteo.weather.evapotranspiration import (
    air_pressure,
    hourly_reference_evapotranspiration,
    psychrometric_constant,
    saturation_vapour_pressure,
    top_of_atmosphere_radiation,
    wind_factor_10m_to_2m,
)

NDIAYE_LATITUDE = 16 + 13 / 60
NDIAYE_LONGITUDE = -(16 + 15 / 60)
FAO_RADIATION_TO_W_M2 = 1 / 0.0036


def _dew_point_from_humidity(*, temperature_c: float, humidity_percent: float) -> float:
    ea = saturation_vapour_pressure(temperature_c=temperature_c) * humidity_percent / 100
    log_ratio = math.log(ea / 0.6108)
    return 237.3 * log_ratio / (17.27 - log_ratio)


def test_air_pressure_and_psychrometric_constant_at_1800_m() -> None:
    assert air_pressure(elevation_m=1800) == pytest.approx(81.8, abs=0.1)
    assert psychrometric_constant(elevation_m=1800) == pytest.approx(0.054, abs=0.0005)


def test_wind_at_10_m_becomes_2_4_m_s_at_2_m() -> None:
    assert 3.2 * wind_factor_10m_to_2m() == pytest.approx(2.4, abs=0.02)


def test_top_of_atmosphere_radiation_matches_fao_for_ndiaye_afternoon() -> None:
    value = top_of_atmosphere_radiation(
        latitude=NDIAYE_LATITUDE,
        longitude=NDIAYE_LONGITUDE,
        hour_end=datetime(2026, 10, 1, 16, tzinfo=UTC),
    )
    assert value == pytest.approx(3.543 * FAO_RADIATION_TO_W_M2, rel=0.02)


def test_top_of_atmosphere_radiation_is_zero_at_night() -> None:
    value = top_of_atmosphere_radiation(
        latitude=NDIAYE_LATITUDE,
        longitude=NDIAYE_LONGITUDE,
        hour_end=datetime(2026, 10, 1, 4, tzinfo=UTC),
    )
    assert value == 0.0


def test_evapotranspiration_matches_fao_example_19_afternoon() -> None:
    dew_point = _dew_point_from_humidity(temperature_c=38, humidity_percent=52)
    assert saturation_vapour_pressure(temperature_c=38) == pytest.approx(6.625, abs=0.005)
    assert saturation_vapour_pressure(temperature_c=dew_point) == pytest.approx(3.445, abs=0.005)
    et0 = hourly_reference_evapotranspiration(
        temperature_c=38,
        dew_point_c=dew_point,
        shortwave_radiation_w_m2=2.450 * FAO_RADIATION_TO_W_M2,
        wind_speed_10m_m_s=3.3 / wind_factor_10m_to_2m(),
        elevation_m=8,
        top_of_atmosphere_w_m2=3.543 * FAO_RADIATION_TO_W_M2,
    )
    assert et0 == pytest.approx(0.63, abs=0.01)


def test_evapotranspiration_is_close_to_zero_at_night() -> None:
    et0 = hourly_reference_evapotranspiration(
        temperature_c=28,
        dew_point_c=_dew_point_from_humidity(temperature_c=28, humidity_percent=79),
        shortwave_radiation_w_m2=0,
        wind_speed_10m_m_s=1.9 / wind_factor_10m_to_2m(),
        elevation_m=8,
        top_of_atmosphere_w_m2=0,
    )
    assert 0 <= et0 < 0.05


def test_negative_evapotranspiration_is_clipped_to_zero() -> None:
    et0 = hourly_reference_evapotranspiration(
        temperature_c=-5,
        dew_point_c=-5,
        shortwave_radiation_w_m2=0,
        wind_speed_10m_m_s=0,
        elevation_m=500,
        top_of_atmosphere_w_m2=0,
    )
    assert et0 == 0.0
