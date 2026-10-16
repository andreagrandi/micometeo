# Estimates from file weather against the published estimates

Issue #127, part of epic #123.

## Question

How much do the Tuscany estimates change when the weather comes from the
`ecmwf_ifs` files instead of the API's `best_match`? Does the Italian 2 km
model ICON-2I, read from files for the first 60 hours, bring them closer?

## Answer

For past days the files give the same weather as the API. For the days ahead
they give a different forecast.

- The 30 past days match. Rain and soil moisture are the same as the stored
  values in all 333 cells. Evapotranspiration differs by a median of 0.5 mm
  over 30 days, as issue 126 found.
- On 16 October, estimates for today and the next 2 days match. The typical
  difference is 0 points and the largest is 8 points.
- From day 3 on, the estimates move a lot. The typical difference is 7 to 12
  points, and the file estimates are 6 to 12 points higher on average. That
  is larger than the change between two published runs 3 nights apart, so
  the stop rule was reached.
- ICON-2I changes almost nothing. Its 60 hours cover days 0 to 2, where the
  two sources already agree.

The cause is the forecast, not the reader. For the days ahead, `best_match`
takes rain and temperature from the German ICON models first. The files hold
only the ECMWF forecast. This week the two models disagree on a storm from 18
to 21 October. Day 3 is 19 October, the first day whose estimate depends on
rain from 18 October.

Recommendation: use the files for past days only. Keep the API for today and
the 7 days ahead. The numbers behind it are in AC4.

Owner decision, 16 October 2026: take every day from the files, past days and
the days ahead, and accept the ECMWF forecast. See D23 in
`docs/decisions.md`.

Run: `reports/runs/bulk_weather_estimates/20261016T113336Z-783222.json`.
Script: `experiments/bulk_weather_estimates/run.py`. Details of the run are in
`data/processed/bulk_weather_estimates/20261016T113336Z-783222/summary.json`.

## Dates compared

The issue asks for 3 recent dates with a published Tuscany run. The local
database held one, 13 October, run `712b336a`. Its weather was fetched on
14 October. With the owner's agreement, the app's normal Tuscany night ran for
16 October on 16 October. It cost 8 requests and 666 counted calls, from 11:06
to 11:17 UTC, and published run `0e1bb4cf`.

Only 16 October was compared with the files. The stop rule was reached on
this first date, so the other date was not run. 13 October is used only as
the yardstick for the stop rule.

16 October is the fairest date for this test. The API answered from the
`ecmwf_ifs` 00 UTC run of 16 October, which appeared in the bucket at
06:33 UTC. Before the 06 UTC run replaced it, the files of that run were saved
for the 256 grid points of the Tuscany cells, 28 MB, in
`data/raw/bulk_weather_estimates/newest_files_20261016/`. File weather and API
weather therefore come from the same hours of the same ECMWF run.

## How the comparison works

For each of the 333 cells:

1. The grid point and the height correction are chosen as the API does, with
   the code from issue 125. That code picked the same grid point as the
   archive API for all 353 Tuscany cells checked in issue 125.
2. Hourly rain, temperature, dew point, radiation, wind and soil values come
   from the saved files for the 38 days from 16 September to 23 October.
   Evapotranspiration comes from the function of issue 126.
3. Hours become days with the app's own code in
   `apps/application/weather_summaries/aggregation.py`.
4. The app's own code builds the 8 day summaries and the estimate for every
   forest square. It uses `_make_summary`, `_forecast_inputs` and
   `calculate_forecast` with the current method, and the same forest, terrain
   and host tree inputs as the published run. Nothing is written to the
   database.

Before any comparison, the script ran the same steps on the stored weather.
It reproduced all 71,031 published forest squares exactly, on all 8 days. So
every difference below comes from the weather alone.

## AC1: estimate differences per day

Files minus published, in percentage points, for the 71,031 Tuscany forest
squares of 16 October. No square was unavailable on either side.

| Days ahead | Date | Typical | 90th percentile | Largest | Mean, files minus published | Squares with 5 points or more |
|---|---|---|---|---|---|---|
| 0 | 16 Oct | 0 | 1 | 1 | -0.2 | 0% |
| 1 | 17 Oct | 0 | 1 | 5 | -0.2 | 0.02% |
| 2 | 18 Oct | 0 | 1 | 8 | 0.0 | 0.4% |
| 3 | 19 Oct | 7 | 16 | 21 | +8.0 | 67% |
| 4 | 20 Oct | 12 | 22 | 29 | +12.3 | 86% |
| 5 | 21 Oct | 8 | 14 | 21 | +7.8 | 77% |
| 6 | 22 Oct | 7 | 13 | 21 | +6.8 | 74% |
| 7 | 23 Oct | 7 | 13 | 25 | +6.4 | 67% |

The typical difference is the median of the absolute differences. Every row
is in `reports/bulk_weather_estimates_days.csv`.

### The stop rule

The issue compares the first date with the change between two consecutive
published nights. The database holds two published nights, 3 nights apart.
A one-off read-only query compared their estimates for the same target dates:

| Target date | Days ahead, 13 Oct run | Days ahead, 16 Oct run | Typical | 90th percentile | Largest | Squares with 5 points or more |
|---|---|---|---|---|---|---|
| 16 Oct | 3 | 0 | 0 | 1 | 9 | 0.9% |
| 17 Oct | 4 | 1 | 0 | 1 | 8 | 0.5% |
| 18 Oct | 5 | 2 | 1 | 2 | 7 | 0.2% |
| 19 Oct | 6 | 3 | 2 | 8 | 28 | 22% |
| 20 Oct | 7 | 4 | 2 | 9 | 33 | 23% |

Three nights should change estimates more than one night does. Even so, the
files move the estimates for 19 and 20 October about 4 to 6 times more than
three nights of published runs: a typical 7 and 12 points against 2. Days 0
to 2 stay within the yardstick. The stop rule was reached, and the owner was
asked before going on.

## AC2: rain and soil moisture per cell

Files minus stored, for the 333 cells. Every row is in
`reports/bulk_weather_estimates_cells.csv`.

| Value | Typical difference | Range across cells |
|---|---|---|
| Rain, 30 past days | 0 mm | 0 to 0 mm |
| Soil moisture, mean of 30 past days | 0 | -0.00001 to +0.00001 m³/m³ |
| Evapotranspiration, 30 past days | 0.5 mm | -0.4 to +1.9 mm |
| Rain, today and 7 days ahead | 15 mm | -221 to +123 mm |
| Soil moisture, mean of the 8 days | 0 | -0.00004 to +0.00003 m³/m³ |
| Mean temperature, the 8 days | 0.7 °C | -2.6 to +0.6 °C |

Here the typical difference is the median of the absolute differences. Soil
moisture matches on every day, ahead as well, because `best_match` also takes
soil from the IFS model.

The rain of the 8 days differs in both directions. The median cell gets 56 mm
from the API and 50 mm from the files. In southern Tuscany the API forecasts
far more rain. For cell 42.75,10.15 it gives 281 mm, with 152 mm on 20 October,
against 60 mm from the files. In the north-west the files forecast more. For
cell 44.35,9.65 they give 210 mm against 87 mm.

14 coastal cells, such as 42.25,11.05, have a soil moisture of 0 in both the
files and the stored values. The API returns the same value, so this
comparison does not cover it. The current method does not use soil moisture.

## AC3: ICON-2I for the first 60 hours

The 60 hours run from midnight of 16 October in Rome to noon on 18 October.
Each hour comes from the newest ICON-2I run published before the API fetch,
from the runs of 14 October 00 UTC to 16 October 00 UTC. Rain, temperature,
dew point, radiation and wind come from ICON-2I. Soil stays from `ecmwf_ifs`.
The grid point choice and the height correction copy Open-Meteo's code for
regular grids. On these grids a grid point within 100 m of the place height
keeps its own height, so 307 of 333 cells get a correction. ICON-2I stores
relative humidity and wind speed instead of dew point and wind components.
Dew point comes from temperature and humidity with Open-Meteo's formula.

| Days ahead | Typical | Largest | Squares with 5 points or more |
|---|---|---|---|
| 0 | 0 | 1 | 0% |
| 1 | 0 | 2 | 0% |
| 2 | 0 | 9 | 0.01% |
| 3 to 7 | 6 to 12 | 21 to 29 | 66 to 87% |

ICON-2I cuts the largest difference on day 1 from 5 to 2 points. It changes
nothing that matters. Days 0 to 2 already agree, and days 3 to 7 lie outside
its 60 hours. The 8-day mean temperature moves closer to the API, a typical
0.5 °C instead of 0.7 °C. The 8-day rain does not, at 15 mm either way. A
model that reaches 60 hours cannot fix a gap that opens after 60 hours.

## AC4: recommendation

Use the files for past days only.

- **Every day: no.** From day 3 on, the files change the estimates of 67 to
  86 percent of Tuscany forest squares by 5 points or more. The typical
  change is 7 to 12 points. This is a change of forecast, not an error in
  reading the files. The test does not show which forecast is better.
- **Past days only: yes.** Rain and soil moisture of the 30 past days match
  in every cell, and evapotranspiration is within 2 mm over 30 days. The app
  could take yesterday from the files and ask the API only for the 8 days
  ahead. That halves a normal night, from 666 to 333 counted calls for
  Tuscany and from 7,452 to 3,726 for all of Italy. It also removes the first
  load of 30 days, which would cost about 14,900 counted calls for all of
  Italy.
- **Not at all: no.** The past days match too well to keep paying API calls
  for them.

Two ways remain to replace the API for the days ahead as well. Neither is part
of this issue:

- Read the ICON forecasts from the bucket too, in `data_run/dwd_icon_d2/`,
  `data_run/dwd_icon_eu/` and `data_run/dwd_icon/`. Then join them with the
  rules of `best_match` that the issue 124 report describes.
- Accept the ECMWF forecast, if it proves as good as the API's mix. A
  follow-up issue, #145, checks both forecasts of this storm against the
  weather that falls.

The owner chose the second way after reading these numbers. D23 records it.

## AC5: the database is unchanged

The script opened the database read-only and checked that the session was
still read-only at the start and at the end. Before and after:

| What | Before | After |
|---|---|---|
| Tuscany published run | `0e1bb4cf` | `0e1bb4cf` |
| Tuscany previous run | `712b336a` | `712b336a` |
| Forecast runs | 2 | 2 |
| Forecast run cells | 666 | 666 |
| Estimate updates | 1,361 | 1,361 |
| Estimate rows | 320,636 | 320,636 |
| Daily weather rows | 17,218 | 17,218 |
| Weather snapshots | 695 | 695 |
| Snapshot days | 26,383 | 26,383 |
| Weather summaries | 5,560 | 5,560 |

The counts for the compared run alone also match: 333 cells, 71,031 estimate
rows and 12,654 daily weather rows. The script made no API call. It read
32 MB in 1,157 requests from the bucket.

## Other findings

- **The bucket keeps past forecasts.** `data_run/ecmwf_ifs/` holds every run
  since 13 July 2026, four a day. `data_run/italia_meteo_arpae_icon_2i/`
  holds two a day. A forecast that a past night used can be rebuilt later.
- **Past runs can be rebuilt to the hour.** After 90 hours the run files store
  values every 3 hours, and later every 6 hours. The script fills the hours
  between with Open-Meteo's own rules. For the 00 UTC run of 16 October it
  matched the saved hourly files within the files' storage step: 0.025 °C for
  temperature, 0.05 mm for rain and 4.2 W/m² for radiation. Source:
  `reports/bulk_weather_estimates_interpolation.csv`.

## Limits of this result

- One date, in a week with a large storm forecast. In a dry week the
  forecasts may agree on every day. In a wet week they will often disagree.
  The yardstick compares runs 3 nights apart, not consecutive nights.
- The stored weather for 16 October was fetched about 4.5 hours after the
  newest ECMWF run appeared. A night run at 00:30 UTC would use an older run
  in both the files and the API.
- The code that rebuilds a past date from several forecast runs was written
  but not run, because 13 October was not compared.
