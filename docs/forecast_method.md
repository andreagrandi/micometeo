# Experimental porcini forecast method

This document defines `porcini-experimental-v2` in
`src/micometeo/forecast_method.py`. It calculates one whole percentage for one
500 m square and one Italian local date. The percentage is an experimental,
unvalidated estimate. It is not a measured probability and it is not a chance
that a visitor will find a mushroom.

New estimate updates use v2. The code keeps `porcini-experimental-v1` so that
updates already stored with v1 still recalculate the same facts when an area is
read. The last section of this document describes v1 and why v2 replaced it.

The event is visible fruiting bodies from the four-species porcini group,
*Boletus edulis*, *B. aereus*, *B. reticulatus* and *B. pinophilus*, somewhere
in the selected 500 m square on the Italian local target date. The event key is
`visible_porcini_fruiting_bodies_in_500m_cell_on_italian_date`.

## Public records

`NumericInput` is a frozen record with these fields:

| Field | Meaning |
| --- | --- |
| `value` | A finite number, or `None` when the value is missing. |
| `unit` | Exactly `mm`, `deg_c`, `m` or `fraction`, as required by the input. |
| `source_id` | The stable identifier of the source record or build. |
| `period_start`, `period_end` | Inclusive dates covered by the value. |
| `completed_day_count` | Number of completed days in the period. |
| `forecast_day_count` | Number of forecast days in the period. |
| `quality` | Optional source quality text. |
| `semantic` | Temperature records must use the canonical value `temperature_at_reference_altitude`. |

`DailyTemperatures` is a frozen record with the same period, day count, source,
quality and semantic fields. Instead of one value it holds `daily_means` and
`daily_minimums`, one entry for each day of its period. Both are air
temperatures at the Open-Meteo reference altitude, in `deg_c`.

`ForecastInputs` contains `assessment_date`, `target_date`, the numeric inputs
`old_rain`, `recent_rain`, `target_temperature`, `reference_altitude`,
`square_altitude` and `forest_share`, and the daily record
`period_temperatures`. v2 reads `period_temperatures` and ignores
`target_temperature`. v1 reads `target_temperature` and ignores
`period_temperatures`.

`calculate_forecast` takes the inputs and a method, which defaults to v2. It
returns a frozen `ForecastResult` with these fields:

| Field | Meaning |
| --- | --- |
| `whole_percentage` | An integer from 5 through 95, or `None` when no estimate is available. |
| `unavailable_reason` | A stable reason key, or `None` for an estimate. |
| `missing_inputs` | Ordered input keys with missing values. |
| `method_version` | The version string, such as `porcini-experimental-v2`. |
| `event_key` | The event described above. |
| `experimental_unvalidated` | Always `True` for this method. |
| `ordered_facts` | Frozen facts produced by the same calculation, in a stable order. |

The calculation does no network or database work. The estimate update service
reads the stored weather, terrain and forest records and passes them in.

## Required input schema

All input periods are inclusive. A `None` record or a record whose `value` is
`None` is missing. A daily temperature record is missing when any daily mean or
daily minimum is `None`. A numeric zero is a valid value.

| Input | Unit | Period | Completed days | Forecast days |
| --- | --- | --- | ---: | ---: |
| `old_rain` | `mm` | Target minus 21 through target minus 8 | 14 | 0 |
| `recent_rain` | `mm` | Target minus 7 through target minus 1 | `7 - days_ahead` | `days_ahead` |
| `period_temperatures` | `deg_c` | Target minus 19 through target | `19 - days_ahead` | `days_ahead + 1` |
| `reference_altitude` | `m` | Assessment date only | 1 | 0 |
| `square_altitude` | `m` | Assessment date only | 1 | 0 |
| `forest_share` | `fraction` | Assessment date only | 1 | 0 |

`days_ahead` is the number of days from the assessment date to the target date.
It must be from zero through seven. Days before the assessment date count as
completed. The assessment date and later days count as forecast, so the target
day is always a forecast day. For example, a target three days after
assessment has 16 completed and 4 forecast days in its temperature period.

The temperature period has 20 days. Each weather snapshot stores the 21 days
before the assessment date and the 7 days after it, so the 20 days ending on
any target date are always inside the snapshot.

Terrain and forest values use the assessment date as their build date. A
regional tree value is optional and is not an input to this method.

The method rejects wrong units, dates in the wrong period, inconsistent day
counts, daily lists of the wrong length, negative rain, non-finite numbers and
forest shares outside zero through one. It accepts finite low and high
altitudes. It rejects temperatures without the canonical reference-altitude
semantic, because it applies the altitude adjustment once itself.

## Formula

```text
lapse = 0.0065 * (square_altitude - reference_altitude)
corrected_mean = average(daily_means) - lapse
frost_days = number of days with daily_minimum - lapse below 0

d = clamp(old_rain / 60)
r = clamp(recent_rain / 30)
t = exp(-0.10455 * (corrected_mean - 13.7)^2)
    when corrected_mean is 13.7 or lower
t = exp(-ln(2) * ((corrected_mean - 13.7) / (20 - 13.7))^2)
    when corrected_mean is above 13.7
k = clamp(1 - frost_days / 4)
f = clamp((forest_share - 0.10) / 0.90)

score = d * (0.90 + 0.10 * r) * t * k * (0.75 + 0.25 * f)
whole_percentage = ROUND_HALF_UP(5 + 90 * score)
```

`clamp` sets a value below zero to zero and a value above one to one. Raw
invalid inputs are rejected before this step. The implementation uses decimal
round-half-up after the score is calculated, checks that the score is finite
and from zero through one, and never repairs a bad method configuration.

| Parameter | Value | Source or status |
| --- | ---: | --- |
| Older rain saturation | 60 mm | Project choice that maps the Piemonte rain description. |
| Recent rain saturation | 30 mm | Project choice. |
| Recent rain base and weight | 0.90 and 0.10 | Project choice, unchanged from v1. |
| Temperature period | 20 days ending on the target date | Bielefeld preprint, which used a 20-day mean. |
| Temperature peak | 13.7 deg C | Bielefeld preprint, table S1, all sites, 20-day temperature and 26-day rain windows. |
| Cold side of the curve | 0.10455 | Same table row, the quadratic temperature term of the fitted model. |
| Warm side of the curve | Half at 20 deg C | Project choice. 20 deg C is the highest 20-day mean the Bielefeld study observed. |
| Frost threshold | Daily minimum below 0 deg C at the square | Project choice, same threshold as the stored frost flag. |
| Frost days that bring the score to zero | 4 | Project choice. No source gives a number. |
| Temperature lapse rate | 0.0065 deg C per metre | Open-Meteo elevation adjustment assumption. |
| Minimum forest share | 0.10 | Decision D17. |
| Forest base and weight | 0.75 and 0.25 | Project choice, unchanged from v1. |
| Output bounds | 5 through 95 | Project choice for display. |

Only the temperature peak and the cold side of the curve come from a fitted
model. The project fitted nothing itself. No year or area kept aside for the
final benchmark was used to choose any value.

### Why each rule exists

Cold and heat. The temperature factor multiplies the whole score. v1 let
temperature remove at most a quarter of the score, so a frozen January forest
in the Alps and a 34 deg C August day in Puglia both showed 73 percent with
good rain. Porcini do not fruit in either case. In v2 both give 5 percent.

The Bielefeld study modelled daily porcini counts with a quadratic temperature
term on a log scale. Its predicted production relative to the peak is
`exp(-0.10455 * (T - 13.7)^2)`. v2 uses that curve as it is below the peak. It
gives 0.24 at 10 deg C and less than 0.04 at 8 deg C, which matches the
study's finding that fruiting was largely absent at 20-day means of 5 to 10 deg
C, the most common conditions in its seasons.

Above the peak, the same curve gives 0.016 at 20 deg C. v2 does not use it
there, for two reasons. The study observed 20-day means only up to 20 deg C,
in one German beech forest, for *B. edulis* only, from August to November. The
Piemonte material describes *B. reticulatus* and *B. aereus* as warmth-loving
summer species in Italy. The published curve would set almost every July and
August estimate to the floor. v2 instead halves the factor at 20 deg C and
falls slowly after that: 0.22 at 23 deg C, 0.05 at 27 deg C and almost zero at
34 deg C. The half point at 20 deg C is a project choice, not a measured value.

Several days instead of one. The Bielefeld study compared windows from 2 to 35
days and found the best fit with a 20-day mean temperature. One warm day in a
cold month no longer lifts the score, and one hot day in a mild month no longer
drops it.

Frost. No study the project found gives a number of frost days. The Piemonte
material says the first autumn frosts stop *B. reticulatus*, and that
*B. edulis*, *B. aereus* and *B. pinophilus* can be found until the first
frosts and beyond, into late November when leaf litter covers the ground. The
Bielefeld monitoring stopped each year at the first heavy frost. v2 therefore
lets one frost night lower the score without ending it. Each day in the period
whose minimum is below zero at the square removes a quarter of the score, and
four frost days bring it to the floor. The minimum gets the same altitude
adjustment as the mean, so a square 500 m above the weather cell centre counts
frost 3.25 deg C sooner.

No season rule. v1 removed the 15 June to 15 November season in #47 because one
calendar range does not fit four species from the Alps to Sicily. The Piemonte
material describes spring fruiting for some species, and *B. aereus* in
southern oak and cork oak woods fruits into December. With the temperature and
frost rules, a winter in the Alps or a lowland summer heat already gives 5
percent. A fixed season would only remove the mild-winter and early-summer
cases that the sources describe. The project found no source that gives a day
length limit for these species, so v2 has none.

Recent rain. The rain of the last 7 days still changes the score by at most 10
percent. The Piemonte timing and the Bielefeld counts both point to rain 8 to
30 days before fruiting, which the older rain input covers. No source in the
project supports a stronger effect for the last week.

## Contributing facts

`ordered_facts` contains known values even when another required input is
missing. Each fact records the original value, unit, source identifier, source
identifiers for derived values, inclusive dates, completed and forecast day
counts, a normalized factor when one exists, a role key and a translation key.
The v2 order is:

| Role key | Value and factor |
| --- | --- |
| `older_rain` | Original 14-day rain and `d`. |
| `recent_rain` | Original seven-day rain and `r`. |
| `mean_temperature_at_reference` | 20-day mean temperature from the weather provider, with the period's completed and forecast day counts. |
| `reference_altitude` | Provider elevation used as the adjustment reference. |
| `square_altitude` | Terrain elevation of the square. |
| `corrected_mean_temperature` | 20-day mean at the square altitude and `t`. |
| `frost_days` | Number of frost days at the square, unit `days`, and `k`. |
| `forest_share` | Original forest fraction and `f`. |

The two derived facts name the temperature, reference altitude and square
altitude sources. Facts for missing values do not appear.

## Missing results

| Condition | `whole_percentage` | `unavailable_reason` |
| --- | --- | --- |
| Missing old rain | `None` | `older_rain` |
| Missing recent rain | `None` | `recent_rain` |
| Missing temperature on any day of the period | `None` | `period_temperature` |
| Missing reference altitude | `None` | `reference_altitude` |
| Missing square altitude | `None` | `square_altitude` |
| Missing forest share | `None` | `missing_forest_data` |
| Forest share below 0.10 | `None` | `forest_below_minimum` |

When more than one required value is missing, `missing_inputs` lists all
missing keys in the order of this table, with `forest_share` last. The first
missing key is the unavailable reason unless the forest value is missing or
below the minimum.

## Worked examples

The tests in `tests/app/test_forecast_method.py` check every example below.

The first examples use an assessment and target date of 15 June 2026, reference
altitude 500 m and square altitude 1,000 m. Every daily mean is 16.95 deg C and
every daily minimum is 8 deg C. The adjustment gives a 13.7 deg C mean at the
square and no frost days.

| Older rain | Recent rain | Forest share | Result |
| ---: | ---: | ---: | ---: |
| 60 mm | 30 mm | 1.00 | 95 |
| 0 mm | 30 mm | 1.00 | 5 |
| 60 mm | 30 mm | 0.10 | 73 |
| Missing | 30 mm | 1.00 | Unavailable, `older_rain` |
| 60 mm | 30 mm | 1.00, one daily mean missing | Unavailable, `period_temperature` |

With the ideal row and one daily minimum of 2 deg C at the reference altitude,
that night is -1.25 deg C at the square. The result is 73 and the `frost_days`
fact has value 1 and factor 0.75.

Cold, heat and points on the temperature curve, all with 60 mm older rain, 30
mm recent rain, full forest and no frost unless stated:

| Case | Mean at the square | Factor `t` | Result |
| --- | ---: | ---: | ---: |
| Alps, 20 January 2026, square and reference at 1,500 m, minimums -10 deg C | -5 deg C | 0.00 | 5 |
| Puglia, 5 August 2026, square and reference at 100 m | 34 deg C | 0.00 | 5 |
| Cold, below the observed fruiting range | 5 deg C | 0.00 | 5 |
| Cold side | 10 deg C | 0.24 | 27 |
| Peak | 13.7 deg C | 1.00 | 95 |
| Warm half point | 20 deg C | 0.50 | 50 |

A future example uses assessment date 15 June 2026 and target date 18 June
2026. The older rain period is 28 May through 10 June with 14 completed days.
The recent rain period is 11 through 17 June with four completed and three
forecast days. The temperature period is 30 May through 18 June with 16
completed and 4 forecast days. For older rain 48 mm, recent rain 15 mm, every
daily mean 15 deg C, minimums above zero, both altitudes 500 m and forest share
0.75, the result is 67.

## Version 1

`porcini-experimental-v1` used the target day's mean temperature only, with
the factor `0.75 + 0.25 * clamp(1 - abs(corrected - 13) / 10)`, and had no
frost rule. Its other inputs and parameters match v2. The code keeps it
unchanged and the estimate service uses it to recalculate facts for updates
stored with that version. #66 replaced it because temperature could lower the
score by at most a quarter.

## Source evidence and limits

The Regione Piemonte material describes porcini appearing 12 to 15 days after
at least 30 mm of rain in the relevant earlier period. See the [official
regional resource](https://www.regione.piemonte.it/web/media/14353/download),
the [timing pages](https://www.regione.piemonte.it/web/sites/default/files/media/documenti/2019-11/funghi_tartufi_risorse_del_bosco_pagg_38-52.pdf)
and the [*B. aereus* pages](https://www.regione.piemonte.it/web/sites/default/files/media/documenti/2019-11/funghi_tartufi_risorse_del_bosco_pagg._53-72.pdf).
This supports the delayed rain input. It does not give a national percentage
or a one-degree cooling rule.

The Bielefeld *B. edulis* preprint used one German beech forest from 2015 to
2024, visited 2 to 4 times a week from early August until the first heavy
frost. Fruiting was concentrated at a 20-day mean temperature of 10 to 15 deg
C, with a fitted peak of 13.7 deg C for all sites, after rain over the previous
26 days. The 20-day means of its seasons ranged from 5 to 20 deg C. It does not
calibrate an Italian four-species percentage. The [preprint](https://www.biorxiv.org/content/10.64898/2025.12.12.693895v2)
also found that the cooling rule did not separate porcini days there.

The Piemonte material places *B. edulis* roughly from 300 m to 2,000 m with
tree-line exceptions. It places *B. aereus* around 200 m to 1,000 m, sometimes
to 1,400 m, with autumn and regional spring differences. These ranges do not
support one national altitude exclusion. The method keeps altitude as a
temperature adjustment and forest as a minimum eligibility value only.

The Swiss study reports a shift in autumn fungal timing after 1991. It does not
measure this four-species Italian event. See [Global Change Biology,
10.1111/gcb.12263](https://pubmed.ncbi.nlm.nih.gov/23686649/).

The method follows local decisions D17 and D18 and the limits in [P2](../reports/p2_habitat.md),
[P3](../reports/p3_weather.md) and [P4](../reports/p4_benchmark.md). P4's
rain share is evidence for a useful input, not a 95 percent chance. P4's
failed place learner and P5's synthetic map numbers do not enter this method.
The formula does not use soil, slope, aspect, tree species, a cooling rule, a
season rule or visitor finding records as absence evidence.

The [Open-Meteo documentation](https://open-meteo.com/en/docs) describes the
provider's weather-centre elevation and temperature adjustment. The estimate
service passes the reference altitude and square altitude separately so the
method adjusts once.
