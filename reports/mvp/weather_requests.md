# Weather requests and allowance

## National accounting

The completed `italy-forest-copernicus-2018-v1` build contains 717,104 forest
squares. Their centres map to 3,726 distinct weather cells. Each cell spans
0.1 degrees and uses its centre as the requested location. Only cells with at
least one eligible forest square can receive weather.

This command reads the database and makes no weather request:

```sh
uv run python apps/application/manage.py weather_request_budget \
  --forest-build-version italy-forest-copernicus-2018-v1
```

| Region | Distinct forest weather cells |
| --- | ---: |
| Piemonte | 340 |
| Valle d'Aosta | 45 |
| Lombardia | 329 |
| Trentino-Alto Adige | 191 |
| Veneto | 262 |
| Friuli-Venezia Giulia | 125 |
| Liguria | 105 |
| Emilia-Romagna | 313 |
| Toscana | 333 |
| Umbria | 123 |
| Marche | 135 |
| Lazio | 240 |
| Abruzzo | 149 |
| Molise | 73 |
| Campania | 191 |
| Puglia | 260 |
| Basilicata | 132 |
| Calabria | 200 |
| Sicilia | 328 |
| Sardegna | 321 |

Regional counts include 469 repeated memberships across borders. They cannot
be added to obtain the national distinct count.

## Request coverage and identity

The Forecast API request uses `best_match` and five hourly variables:

- `precipitation`
- `temperature_2m`
- `soil_moisture_0_to_7cm`
- `soil_temperature_0_to_7cm`
- `et0_fao_evapotranspiration`

A first request covers 21 previous Italian dates, today and seven future
dates. A normal daily request refreshes three recent dates, today and seven
future dates. A previous snapshot that is more than 21 days out of date can
also need missing historical dates. The planner sends those dates in
contiguous parts of at most 13 local dates, followed by the normal daily
request. It keeps each refresh part at one conservative reserved call per
cell, including the Italian clock change. The single-request convenience
function rejects a multipart refresh instead of creating an overlong request.

Requests use UTC Unix timestamps. Their ISO hour bounds cover the first
Italian midnight through the closing midnight after the last requested date.
This includes the closing precipitation interval and handles Italian clock
changes when daily summaries are formed. The provider documents hour bounds
as full date and time strings. [Forecast API documentation](https://open-meteo.com/en/docs)

The request identity includes the endpoint, ordered centres, variables,
model, local dates, exact UTC bounds, timezone, time format, provider options
and forest build version. Different requests cannot share a completed-request
record merely because their dates or first coordinate match.

Open-Meteo adjusts temperature for the requested location's elevation. The
response records that elevation and the returned weather-grid coordinate,
which can differ from the requested centre. The calculation later applies
only the difference between that reference elevation and the 500 m square's
elevation. [Forecast API response fields](https://open-meteo.com/en/docs)

## Counted calls

The allowance assessment in [P6](../p6_cost_licence_portability.md) remains
the basis for the free service limits. Each network attempt reserves its
counted weight before sending, including retries, refusals and interrupted
attempts. Reusing stored weather reserves nothing. A 429 response keeps the
request pending, saves its full message and records when it can be retried.

At most 100 places share one HTTP request, so all national cells require 38
requests. A request still counts every place. Nominal weighting is the larger
of one or variables divided by ten, multiplied by the larger of one or dates
divided by fourteen, multiplied by places.

Reservations count every requested timestamp, including closing midnight,
then round up to whole provider-day equivalents. A first request therefore
reserves 30 divided by 14 calls per place. The provider does not return a
billed weight, so this report keeps nominal and reserved amounts separate.

| Scenario for all 3,726 cells | Nominal calls | Reserved calls |
| --- | ---: | ---: |
| First request, 29 Italian dates | 7,718.142889 | 7,984.285741 |
| Normal daily request, 11 Italian dates | 3,726 | 3,726 |
| Stale snapshot, 18 missing historical dates plus one daily request | 11,178 | 11,178 |
| 31 normal daily requests | 115,506 | 115,506 |
| First request plus 30 daily requests | 119,498.142889 | 119,764.285741 |
| 31 daily requests with one retry each | 231,012 | 231,012 |
| First month with one retry each | 238,996.285778 | 239,528.571482 |

The implementation caps rolling usage at 540 calls per minute, 4,500 per
hour, 9,000 per day and 270,000 per 31 days. These values preserve a margin
below the free allowance. All cells fit within the daily limit for one first
request or one daily request. A first national request needs more than one
hour because its 7,984.285741 reserved calls exceed the 4,500 hourly cap.

One retry for every first request would reserve 15,968.571482 calls. It
exceeds the application's daily cap by 6,968.571482 and the provider's
10,000-call daily allowance by 5,968.571482. The limiter defers those attempts.
Neither monthly scenario in the table exceeds the application's monthly cap.
Visitors cannot override these limits.

The stale-snapshot row contains two historical parts and one normal daily
part. Its 11,178 reserved calls exceed the 9,000-call daily cap by 2,178, so
the quota service spreads the work across rolling windows. Every retry adds
the reserved weight of the part that it retries. A refusal or worker crash
therefore remains counted even when the request stays pending.

## Live check and local tests

The live check is limited to three eligible locations:

```sh
uv run python apps/application/manage.py check_weather_response \
  --forest-build-version italy-forest-copernicus-2018-v1 \
  --assessment-date 2026-10-12 \
  --limit 3 \
  --cache-dir data/raw/weather_requests
```

The first check exposed invalid numeric hour parameters. The next check
received an HTTP 200 response but exposed a validator that incorrectly
required returned weather-grid coordinates to equal requested coordinates.
Both attempts remain in the durable allowance records.

The corrected request succeeded at 2026-10-12 01:31:47 UTC. It returned 697
hourly timestamps per place, from 2026-09-20 22:00 UTC through 2026-10-19
22:00 UTC. This covers all 29 Italian dates and the closing midnight. The
request reserved 6.428572 counted calls for three places. The two earlier
network attempts and this successful retry reserved 19.285716 calls in total.
The local failed-request status was reopened after fixing the validator;
the original attempt records were preserved.

| Requested centre | Returned weather-grid coordinate | Reference elevation |
| --- | --- | ---: |
| 35.55, 12.55 | 35.541237, 12.556473 | 0 m |
| 35.85, 12.85 | 35.845905, 12.828222 | 0 m |
| 36.65, 14.95 | 36.712204, 14.966927 | 0 m |

The returned units were millimetres for precipitation and ET0, degrees Celsius
for air and soil temperature, and cubic metres per cubic metre for soil
moisture. The provider returned GMT and zero UTC offset. The metadata file is
`data/raw/weather_requests/2a720dedfbf8b6e3c2bca09f60c303ded24540f5998b5ec4a333c26271b99b08.json`.
Its successful attempt ID is `70858afc-e9ef-4d96-8a77-d6e462701be9`.

The checked response metadata is saved separately from the hourly data. It
records the source, request and attempt IDs, retrieval time, units, requested
centres, returned coordinates and elevation for the daily-summary adapter.

```sh
uv run pytest tests/app/test_weather_requests.py tests/test_weather.py
```

The tests use controlled responses and a fake clock for identity, Italian
date coverage, place weighting, retries, refusals, process restarts and each
rolling usage limit. They do not request weather for all Italy.
