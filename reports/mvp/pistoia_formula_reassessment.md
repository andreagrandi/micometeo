# Pistoia formula reassessment

Checked on 12 and 13 October 2026 for [issue #91](https://github.com/andreagrandi/micometeo/issues/91).
Issue #91 now includes the application correction requested by the owner.
Method v4 uses a new weather history identity. Saved v1 to v3 records remain
unchanged. This report does not validate a mushroom probability.

## Finding

The selected 5% result follows the v3 code, but that code contains rules
whose numerical strength is not established by the cited evidence. In
particular, zero rain in the fixed older window cancels every other favorable
input. More recent rain cannot overcome it. Nearby gauges also show much more
recent rain than the app's selected weather cell.

The next method must address the weather discrepancy and the unsupported hard
cutoffs separately. Increasing scores until the map looks plausible would not
resolve either problem.

## Exact saved result

- Square: `500m_E4390500_N2319500`, near Pistoia.
- Assessment and target: 12 October 2026.
- Update: `2b6df2cf-6d2b-4b48-93cc-adbd7455c268`.
- Snapshot: `ca35f4a5-6509-4283-bab0-52a6a0391c18`.
- Method: `porcini-experimental-v3`.
- Weather request: 43.95 N, 10.85 E. Returned position: 43.952393 N, 10.85511 E.

The saved update was rechecked through the area API on 13 October. It still
returns v3 and 5%, with the following source identities:

- Rain: `open-meteo:69e10400c83d7a95377b27959f3b3351a9d33b2fc937be637577e22ce4eb3e03`.
- Temperature: `weather-snapshot-days:ca35f4a5-6509-4283-bab0-52a6a0391c18`.
- Reference altitude: `weather-snapshot:ca35f4a5-6509-4283-bab0-52a6a0391c18`.
- Square altitude: `terrain-cell:80495`.
- Forest fraction: `forest-cell:80071`.
- Host groups: `jrc:d8998582df944b32f134ef85beb51380e255e4702d6714ebb01b5bd3029ddd0a`.

The host source covers 2006 and describes modelled occurrence at 1 km,
not tree cover. The frost count and corrected temperature use the dated
temperature rows and both altitude sources. The assessment date attached to
static inputs identifies their use in the update, not a new survey that day.

| Input | Value | Factor used |
| --- | ---: | ---: |
| Rain, 21 September to 4 October | 0 mm | 0 |
| Rain, 5 to 11 October | 4.1 mm | 0.136667, then 0.913667 after the base and weight |
| Mean air temperature, 23 September to 12 October | 18.66291 C | Reference value |
| Weather reference altitude | 315 m | Reference value |
| Square altitude | 507.4 m | Temperature adjustment of 1.2506 C |
| Corrected mean temperature | 17.41231 C | 0.786096 |
| Frost days in the temperature period | 0 | 1 |
| Forest fraction | 0.624 | 0.582222, then 0.895556 after the base and weight |
| Beech occurrence | 0.210207 | Host input |
| Chestnut occurrence | 0.331793 | Highest host input |
| Oak occurrence | 0.142039 | Host input |
| Pine occurrence | 0.046318 | Host input |
| Spruce and fir occurrence | 0.100691 | Host input |
| Host multiplier | 0.665897 | Applied to the whole score |

The score is zero because its first multiplier is zero. The displayed value
is therefore `5 + 90 * 0`, which is 5%. This is a display floor, not an
observed 5% frequency of porcini fruiting.

The area API returned all these inputs, including complete tree data. Soil
temperature and moisture were present in the weather record, but v3 does not
use them. Slope, aspect and evaporation also do not affect its score.

## Weather checks

A fresh Open-Meteo hourly precipitation request for the selected coordinates
returned zero older rain, 4.1 mm recent rain and no null hourly values. Its
daily endpoint returned the same totals. The historical-weather endpoint
returned 0.5 mm for the older period at a different returned grid position,
43.971878 N, 10.925645 E. The calculation's zero is not a missing input
silently filled with zero by the application.

Across the original Tuscany database, 231 of 333 weather summaries for 12 October have zero
older rain. The maximum older-rain total is 2.4 mm. This explains why a large
part of the map reaches or approaches the floor.

The independent source was the Regione Toscana SIR gauge network. The
[station table](https://www.sir.toscana.it/monitoraggio/stazioni.php?type=pluvio_men)
read during this check reported these provisional seven-day totals:

| Gauge | Code | Seven-day rain |
| --- | --- | ---: |
| Pontelungo valle | TOS01004839 | 27.4 mm |
| Baggio | TOS01001263 | 36.9 mm |
| Sammomme | TOS03001241 | 49.2 mm |
| Pracchia | TOS30150800 | 62.4 mm |

The table gave updates on 12 October at 22:30 standard time, except Pracchia
at 22:15. Its current-day amount is a separate column.

The [Sammomme daily graph data](https://www.sir.toscana.it/monitoraggio/dettaglio.php?id=TOS03001241&type=pluvio_men)
allows comparison over the actual completed date windows. Its cumulative
series stays at 2.8 mm from 20 September through 5 October. It then rises as
follows:

| Date | Daily increase | Cumulative amount |
| --- | ---: | ---: |
| 6 October | 3.8 mm | 6.6 mm |
| 7 October | 8.9 mm | 15.5 mm |
| 8 October | 32.9 mm | 48.4 mm |
| 9 October | 3.4 mm | 51.8 mm |
| 10 October | 0.2 mm | 52.0 mm |
| 11 October | 0 mm increase | 52.0 mm |

Thus this gauge also has no increase during 21 September to 4 October, but
49.2 mm during 5 to 11 October. This supports a recent wet spell after a dry
older window. It does not establish a positive porcini observation in the
selected square. The owner's garden observations do not identify species or
provide a dated survey of that square.

Limitations: these gauges and the selected model cell are different places.
SIR uses standard time and its current readings are not validated. Their
agreement on substantial recent rain warrants a comparison at each station's
verified coordinates, rather than substituting a nearby station into all
500 m squares. The [SIR archive](https://www.sir.toscana.it/consistenza-rete)
explains validation status and source attribution requirements.

## Rule and evidence audit

| Rule | Evidence or authority | Reassessment |
| --- | --- | --- |
| 10% forest eligibility | Owner decision D17 | Retain unless the owner revises the product definition. It does not mean fungi cannot grow outside eligible woods. |
| Older and recent rain windows | Owner decision D18 | Retain as available inputs. The decision does not establish a zero-score veto or the 60 mm divisor. |
| Zero older rain cancels all inputs | Project formula | Replace this hard veto only after testing candidate timing and moisture rules. Rainfall delay evidence does not establish this exact multiplier. |
| Recent rain changes the factor from 0.9 to 1 | Project coefficients | No quantitative calibration supports such a weak response. Reassess with dated rainfall and fruiting observations. |
| Temperature curve below 13.7 C | One German beech-forest preprint | Source-derived relative count response, not an Italian four-species probability. Retain as a candidate for testing, not an established universal curve. |
| Warm response halves at 20 C | Project choice | Needs testing, especially for the warmer-weather porcini species. |
| Four frost nights force 5% | Project choice | The sources do not establish this count, window or equal effect for all four species. Remove the unsupported hard cutoff from a proposed replacement. |
| Forest weight and tree multiplier | Project choices | Test their effect independently. The 2006 tree maps are modelled occurrence, not current stand composition. |
| Missing trees have factor 1; known zeros have factor 0.5 | Explicit fallback policy | Missing evidence can score higher than complete low-host evidence. This needs an explicit treatment of uncertainty. |
| 5 to 95 percentage mapping | Project display choice | It has not been calibrated against event frequency. Keep that distinction in any proposal; do not claim a measured probability. |

The [Bielefeld preprint](https://www.biorxiv.org/content/10.64898/2025.12.12.693895v2.full)
models counts using temperature and precipitation windows. The inspected text
describes a 20-day temperature optimum and a 26-day precipitation window.
That differs from v3's 14-day older-rain window, which excludes the last seven
days. The preprint does not establish the current hard veto or output bounds.
The full HTML was accessible directly even though the web reader failed.

The Piemonte PDF endpoints could not be read in this check. The repository's
summary attributes a 12 to 15 day response after at least 30 mm of rain to
those sheets. That attribution was not independently reverified here and
must not be treated as fresh evidence for the coefficients.

## Executed sensitivity checks

Run `uv run python tools/forecast_checks/audit_rules.py`. All examples use
ideal temperature, full forest and no frost unless the row changes them.
These are controlled inputs, not invented measurements.

| Changed input | V3 output |
| --- | ---: |
| Ideal inputs, missing tree data | 95% |
| Zero older rain and 100 mm recent rain | 5% |
| 0.5 mm older rain and 100 mm recent rain | 6% |
| 30 mm older rain and no recent rain | 46% |
| 30 mm older rain and 100 mm recent rain | 50% |
| Four frost nights in 20 days | 5% |
| 20-day temperature of 10 C | 27% |
| 20-day temperature of 20 C | 50% |
| Forest cover of exactly 10% | 73% |
| Forest cover of 9% | Unavailable |
| All host occurrence values known and zero | 50% |

## What the previous benchmark establishes

The [P4 report](../p4_benchmark.md) reports older rules, not v3. In Bielefeld,
30-day rain alone placed 39% of fruiting days in the top fifth, compared with
32% for those rules. The uncertainty ranges overlap. These results support
checking simple rain measures and do not validate the current coefficients.

A read-only check of the existing Zenodo CSV, using the `All` site and exact
21-to-8-day windows with every source day present, found 1,010 usable days,
141 with fruiting, and only two with exactly zero older rain. Neither of those
two had fruiting. That tiny dry subset cannot establish a general hard veto.
This was not a new v3 benchmark: minimum temperatures and matched Italian
species outcomes were not reconstructed for it.

## Investigation plan recorded before implementation

1. Verify gauge coordinates and compare the same completed days with provider
   grid values at those locations. Retain both sources and their quality flags.
2. Propose rain rules that represent a wet spell and its delay without making
   one disjoint window erase all other evidence. Compare recent and longer
   accumulated rain before choosing weights. Any change to D18 needs a recorded
   product decision.
3. Test temperature, frost and host effects separately on observations with
   known dates and species. Do not tune solely to these Pistoia screenshots.
4. Compare candidates against rain alone and the unchanged current method on
   years kept aside for checking. Report ranking and probability calibration
   separately. German counts alone cannot establish Italian calibration.
5. Version any accepted replacement and preserve the old update explanations.

Software tests do not establish scientific accuracy. The later correction
below fixes the identified weather routing and rain veto under the owner's
instructions. Its new coefficients remain provisional.

## Competitor check on 13 October 2026

Opened the public [Meteo Funghi map](https://meteofunghi.fungocenter.it/embed)
in standalone headed Chrome. Its update label showed 12 October 2026, matching
the date of the Micometeo example. Read the public map's embedded GeoJSON,
not the simulated alert on its landing page.

The comparison location is 43.9839 N, 10.8674 E. The nearest published points
are below. Distances use a local latitude and longitude approximation.

| Latitude | Longitude | Approximate distance | Growth index out of 10 |
| --- | --- | --- | --- |
| 43.893002 | 10.832873 | 10.5 km | 1.0 |
| 44.093002 | 10.832873 | 12.4 km | 1.5 |
| 43.893002 | 11.032873 | 16.7 km | 1.2 |
| 44.093002 | 11.032873 | 18.0 km | 1.5 |

These are nearby grid values, not a forecast calculated at our exact square.
The map's published points here are spaced by 0.2 degrees. Its client assigns
values below 3 to the lowest growth category. The public data inspected did
not include the underlying rain or temperature series.

The [published method](https://meteofunghi.fungocenter.it/how-it-works)
uses seven-day mean temperature and weighted rainfall over 28 days from
OpenWeatherMap. It excludes habitat, altitude and exposure. It does not
publish enough coefficients to reproduce its calculation from this page.
Its low scores therefore do not validate our formula or justify converting
its index to a Micometeo percentage.

The public client also makes low scores nearly invisible. Its circle opacity
is zero at index 0 and 0.02 at index 3. This is a presentation choice, not
evidence of absent forest or absent data. Micometeo should keep those states
distinguishable when revisiting the map.

This check provides no competing high forecast for the Pistoia example.
The independent gauge rainfall discrepancy and the current formula's hard
veto from the older dry window remain the concrete problems to resolve.
Use the competitor's longer rainfall history as a comparison candidate,
not as a source of unreported weights or a target score to imitate.

## Matched-location weather check on 13 October

The [SIR station metadata](https://www.sir.toscana.it/open_layers/ajax_stations.php?id=TOS03001241)
places Sammomme at 44.037 N, 10.920 E, altitude 785 m. Requests at those
coordinates still show a large difference between the two Open-Meteo
endpoints. All totals below cover 5 to 11 October inclusive.

| Requested location | Forecast endpoint | Historical-weather endpoint | SIR gauge |
| --- | ---: | ---: | ---: |
| App weather request, 43.95 N, 10.85 E | 4.1 mm | 53.0 mm | No gauge at that point |
| Sammomme, 44.037 N, 10.920 E | 4.7 mm | 46.3 mm | 49.2 mm |

Three further requests at published SIR station coordinates give the following
totals for the same API dates. The gauge totals are the provisional readings
recorded above, with the standard-time boundary limitation still applying.

| Gauge and requested coordinates | Forecast endpoint | Historical endpoint | Gauge total |
| --- | ---: | ---: | ---: |
| Pontelungo valle, 43.920 N, 10.896 E | 3.6 mm | 67.6 mm | 27.4 mm |
| Baggio, 43.991 N, 10.964 E | 2.1 mm | 53.0 mm | 36.9 mm |
| Pracchia, 44.055 N, 10.907 E | 3.1 mm | 46.3 mm | 62.4 mm |

This broader check matters: the historical endpoint captures substantial rain
but overestimates Pontelungo and Baggio and underestimates Pracchia. Switching
endpoints is not sufficient evidence of reliable local rainfall. The report
does not select only Sammomme's close agreement to claim general accuracy.

The forecast endpoint returned 44.04428 N, 10.895042 E for Sammomme. The
historical endpoint returned 44.04218 N, 10.942249 E. These remain model
cells near the gauge, not measurements at its instrument. The gauge uses
standard time while these daily API requests use Europe/Rome. Boundary-hour
differences remain, but do not explain why one endpoint largely misses the
multi-day wet spell and the other captures it.

The historical endpoint also passed a bounded hourly compatibility check
using all five application variables, GMT and Unix timestamps. For the app
location, from 4 October at 22:00 UTC through 11 October at 22:00 UTC, it
returned exactly 169 hourly timestamps with no missing values. Summing
precipitation after the first timestamp gives 53.0 mm. This follows the
application's preceding-hour rain convention and confirms the daily total.

The [Open-Meteo historical-weather documentation](https://open-meteo.com/en/docs/historical-weather-api)
describes reconstructed past weather and distinguishes its underlying
datasets and delays. The archive endpoint is not a gauge observation and
this check does not establish its superiority across Italy. It supplies
substantially better evidence for this wet spell than the forecast endpoint.
Request selection must retain the dataset, returned coordinates, dates and
retrieval time rather than calling all past values observations.

The captured arrays and request parameters are in
`tools/forecast_checks/pistoia_2026_10_12.json`. They include 30 complete
preceding days at the app location from both endpoints, plus the matched
Sammomme seven-day comparison. They were retrieved after the target date,
so they diagnose this failure but do not establish forecast accuracy as it
would have been known on that morning.

## Implemented candidate and explicit assumptions

`src/micometeo/moisture_method.py` implements the v4 rules.
`tools/forecast_checks/moisture_candidate.py` exposes them to the offline replay.
The application registers `porcini-experimental-v4` as its current method. It requires every
one of the 30 dates preceding the target, rejects duplicate or misordered
dates, and returns unavailable for missing rain, temperature or evaporation.
Zero measured rain remains distinct from missing rain. Forest cover below
10 percent remains ineligible under D17.

The candidate carries a water store through each day. It adds rain, deducts
evaporation and drainage, then combines recent moisture persistence with
temperature. It produces one final experimental score. Internal factors and
uncertainty bounds exist only for diagnosis.

Every coefficient below is a provisional project choice. None is claimed
as a measured Italian porcini threshold.

| Choice | Candidate value and reason |
| --- | --- |
| Water capacity | 80 mm. A bounded store makes older rainfall decay rather than accumulate forever. |
| Daily retained rain cap | 25 mm. Tests reduced benefit from concentrated rain. Daily totals cannot reveal actual storm intensity or infiltration. |
| Daily drainage | Five percent of the previous store. Represents moisture loss beyond evaporation. |
| Evaporation loss | Half of daily reference evapotranspiration. Reference evapotranspiration describes a reference crop, not the forest floor; the multiplier needs checking. |
| Starting water | 40 mm, with separate runs starting at 0 and 80 mm. Their resulting score range exposes the unknown initial moisture. |
| Moisture response | Store divided by 40 mm, capped at 1. Use the smaller of today's response and the preceding seven-day mean response. This allows gradual preparation and persistence without fixing an emergence date. |
| Temperature response | Daily factors at 0, 5, 8, 12, 18, 22, 25 and 30 C are 0, 0.1, 0.4, 1, 1, 0.7, 0.3 and 0. Interpolate and average the final seven days. These broad bands follow the supplied document; the factors and seven-day aggregation are choices. |
| Altitude | The replay retains the existing 0.0065 C per metre adjustment before passing temperatures into the candidate. |
| Final mapping | Retain 5 to 95 to isolate rule changes from the public scale. This remains an uncalibrated score. |

The candidate removes the older-rain veto and the count of four frost nights
that cancels the whole result. Cold weather instead reduces the daily
temperature response. It uses forest cover as an eligibility check, without
the previous arbitrary forest or host-occurrence multipliers. Tree occurrence
maps do not measure stand composition or prove mycelium presence. Missing
tree information therefore cannot earn a numerical bonus over known values.

Measured soil moisture, soil texture, host composition, slope, exposure and
species-specific seasonality are not encoded in this candidate. Their absence
is explicit. In particular, volumetric soil moisture cannot be converted into
available water without soil properties or an appropriate local reference.
Reference evapotranspiration supplies a drying input but does not establish
the real drying rate beneath these trees. This is a testable partial equation,
not a claim to encode every ecological statement in the owner's document.

## Candidate replay results

Run `uv run python -m tools.forecast_checks.compare_pistoia`. It reads the
captured data without a network connection or database access.

| Input source | Rain in 7 / 14 / 21 / 30 days | Candidate score | Score range from initial moisture |
| --- | --- | ---: | --- |
| Forecast endpoint | 4.1 / 4.1 / 4.1 / 9.3 mm | 5 | 5 to 5 |
| Historical endpoint | 53.0 / 53.3 / 53.5 / 63.1 mm | 50 | 50 to 56 |

The same candidate stays at 5 with the app's low-rain weather source. With
the historical endpoint it retains about 30.0 mm of water and responds to the
wet spell. The resulting 50 is not a verified probability or a replacement
for the saved 5%. No coefficient was changed after this replay to obtain it.
This comparison shows why weather selection and the rain rule both need work.

Run `uv run python -m tools.forecast_checks.check_bielefeld` to reproduce the
older-window evidence counts from the existing local source ZIP. It gives
1,010 complete windows, 141 fruiting days, two zero-rain older windows and no
fruiting on those two dates. This checks coverage, not candidate accuracy.
The source table does not supply the candidate's daily evaporation input.
No substitute evaporation values were invented to claim a candidate benchmark.

## Application correction

1. Completed days now use the historical endpoint. Today and the following
   seven days use the forecast endpoint. The first load splits 30 past days
   into three requests and adds one forecast request. Later loads reuse
   completed historical days and replace yesterday's forecast with history.
   Missing weather stays unavailable, with no silent dry-weather substitution.
2. Weather fetches and snapshots now include `pipeline_version` in their
   identity. Version 1 retains the old history. Version 2 stores 30 past days
   and eight forecast days. Migrations preserve existing rows. The current
   formula refuses a version 1 snapshot.
3. V4 removes the older-rain veto and uses the moisture equation documented
   above. V1, v2 and v3 remain available to explain their saved results.
4. The public map still shows one score. The method remains experimental.
   Forest eligibility and altitude correction remain active. Host occurrence
   values remain available as source facts but do not multiply the score.
5. The local Tuscany database has received new weather and completed estimates
   for all 333 weather cells and 71,031 eligible forest squares. Today's scores
   range from 18 to 87, with no unavailable forest-square results.
   No national database was changed. On 13 October the original square
   has a v4 score of 60 from update
   `58ed299f-cebf-4928-bb33-1e2f03a44a88`, using snapshot
   `ed87152b-a3f4-415b-b04e-14f54dc8415a`. This is a new assessment date,
   distinct from the 12 October offline replay score of 50.

The moisture coefficients still require comparison with dated mushroom
observations. Their activation fixes the identified software behavior and
weather routing; it does not establish biological accuracy.

## Local verification

- `uv run pytest --ignore=tests/e2e -q --tb=short --maxfail=8`: 399 passed initially. Four failed checks passed after updating legacy fixtures, the date-dependent map check and request-count expectations. These 403 checks cover the backend and offline tools.
- `uv run pytest tests/app/test_weather_on_demand.py -q --tb=short --maxfail=3`: 30 passed, including split-request retries and recovery.
- `manage.py makemigrations --check --dry-run`: no missing migrations. Both new migrations were applied only to `micometeo_tuscany_56`.
- `uv run python tools/forecast_checks/audit_rules.py`: reproduced all v3 sensitivity cases above.
- `uv run python -m tools.forecast_checks.compare_pistoia`: reproduced the captured-weather candidate comparison.
- `uv run python -m tools.forecast_checks.check_bielefeld`: reproduced the source-coverage counts above.
- `uv run python -m compileall -q tools/forecast_checks`: passed.
- The saved area API still returns v3 and 5% for the original update.
- Headed Chrome with real Tuscany data showed 60% for the original square on 13 October and 62% on 14 October. Dragging kept the details open. The colored estimate layer rendered. A 390-pixel phone viewport had no page overflow. English retained the selected square and 60% result. No JavaScript errors or failing application API requests occurred in this browser check.

These checks establish reproducibility and intended code behavior. They do
not establish biological accuracy or repair the previously reported WebKit
failures in PR #92. The changes remain uncommitted on
`fix/scoring-reassessment-91`, based on the pushed map checkpoint.
