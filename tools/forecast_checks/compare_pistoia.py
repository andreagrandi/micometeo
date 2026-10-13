"""Replay captured Pistoia weather through the proposed moisture rules.

This command reads a small local evidence file and does not access the database.
"""

from dataclasses import asdict
from datetime import date, timedelta
import json
from pathlib import Path

from tools.forecast_checks.moisture_candidate import WeatherDay, calculate_candidate


def run() -> None:
    evidence = json.loads(Path(__file__).with_name("pistoia_2026_10_12.json").read_text())
    start = date.fromisoformat(evidence["period_start"])
    output = {}
    for name, provider in evidence["providers"].items():
        adjustment = 0.0065 * (evidence["square_altitude_m"] - provider["reference_altitude_m"])
        rows = zip(provider["rain_mm"], provider["temperature_c"], provider["et0_mm"], strict=True)
        days = tuple(WeatherDay(day=start + timedelta(days=index), rain_mm=rain,
                                temperature_c=temperature - adjustment, et0_mm=et0)
                     for index, (rain, temperature, et0) in enumerate(rows))
        result = calculate_candidate(target_date=date.fromisoformat(evidence["assessment_date"]),
                                     days=days, forest_share=evidence["forest_share"])
        output[name] = asdict(result)
    station = evidence["sammomme"]
    output["sammomme_recent_rain_mm"] = {
        name: round(sum(station[name]), 2)
        for name in ("gauge_daily_increase_mm", "forecast_daily_mm", "historical_daily_mm")
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    run()
