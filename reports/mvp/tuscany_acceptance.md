# Tuscany acceptance

This report closes epic #96. It collects the results of #97, #98 and #99 and
records the serving checks of #100. All figures come from the local database
`sporameteo` on 13 and 14 October 2026. No national job, purchase, deployment
or new provider was part of this work.

## Data versions

| Input | Version |
|---|---|
| ISTAT administrative geometry | `italy-500m-istat-2026-01-01-v1` |
| Copernicus forest | `italy-forest-copernicus-2018-v1` |
| Copernicus terrain | `italy-terrain-glo30-2021-v2` |
| JRC host trees | `d8998582df944b32f134ef85beb51380e255e4702d6714ebb01b5bd3029ddd0a` |
| Formula | `porcini-experimental-v4` |
| Published run | `712b336a-e958-438a-b0b0-5b2ef871023e`, assessment date 13 October 2026 |

The Tuscany-only database `sporameteo_tuscany_56` holds the same sources under
its own build names, recorded in `tuscany_inputs.md`.

## Coverage

- Tuscany has 71,031 forest squares that share 333 weather cells.
- All 333 cells have a ready weather snapshot for 13 October 2026. Each
  covers 38 dates, 13 September to 20 October: 30 completed days, the
  assessment day and 7 days ahead. See `tuscany_weather.md`.
- The published run holds 333 estimate updates and 71,031 result rows with
  eight values each, for 13 to 20 October. See `tuscany_forecast_run.md`.

## Provider calls

- The first full load used 1,092 counted calls in 12 HTTP requests, 12
  percent of the 9,000 calls allowed per day. No request was refused or sent
  twice.
- A normal night is planned at 666 counted calls: yesterday from the
  historical source and 8 forecast days for each of the 333 cells.
- Italy would need 14,904 counted calls for a first load and 7,452 per night.
  These are planning figures only. No national request was made.

## Calculation time

| Step | Time | Peak memory |
|---|---|---|
| Weather window, 12 requests at least 90 seconds apart | about 17 minutes without the interruption in `tuscany_weather.md` | not recorded |
| Estimates for all 71,031 squares | 144 seconds | 142 MB |
| Filling the map cache after publication | 11.6 seconds | 160 MB |

## Stored size

| Part | Size |
|---|---|
| Estimate updates | 8.1 MB |
| Estimate results | 14 MB |
| Map cache table, 604 entries after warming | 53 MB |
| Whole database | 2,389 MB |

## Serving the published run

These times were measured over HTTP on the local Django development server,
one request at a time. The squares view is 40 by 28 km around Florence with
4,605 squares. The overview covers all of Tuscany.

| Request | Empty cache | After warming, new view and date | Same request again | Data sent with gzip |
|---|---|---|---|---|
| Squares | 0.81 s | 0.32 s | 0.11 s | 251 KB, 2.9 MB unpacked |
| Overview | 1.33 s | 0.27 s | 0.09 s | 128 KB, 1.4 MB unpacked |

With an empty cache every answer is built from the database alone. After
warming, a new view or date reads cached 10 km tiles, or the compact overview
data of the run, and runs no query on the forest square or result tables.
Before #100 the same squares view first asked the weather service and could
wait up to three seconds for it.

## Checks against the epic

- AC1: #97, #98 and #99 are closed with their checks. #100 adds
  `tests/app/test_published_forecast_api.py` and
  `tests/e2e/test_published_forecast_map.py`.
- AC2: the API tests replace the weather request, habitat download and
  estimate calculation functions with ones that fail, and the map, overview
  and details still answer with the same run, date, update and percentage. In
  a browser session on 14 October the map, overview, date strip and details
  agreed on every checked square. The session panned, changed dates, opened
  details on a desktop and a phone screen size and searched for Pistoia. The
  database held 77 provider request attempts, 362 weather fetches and 689
  estimate updates before and after the session.
- AC3: a failed newer run leaves the published pointer and its dates
  unchanged, tested in `test_forecast_runs.py` and
  `test_published_forecast_api.py`. The browser keeps the drawn squares
  while a new date, view or run loads and replaces them once. On a 50 ms
  sample during date changes and pans, the square layer was never hidden or
  emptied.
- AC4: `refresh_tuscany_weather`, `run_tuscany_forecast` and
  `warm_published_map_cache` reject any region except 09. Italy-wide figures
  above come from the planner and made no provider request.

## Limits

- The run of 13 October was still the published run on 14 October, because
  no nightly worker ran. The map showed 14 to 20 October with the note
  "Estimates from 13 Oct." and did not move any value to another date.
- The details explanation of one square is rebuilt from stored inputs the
  first time it is opened, then kept in the cache. The percentage itself is
  never recalculated.
- Photon place search at photon.komoot.io remains a remote request, as the
  epic allows.
