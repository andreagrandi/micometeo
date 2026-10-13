"""Print controlled v3 checks without changing saved estimates.

These examples measure formula behavior, not biological accuracy.
"""

from dataclasses import replace
from datetime import date, timedelta
import json

from micometeo.forecast_method import (
    DailyTemperatures,
    ForecastInputs,
    HostTrees,
    METHOD_V3,
    NumericInput,
    calculate_forecast,
)


def numeric(*, value: float, unit: str, start: date, end: date, days: int) -> NumericInput:
    return NumericInput(
        value=value, unit=unit, source_id="controlled-audit",
        period_start=start, period_end=end,
        completed_day_count=days, forecast_day_count=0,
    )


def run() -> None:
    day = date(2026, 10, 12)
    temperatures = DailyTemperatures(
        daily_means=(13.7,) * 20, daily_minimums=(8.0,) * 20,
        unit="deg_c", source_id="controlled-audit",
        period_start=day - timedelta(days=19), period_end=day,
        completed_day_count=19, forecast_day_count=1,
        semantic="temperature_at_reference_altitude",
    )
    base = ForecastInputs(
        assessment_date=day, target_date=day,
        old_rain=numeric(value=60, unit="mm", start=day - timedelta(days=21), end=day - timedelta(days=8), days=14),
        recent_rain=numeric(value=30, unit="mm", start=day - timedelta(days=7), end=day - timedelta(days=1), days=7),
        target_temperature=None, period_temperatures=temperatures,
        reference_altitude=numeric(value=500, unit="m", start=day, end=day, days=1),
        square_altitude=numeric(value=500, unit="m", start=day, end=day, days=1),
        forest_share=numeric(value=1, unit="fraction", start=day, end=day, days=1),
    )
    cases = {
        "ideal_missing_hosts": base,
        "dry_older_window_100mm_recent": replace(base, old_rain=replace(base.old_rain, value=0), recent_rain=replace(base.recent_rain, value=100)),
        "older_0_5mm_100mm_recent": replace(base, old_rain=replace(base.old_rain, value=0.5), recent_rain=replace(base.recent_rain, value=100)),
        "older_30mm_no_recent_rain": replace(base, old_rain=replace(base.old_rain, value=30), recent_rain=replace(base.recent_rain, value=0)),
        "older_30mm_100mm_recent": replace(base, old_rain=replace(base.old_rain, value=30), recent_rain=replace(base.recent_rain, value=100)),
        "four_frost_nights": replace(base, period_temperatures=replace(temperatures, daily_minimums=(-2.0,) * 4 + (8.0,) * 16)),
        "mean_10_degrees": replace(base, period_temperatures=replace(temperatures, daily_means=(10.0,) * 20)),
        "mean_20_degrees": replace(base, period_temperatures=replace(temperatures, daily_means=(20.0,) * 20)),
        "forest_10_percent": replace(base, forest_share=replace(base.forest_share, value=0.1)),
        "forest_9_percent": replace(base, forest_share=replace(base.forest_share, value=0.09)),
        "complete_zero_hosts": replace(base, host_trees=HostTrees(values=(0, 0, 0, 0, 0), source_id="controlled-audit", source_year=2006, resolution_m=1000)),
    }
    output = {}
    for name, inputs in cases.items():
        result = calculate_forecast(inputs=inputs, method=METHOD_V3)
        output[name] = {
            "percentage": result.whole_percentage,
            "unavailable_reason": result.unavailable_reason,
        }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    run()
