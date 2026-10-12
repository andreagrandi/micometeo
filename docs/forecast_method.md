# Experimental porcini forecast method

This document defines `porcini-experimental-v1` in
`src/micometeo/forecast_method.py`. It calculates one whole percentage for one
500 m square and one Italian local date. The percentage is an experimental,
unvalidated estimate. It is not a measured probability and it is not a chance
that a visitor will find a mushroom.

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
| `semantic` | Target temperature records must use the canonical value `temperature_at_reference_altitude`. |

`ForecastInputs` contains `assessment_date`, `target_date`, and these six
numeric inputs: `old_rain`, `recent_rain`, `target_temperature`,
`reference_altitude`, `square_altitude` and `forest_share`.

`calculate_forecast` returns a frozen `ForecastResult` with these fields:

| Field | Meaning |
| --- | --- |
| `whole_percentage` | An integer from 5 through 95, or `None` when no estimate is available. |
| `unavailable_reason` | A stable reason key, or `None` for an estimate. |
| `missing_inputs` | Ordered input keys with missing values. |
| `method_version` | The version string, `porcini-experimental-v1`. |
| `event_key` | The event described above. |
| `experimental_unvalidated` | Always `True` for this method. |
| `ordered_facts` | Frozen facts produced by the same calculation, in a stable order. |

The calculation does no network or database work. Fetching and adapting
weather, terrain and forest records belongs to later application work.

## Required input schema

All input periods are inclusive. A `None` record or a record whose `value` is
`None` is missing. A numeric zero is a valid value.

| Input | Unit | Period | Completed days | Forecast days |
| --- | --- | --- | ---: | ---: |
| `old_rain` | `mm` | Target minus 21 through target minus 8 | 14 | 0 |
| `recent_rain` | `mm` | Target minus 7 through target minus 1 | `7 - days_ahead` | `days_ahead` |
| `target_temperature` | `deg_c` | Target date only | 0 | 1 |
| `reference_altitude` | `m` | Assessment date only | 1 | 0 |
| `square_altitude` | `m` | Assessment date only | 1 | 0 |
| `forest_share` | `fraction` | Assessment date only | 1 | 0 |

`days_ahead` is the number of days from the assessment date to the target date.
It must be from zero through seven. The target temperature remains a one-day
forecast even when the target is the assessment date. This keeps every target
weather input under the same source composition rule.

The old rain period has 14 completed days. The recent rain period can combine
completed weather and saved forecast weather for a future target. For example,
a target seven days after assessment has zero completed and seven forecast
days in its recent rain period. The target date may be a leap day. No calendar
season boundary changes the calculation.

Terrain and forest values use the assessment date as their build date. A
regional tree value is optional and is not an input to this method. A missing
regional value therefore does not disable an otherwise complete square.

The method rejects wrong units, dates in the wrong period, inconsistent day
counts, negative rain, non-finite numbers and forest shares outside zero
through one. It accepts finite low and high altitudes. The method rejects a
target temperature without the canonical reference-altitude semantic or one
marked as already adjusted to square altitude, because it applies the
adjustment once from the Open-Meteo reference altitude.

## Formula

The method uses these provisional engineering parameters:

| Parameter | Value | Source or status |
| --- | ---: | --- |
| Older rain saturation | 60 mm | Provisional mapping of the Piemonte rain description. |
| Recent rain saturation | 30 mm | Provisional recent-rain multiplier. |
| Recent-rain base and weight | 0.90 and 0.10 | Provisional weighting. |
| Temperature optimum | 13 deg C | Approximation from the Bielefeld study, not an Italian calibration. |
| Temperature width | 10 deg C | Provisional saturation width. |
| Temperature base and weight | 0.75 and 0.25 | Provisional weighting. |
| Temperature lapse rate | 0.0065 deg C per metre | Open-Meteo elevation translation assumption. |
| Minimum forest share | 0.10 | Decision D17. |
| Forest base and weight | 0.75 and 0.25 | Provisional weighting. |
| Output bounds | 5 through 95 | Provisional display bounds. |

For each input, `clamp(x, 0, 1)` means the value below zero is set to zero and
the value above one is set to one. Raw invalid inputs are rejected before this
operation. The calculation is:

```text
corrected_temperature = target_temperature
    - 0.0065 * (square_altitude - reference_altitude)
d = clamp(old_rain / 60, 0, 1)
r = clamp(recent_rain / 30, 0, 1)
t = clamp(1 - abs(corrected_temperature - 13) / 10, 0, 1)
f = clamp((forest_share - 0.10) / 0.90, 0, 1)
score = d * (0.90 + 0.10 * r) * (0.75 + 0.25 * t) * (0.75 + 0.25 * f)
whole_percentage = ROUND_HALF_UP(5 + 90 * score)
```

The implementation uses decimal round-half-up after the score is calculated.
It checks that the score is finite and from zero through one, and that the
whole output stays inside the configured bounds. It never silently repairs a
bad method configuration or an output outside those bounds.

All saturation values, weights, the 13 degree optimum, the 10 degree width and
the lapse rate are provisional engineering choices. Their combination maps
published qualitative evidence to a stable display value. It is not measured
calibration, and this ticket adds no automatic learning or field-validation
gate.

Open-Meteo already adjusts its temperature to the weather cell centre altitude,
using the provider's weather-centre elevation. The method applies one
additional translation to the square altitude. It does not apply the 0.0065
rate twice.

## Contributing facts

`ordered_facts` contains known values even when another required input is
missing. Each fact records the original value, unit, source identifier, source
identifiers for derived values, inclusive dates, completed and forecast day
counts, a normalized factor when one exists, an ordered role key and a
translation key. The complete order is:

| Role key | Value and factor |
| --- | --- |
| `older_rain` | Original 14-day rain and `d`. |
| `recent_rain` | Original seven-day rain and `r`. |
| `target_temperature_at_reference` | Original target temperature from the weather provider. |
| `reference_altitude` | Provider elevation used as the correction reference. |
| `square_altitude` | Terrain elevation of the square. |
| `corrected_temperature` | Derived temperature at square altitude and `t`; its source identifiers name all three inputs. |
| `forest_share` | Original forest fraction and `f`. |

Facts for missing values do not appear. Facts already known remain in the
result so an unavailable response can still explain the available evidence.

## Missing results

| Condition | `whole_percentage` | `unavailable_reason` |
| --- | --- | --- |
| Missing old rain | `None` | `older_rain` |
| Missing recent rain | `None` | `recent_rain` |
| Missing target temperature | `None` | `target_temperature` |
| Missing reference altitude | `None` | `reference_altitude` |
| Missing square altitude | `None` | `square_altitude` |
| Missing forest share | `None` | `missing_forest_data` |
| Forest share below 0.10 | `None` | `forest_below_minimum` |

When more than one required value is missing, `missing_inputs` contains all
missing keys in the fixed weather and altitude order, followed by
`forest_share`. The first missing key is the unavailable reason unless the
forest value is missing or below the minimum.

## Worked examples

The first examples use an assessment and target date of 15 June. They use
Open-Meteo reference altitude 500 m, square altitude 1,000 m and a target
temperature of 16.25 deg C. The one adjustment gives 13 deg C at the square.

| Older rain | Recent rain | Forest share | Result |
| ---: | ---: | ---: | ---: |
| 60 mm | 30 mm | 1.00 | 95 |
| 0 mm | 30 mm | 1.00 | 5 |
| 60 mm | 30 mm | 0.10 | 73 |
| Missing | 30 mm | 1.00 | Unavailable, `older_rain` |

The method has no regional tree input, so an ideal weather and forest row still
returns 95 when that optional regional value is absent.

A future example uses assessment date 15 June 2026 and target date 18 June
2026. The older rain period is 28 May through 10 June with 14 completed days.
The recent rain period is 11 through 17 June with four completed and three
forecast days. The target temperature covers 18 June with one forecast day.
For older rain 48 mm, recent rain 15 mm, target temperature 15 deg C, both
altitudes 500 m and forest share 0.75, the result is 65. The result keeps the
periods and the four versus three day composition in its facts.

## Source evidence and limits

The Regione Piemonte material describes porcini appearing 12 to 15 days after
at least 30 mm of rain in the relevant earlier period. See the [official
regional resource](https://www.regione.piemonte.it/web/media/14353/download),
the [timing pages](https://www.regione.piemonte.it/web/sites/default/files/media/documenti/2019-11/funghi_tartufi_risorse_del_bosco_pagg_38-52.pdf)
and the [*B. aereus* pages](https://www.regione.piemonte.it/web/sites/default/files/media/documenti/2019-11/funghi_tartufi_risorse_del_bosco_pagg._53-72.pdf).
This supports the delayed rain input qualitatively. It does not validate a
national probability or a one-degree cooling rule.

The Bielefeld *B. edulis* preprint used one German beech forest from 2015 to
2024 and found a peak near 13 deg C with rain over earlier days. It does not
calibrate an Italian four-species probability. The [preprint](https://www.biorxiv.org/content/10.64898/2025.12.12.693895v2)
also found that the cooling rule did not separate porcini days there.

The Piemonte material places *B. edulis* roughly from 300 m to 2,000 m with
tree-line exceptions. It places *B. aereus* around 200 m to 1,000 m, sometimes
to 1,400 m, with autumn and regional spring differences. These ranges do not
support one national hard altitude exclusion or fixed 15 June and 15 November
steps for all four species. The method therefore keeps altitude as a
temperature correction and forest as a minimum eligibility value only.

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
provider's weather-centre elevation and temperature correction. The application
adapter must preserve that source meaning and pass the reference altitude and
square altitude separately.
