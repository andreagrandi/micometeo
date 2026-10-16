# Calculating evapotranspiration from file weather

Issue #126, part of epic #123.

## Question

Does our own calculation of evapotranspiration, the water that leaves soil and
plants, give the same daily values as the API's `et0_fao_evapotranspiration`?

## Answer

Yes, within 0.08 mm a day. For the 20 Tuscany cells from issue 125, the
typical daily gap is 0.014 mm and the largest is 0.077 mm. No cell's 30-day
total moves by more than 1 mm. The largest 30-day gap is 0.56 mm on a total of
87 mm.

Our value is a little higher than the API's in every cell. Over 30 days the
gap runs from 0.39 to 0.56 mm, about 0.6 percent. Most of it falls in the hours
around sunrise and sunset. The cause is not found. It is small enough for the
next issue to use our values, and the stop rule was not reached.

Run: `reports/runs/bulk_weather_evapotranspiration/20261016T104217Z-01e0b9.json`.
Script: `experiments/bulk_weather_evapotranspiration/run.py`. Function:
`src/sporameteo/weather/evapotranspiration.py`.

## The function

`hourly_reference_evapotranspiration` copies Open-Meteo's hourly code line by
line, as the issue 124 report describes it. That code uses the FAO-56 formula,
the standard method of the UN Food and Agriculture Organization, for one hour.
It takes temperature, dew point, solar radiation, wind at 10 m and the place
height. It returns mm for that hour.

`top_of_atmosphere_radiation` gives the sun's power above the air, averaged
over the hour that ends at the given time, at the grid point. It copies
Open-Meteo's `calculateRadiationBackwardsAveraged` with one change. Open-Meteo
reads the sun's height in the sky over the year and its timing from a table
built with NREL's solar position method. Our function uses NOAA's shorter
formulas for the same two values.

The function differs from FAO-56 in the same two ways as Open-Meteo:

- At night FAO-56 carries the cloud ratio over from the hours before sunset.
  Open-Meteo guesses it from humidity as `0.8 - 0.4 * relative humidity`.
- The sun position comes from NOAA's formulas, not from FAO-56's simpler ones.

## AC1: tests against the FAO-56 worked examples

`tests/test_evapotranspiration.py` has 7 tests:

| FAO-56 example | Checked value | FAO-56 | Ours |
|---|---|---|---|
| Example 2, 1,800 m | air pressure | 81.8 kPa | 81.8 kPa |
| Example 2, 1,800 m | psychrometric constant | 0.054 kPa/°C | 0.054 kPa/°C |
| Example 14 | wind 3.2 m/s at 10 m, at 2 m | 2.4 m/s | 2.39 m/s |
| Example 19, 14 to 15 h | evapotranspiration | 0.63 mm | 0.63 mm |
| Example 19, 02 to 03 h | evapotranspiration | 0.0 mm | 0.03 mm |
| Example 19, 14 to 15 h | sun power above the air | 984 W/m² | 997 W/m² |

Example 19 is one hour at N'Diaye in Senegal on 1 October. The afternoon
test passes FAO's own sun power, so it checks the formula alone, and it
matches within 0.01 mm.

Two values differ from FAO, and the tests allow for both:

- The night hour gives 0.03 mm instead of 0.0 mm. FAO assumes a cloud ratio
  of 0.8, while Open-Meteo's humidity guess gives 0.48. With FAO's own numbers
  the result is about 0.02 mm, which FAO prints as 0.0. The test checks that
  the value is between 0 and 0.05 mm.
- Our sun power is 1.3 percent above FAO's. FAO's short formula puts the sun
  4.3 degrees south of the equator on 1 October. The real value is about
  2.9 degrees, which NOAA's formula gives. The test allows 2 percent.

The other two tests check that the sun power is 0 for an hour of full night,
and that a negative result becomes 0.

## AC2: daily gap from the API, per cell

The script used the file weather saved by issue 125, run
`20261016T095133Z-7934cd`. Temperature and dew point already carry the API's
height correction. Each cell uses the place height that the API returned and
the grid point's latitude and longitude for the sun. Hours are summed into days
from midnight to midnight in Rome time, as `src/sporameteo/weather/features.py`
does. The API values are its hourly `et0_fao_evapotranspiration`, summed the
same way. No API call was made.

Past days are 16 September to 15 October 2026, from the archive API. Days
ahead are 16 to 23 October, from the forecast API.

| Days | Cell days | Typical daily gap | Largest daily gap |
|---|---|---|---|
| Past 30 days and 8 days ahead | 760 | 0.014 mm | 0.077 mm |

Per cell, past days, in mm:

| Cell | Place height, m | Typical daily gap | Largest daily gap | Ours, 30 days | API, 30 days | Gap, 30 days |
|---|---|---|---|---|---|---|
| 42.45,11.15 | 0 | 0.014 | 0.056 | 106.67 | 106.19 | 0.48 |
| 42.95,10.95 | 162 | 0.019 | 0.043 | 94.56 | 94.02 | 0.54 |
| 43.15,10.95 | 749 | 0.017 | 0.077 | 87.33 | 86.77 | 0.56 |
| 43.55,10.25 | 0 | 0.018 | 0.067 | 102.00 | 101.50 | 0.50 |
| 43.55,10.75 | 82 | 0.012 | 0.038 | 88.85 | 88.45 | 0.40 |
| 43.55,10.95 | 180 | 0.015 | 0.044 | 84.82 | 84.36 | 0.46 |
| 43.65,11.65 | 1,357 | 0.017 | 0.050 | 72.56 | 72.02 | 0.54 |
| 43.65,11.85 | 331 | 0.016 | 0.041 | 83.32 | 82.83 | 0.49 |
| 43.65,12.15 | 1,022 | 0.011 | 0.042 | 76.13 | 75.74 | 0.39 |
| 43.75,11.05 | 170 | 0.017 | 0.070 | 85.90 | 85.38 | 0.52 |
| 43.75,11.75 | 405 | 0.018 | 0.048 | 81.72 | 81.19 | 0.53 |
| 43.75,12.15 | 1,013 | 0.013 | 0.038 | 75.83 | 75.43 | 0.40 |
| 43.85,10.85 | 56 | 0.013 | 0.030 | 85.89 | 85.49 | 0.40 |
| 43.85,11.65 | 870 | 0.012 | 0.040 | 77.45 | 77.03 | 0.42 |
| 44.05,10.25 | 1,154 | 0.014 | 0.035 | 71.78 | 71.34 | 0.44 |
| 44.05,10.35 | 1,109 | 0.012 | 0.042 | 72.06 | 71.63 | 0.43 |
| 44.15,10.35 | 412 | 0.017 | 0.037 | 78.02 | 77.52 | 0.50 |
| 44.15,10.45 | 519 | 0.020 | 0.062 | 77.08 | 76.52 | 0.56 |
| 44.15,11.05 | 412 | 0.016 | 0.052 | 79.89 | 79.41 | 0.48 |
| 44.15,11.45 | 332 | 0.016 | 0.053 | 81.46 | 80.95 | 0.51 |

The typical gap is the median of the absolute daily differences. The 8 days
ahead give smaller gaps, a typical daily gap of 0.003 to 0.020 mm and 8-day
totals from 0.01 to 0.17 mm higher than the API. Every row, with the date of
the largest gap, is in `reports/bulk_weather_evapotranspiration_cells.csv`.

The API rounds each hour to 2 decimals. The script also ran the function on
the API's own rounded inputs. The gaps barely move: the typical daily gap is
0.014 mm either way. Rounding of the inputs is not the cause of the gap.

## AC3: effect on the 30-day total

No cell's 30-day total moves by more than 1 mm. The gaps run from 0.39 to
0.56 mm, with a median of 0.48 mm, on totals of 71 to 106 mm.

## The gap that remains

Ours is higher in all 20 cells. A one-off check grouped the hourly gaps by
hour of the day, in UTC, over all 38 days. The gap is the mean of ours minus
the API's:

| Hours | Mean gap per hour |
|---|---|
| Night, 19 to 05 | 0.0001 to 0.0004 mm |
| Midday, 09 to 15 | 0.0004 to 0.0008 mm |
| Sunrise, 06 | 0.0018 mm |
| Sunset, 17 and 18 | 0.0015 to 0.0019 mm |

The night hours agree, so the API's rounding is not one-sided. The gap is
largest when the sun is low. At these hours the cloud ratio, actual radiation
divided by clear-sky radiation, is most sensitive to the sun's height. The
two most likely causes are the sun position, NOAA formulas against NREL's
table, and Open-Meteo's 32-bit floating point numbers.

Two checks did not find the cause:

- A sun power 2 percent lower would cancel the 30-day gap, but the midday
  hours would then come out lower than the API. A constant offset does not
  explain the pattern.
- Treating the hours with a very low sun as night fits the 06 and 17 h
  hours better, but it doubles the gap at 18 h.

The gap is 0.6 percent of the 30-day total. The next issue compares estimates,
and it can check whether a gap of this size moves any estimate.

## Limits of this result

- 20 Tuscany cells and one month, from late September to mid October. The gap
  near sunrise and sunset may be larger in winter, when more of the day has a
  low sun.
- The API values come from the same files, read the same day. The comparison
  checks the formula, not the weather.
