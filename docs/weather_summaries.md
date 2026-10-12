# Weather summaries

The application stores one immutable `WeatherDaily` row for each provider
attempt, weather cell and Italian date. A row keeps the provider, model,
endpoint, source ID, request ID, attempt ID, retrieval time, requested and
returned coordinates, provider elevation, and any issue or publication time
that the provider supplied.
`publication_time` stays empty when the Forecast API does not provide it. A
live retrieval time describes when the application received the answer. It does
not claim that the answer was available at the start of the Italian day.
The provider's precipitation field is stored as `rain_mm` for the existing
application contract. It is modelled precipitation and can include snow. The
application does not relabel it as a station observation.

The research path keeps its stricter rule. Historical test output can use only
data that existed before midnight Europe/Rome at the start of the assessment
date. A live application update can use the answer received during its actual
run, and records that retrieval time. These rules describe different uses of
weather data and must not be combined.

## Daily values

`WeatherDaily` stores these numeric values:

| Field | Unit | Hours included |
| --- | --- | --- |
| `rain_mm` | mm | `(start midnight, next midnight]`, including the hour ending at closing midnight |
| `mean_temperature_c` | deg C | `[start midnight, next midnight)` |
| `min_temperature_c` | deg C | Minimum of the same temperature hours |
| `et0_mm` | mm | `(start midnight, next midnight]`, when supplied |
| `mean_soil_temperature_c` | deg C | `[start midnight, next midnight)`, when supplied |
| `mean_soil_moisture` | m3/m3 | `[start midnight, next midnight)`, when supplied |

The boundary rules count 23 hours on the spring clock-change day, 24 hours on
an ordinary day, and 25 hours on the autumn clock-change day. The provider
timestamps are ordered UTC Unix seconds. Required precipitation and temperature
hours produce `complete` only when every expected hour is present and non-null.
Missing required hours produce `checked_known_missing`. A missing optional
variable stays null for that variable and does not erase valid rain or
temperature. Zero rain is a valid value.

Each row's metadata records expected and present hours, null hour positions,
units, quality and the reason for any missing variable. The database stores no
hourly JSON. The hourly arrays exist only while a response is validated and
aggregated.

## Fixed assessment example

For an assessment on 11 October 2026, the application may create target dates
11 through 18 October. The visitor rain choices are:

| Choice | Inclusive dates | Composition |
| --- | --- | --- |
| 7 days | 4 through 10 October | 7 completed days |
| 14 days | 27 September through 10 October | 14 completed days |
| 21 days | 20 September through 10 October | 21 completed days |

For target 11 October, the older method window is 20 September through
3 October. For target 18 October, it is 27 September through 10 October. Both
windows contain completed days only. The recent method window for target
18 October is 11 through 17 October, with zero completed and seven forecast
days. The target weather is the separate 18 October row.

The service creates one `WeatherSnapshot` for the assessment and references all
29 daily dates from 21 days before the assessment through seven days after it.
It then creates exactly eight `WeatherSummary` rows, with `days_ahead` from
zero through seven. The snapshot and its links and summaries are written in one
transaction. A required hourly gap makes its daily row
`checked_known_missing`. If all 29 dates have rows, the snapshot is still ready
and the affected summary numbers are null. If a whole date has no row, no
partial snapshot is marked ready.

Later retrievals cannot rewrite a daily row or a ready snapshot. Repeating the
same request with the same content returns the existing row. A conflicting
content response for the same attempt, cell and date is rejected. A new attempt
gets its own immutable row, and a later forecast does not replace values used by
an earlier assessment. When a new assessment reuses an earlier snapshot, it may
carry forward only dates before that snapshot's assessment date. Dates on or
after the source assessment date were forecasts in that snapshot and must be
requested again, even when those dates have become completed days.

Multipart retrievals use two service calls. `store_weather_daily_rows` accepts
one normalized response and its exact start and end dates. It stores only that
response's immutable daily rows and returns those rows. The caller can persist
several responses with separate attempts. `build_weather_snapshot` then accepts
the explicit IDs of the new rows and one exact previous snapshot. It combines
the new rows with only dates before both assessment dates in the previous
snapshot. It rejects rows from another cell or elevation and rejects two new
rows for the same date. It publishes the snapshot only when all 29 dates are
present. It never combines hourly arrays from separate responses under one
attempt.

## Derived fields and method inputs

Visitor rain is never labelled observed when its rows came from a model. Each
summary metadata section records its inclusive dates, units, completed and
forecast counts, daily row IDs, source IDs, retrieval quality and missing
reasons. The method's older rain covers target minus 21 through target minus 8.
Its recent rain covers target minus 7 through target minus 1 and can combine
completed and forecast rows. The target temperature is a separate one-day
value at the provider reference altitude.

Frost is derived only when the target temperature day is complete and its
minimum temperature is below 0 deg C. The contract has no hail variable, so
hail remains unavailable. The app does not invent a drying threshold when ET0
or soil values are absent.

`weather_numeric_inputs` returns the four weather `NumericInput` records used by
the frozen method. A missing value remains a record with `value=None`, source,
unit, inclusive period and completed versus forecast counts. The adapter does
not adjust temperature for square altitude. Each section source identity covers
all source rows used by that section. The full source and attempt ID lists stay
in summary metadata for provenance consumers. That adjustment belongs to the
existing method and is applied once after the terrain adapter supplies its
separate altitude.
