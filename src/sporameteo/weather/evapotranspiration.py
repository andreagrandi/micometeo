"""Hourly reference evapotranspiration, copied from Open-Meteo's FAO-56 code.

It differs from FAO-56 in two ways. The night ratio of radiation comes from humidity, and the sun position uses NOAA formulas instead of NREL.
"""

import math
from datetime import UTC, datetime

SOLAR_CONSTANT_W_M2 = 1367.7
_BETA = 17.27
_LAMBDA = 237.3


def saturation_vapour_pressure(*, temperature_c: float) -> float:
    """Return the vapour pressure in kPa of air saturated at this temperature.

    Open-Meteo uses the same formula for the dew point to get the actual pressure.
    """
    return 0.6108 * math.exp(_BETA * temperature_c / (temperature_c + _LAMBDA))


def air_pressure(*, elevation_m: float) -> float:
    """Return the air pressure in kPa at this elevation.

    This is FAO-56 equation 7.
    """
    return 101.3 * ((293 - 0.0065 * elevation_m) / 293) ** 5.26


def psychrometric_constant(*, elevation_m: float) -> float:
    """Return the psychrometric constant in kPa per degree Celsius.

    This is FAO-56 equation 8.
    """
    return 0.000665 * air_pressure(elevation_m=elevation_m)


def wind_factor_10m_to_2m() -> float:
    """Return the factor that turns wind at 10 m into wind at 2 m.

    Open-Meteo uses the FAO logarithmic profile, valid below 100 m.
    """
    factor_from = 4.87 / math.log(67.8 * 10 - 5.42)
    factor_to = 4.87 / math.log(67.8 * 2 - 5.42)
    return factor_from / factor_to


def _sun_position(*, moment: datetime) -> tuple[float, float, float]:
    """Return sun declination in degrees, equation of time in hours and sun distance in AU.

    Open-Meteo reads declination and equation of time from a table built with the NREL algorithm. This uses the NOAA fractional year series instead.
    """
    moment = moment.astimezone(UTC)
    day_of_year = moment.timetuple().tm_yday
    hour = moment.hour + moment.minute / 60 + moment.second / 3600
    year_days = 366 if moment.year % 4 == 0 and (moment.year % 100 != 0 or moment.year % 400 == 0) else 365
    gamma = 2 * math.pi / year_days * (day_of_year - 1 + (hour - 12) / 24)
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    equation_of_time_minutes = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    # Open-Meteo's own earth-sun distance, using the day in an average year of 365.25 days.
    seconds_in_average_year = int(moment.timestamp()) % 31_557_600
    day = seconds_in_average_year / 86400 - 4 + 1
    sun_distance = 1 - 0.01672 * math.cos(math.radians(360 / 365.256363 * day))
    return math.degrees(declination), equation_of_time_minutes / 60, sun_distance


def top_of_atmosphere_radiation(*, latitude: float, longitude: float, hour_end: datetime) -> float:
    """Return the sun power in W/m2 above the atmosphere, averaged over the hour ending at hour_end.

    The sun height is integrated between sunrise and sunset and divided by the full hour.
    """
    declination, equation_of_time, sun_distance = _sun_position(moment=hour_end)
    utc_end = hour_end.astimezone(UTC)
    ut = utc_end.hour + utc_end.minute / 60 + utc_end.second / 3600

    colatitude_sun = math.radians(90 - declination)
    p1 = math.radians(-15.0 * (ut - 12.0 + equation_of_time))
    p10 = math.radians(-15.0 * (ut - 1.0 - 12.0 + equation_of_time))

    colatitude = math.radians(90 - latitude)
    p0 = math.radians(longitude)
    if p0 < p1 - math.pi:
        p0 += 2 * math.pi
    if p0 > p1 + math.pi:
        p0 -= 2 * math.pi

    cos_cc = math.cos(colatitude) * math.cos(colatitude_sun)
    sin_ss = math.sin(colatitude) * math.sin(colatitude_sun)
    arg = -cos_cc / sin_ss
    carg = math.pi if arg > 1 or arg < -1 else math.acos(arg)

    sunrise = p0 + carg
    sunset = p0 - carg
    if p10 < sunset or p1 > sunrise:
        return 0.0
    p1_limited = min(sunrise, p10)
    p10_limited = max(sunset, p1)

    left = sin_ss * math.sin(p1_limited - p0) + p1_limited * cos_cc
    right = sin_ss * math.sin(p10_limited - p0) + p10_limited * cos_cc
    sun_height = (left - right) / (p10 - p1)
    return sun_height / (sun_distance * sun_distance) * SOLAR_CONSTANT_W_M2


def hourly_reference_evapotranspiration(
    *,
    temperature_c: float,
    dew_point_c: float,
    shortwave_radiation_w_m2: float,
    wind_speed_10m_m_s: float,
    elevation_m: float,
    top_of_atmosphere_w_m2: float,
) -> float:
    """Return the reference evapotranspiration in mm for one hour.

    This is the FAO-56 Penman-Monteith equation as Open-Meteo applies it to hourly values.
    """
    temp = temperature_c
    wind_2m = wind_factor_10m_to_2m() * wind_speed_10m_m_s
    esat = saturation_vapour_pressure(temperature_c=temp)
    ea = saturation_vapour_pressure(temperature_c=dew_point_c)
    vapour_deficit = esat - ea
    slope = 4098 * esat / (temp + _LAMBDA) ** 2
    gamma = psychrometric_constant(elevation_m=elevation_m)

    net_shortwave = shortwave_radiation_w_m2 * (1 - 0.23) * 0.0864 / 24
    clear_sky_radiation = (0.75 + 0.00002 * elevation_m) * top_of_atmosphere_w_m2
    humidity = 100 * math.exp(17.625 * dew_point_c / (243.04 + dew_point_c)) / math.exp(17.625 * temp / (243.04 + temp))
    humidity = min(max(humidity, 0), 100)
    if top_of_atmosphere_w_m2 <= 0:
        # FAO-56 uses the ratio of the last hours before sunset. Open-Meteo guesses it from humidity.
        relative_radiation = 0.8 - humidity / 100 * 0.4
    else:
        relative_radiation = min(shortwave_radiation_w_m2 / clear_sky_radiation, 1)
    net_longwave = (
        0.20429166e-9
        * (temp + 273.16) ** 4
        * (0.34 - 0.14 * math.sqrt(ea))
        * (1.35 * relative_radiation - 0.35)
    )
    net_radiation = net_shortwave - net_longwave
    soil_heat = 0.5 * net_radiation if shortwave_radiation_w_m2 <= 0 else 0.1 * net_radiation

    et0 = (
        0.408 * slope * (net_radiation - soil_heat)
        + gamma * (37 / (temp + 273)) * wind_2m * vapour_deficit
    ) / (slope + gamma * (1 + 0.34 * wind_2m))
    return max(et0, 0.0)
