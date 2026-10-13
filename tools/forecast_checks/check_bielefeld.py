"""Count dated fruiting observations exposed to the current older-rain veto.

This checks evidence coverage and does not fit or validate a new formula.
"""

import csv
from datetime import date, timedelta
import io
import json
from pathlib import Path
import zipfile


def run() -> None:
    path = Path("data/raw/p4b_bielefeld/Boletus_fruiting_triggers-V1.2.zip")
    with zipfile.ZipFile(file=path) as archive:
        name = next(name for name in archive.namelist() if name.endswith("Environmental_fruiting_data_jun8.csv"))
        reader = csv.DictReader(io.StringIO(archive.read(name=name).decode()))
        rows = {date.fromisoformat(row["Date"]): row for row in reader if row["site"] == "All"}
    counts = {"complete_older_windows": 0, "fruiting_days": 0,
              "zero_older_rain_days": 0, "fruiting_with_zero_older_rain": 0}
    for day, row in sorted(rows.items()):
        dates = [day - timedelta(days=offset) for offset in range(8, 22)]
        if any(previous not in rows for previous in dates):
            continue
        rain = sum(float(rows[previous]["Precip"]) for previous in dates)
        fruiting = float(row["Mnb"]) > 0
        counts["complete_older_windows"] += 1
        counts["fruiting_days"] += int(fruiting)
        counts["zero_older_rain_days"] += int(rain == 0)
        counts["fruiting_with_zero_older_rain"] += int(fruiting and rain == 0)
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    run()
