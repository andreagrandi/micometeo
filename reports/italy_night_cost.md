# Cost of an Italy night on the VPS

Issue #152, part of epic #151.

## Question

Can the VPS run an Italy night inside its limits, or must regions be added one
at a time?

## Answer

Yes, all Italy fits in one night, after three changes made during this issue.
With them every step of the night stays under the 384 MB of the VPS worker,
and the night takes about 15 minutes on the VPS, from 00:30 to about 00:45
UTC. That is well before the first nightly check at 02:30 UTC.

The measurement first found three problems with the code of 17 October:

1. The estimates for all Italy would take about 55 minutes on the VPS.
2. The weather read for all Italy needed 2.5 GB for a normal night and was
   killed under 384 MB after 4.6 seconds.
3. The map cache warm-up built every map tile of Italy ahead of time and
   needed 416 MB.

The changes:

1. The estimates do the weather part of the method once per weather cell
   instead of once per square. They now take about 6 minutes on the VPS, with
   the same results.
2. The weather read loads and stores the cells in blocks of 200. It needs
   202 MB for a night and 302 MB for a first load.
3. The warm-up prepares only the overview of the run. Each map tile is built
   by the first request that needs it. The warm-up needs 232 MB.

Run on 17 October 2026 on a laptop, Apple M2 Pro. Each step ran inside the
app image as a Linux container with 2 CPUs, the same arm64 build the VPS runs.
Script: `experiments/italy_night_cost/`. Measurements:
`reports/runs/italy_night_cost/measurements_sporameteo_estimate_benchmark_20261017.json`.

## What was run

- Database: `sporameteo_estimate_benchmark_20261017`, a copy of the local
  `sporameteo_native` database with its weather, estimate and map cache tables
  emptied. It holds the national builds `italy-500m-istat-2026-01-01-v1`,
  `italy-terrain-glo30-2021-v2` and `italy-forest-copernicus-2018-v1`.
- Weather: `store_file_weather` from the `ecmwf_ifs` files for the 3,726
  Italy weather cells that hold forest. No Open-Meteo API call was made.
- Estimates: the current method, `porcini-experimental-v4`, for the assessment
  date 17 October 2026 and the 8 days of a published run, for all 717,104
  forest squares. Each weather cell is calculated and stored in turn, as
  `run_tuscany_forecast` does.
- Map cache warm-up: the steps of `warm_published_map_cache` for all Italy.
- Memory limit: each step ran without a limit and again with
  `--memory 384m --memory-swap 384m`. That is the worker limit without swap.
  `dokku ps:inspect` shows that the VPS worker has 384 MB of memory and may
  use another 384 MB of swap. The test without swap is the stricter one, and a
  night that needs swap would slow down book corners too.
- Speed of the VPS: the code of `master` ran the Tuscany estimates in 237.0
  seconds on the laptop. The same code ran them in 326.8 seconds on the VPS
  on 17 October. The VPS is therefore 1.38 times slower, and every VPS time
  below is a laptop time multiplied by 1.38.

## Measurements

### Weather read, AC1

| Read | Days | MB read | Requests | Laptop time | Peak memory before | Peak memory after, at 384 MB |
|---|---|---|---|---|---|---|
| First load | 17 September to 24 October | 155.5 | 4,850 | 9.1 min | 1,076 MB | 302 MB |
| Normal night | 17 to 25 October | 110.9 | 3,464 | 5.9 min | 2,495 MB, killed at 384 MB | 202 MB |

The night read was set up by removing the stored forecast days and pretending
the files were one day newer. The read then covers the newest completed day,
today and 7 days ahead, as a real night does.

On the VPS the Tuscany night of 17 October read 31.2 MB with 1,036 requests in
1.6 minutes. Scaled by requests, the Italy night read takes about 5.3 minutes.
Scaled by laptop speed, it takes about 8.1 minutes. The report uses the
larger figure.

Where the memory went, measured on the old code:

| Stage of the night read | Peak before | Peak after |
|---|---|---|
| Plan of the read | 107 MB | 1,874 MB |
| Stored days that can be used again | 1,874 MB | 2,377 MB |
| Reading the files and storing the days | 2,377 MB | 2,381 MB |

`_reusable_rows` in `apps/application/weather_summaries/file_weather.py`
loaded every stored day of every cell as a full Django row, with its metadata,
and the plan and the store step each did it once. It now reads six columns,
one block of 200 cells at a time. The downloaded values stay in compact arrays,
about 30 MB for all Italy, and the hours of a cell become Python values only
when its block is stored. All files are still read before any row is stored,
so a file that fails still stores nothing. A test stores the same read in
blocks of 1 cell and in one block and finds the same rows.

About 170 seconds of the night read on the laptop go to matching each cell to
its grid point and height, before any weather is read. That was not changed
and could be cut in a later issue.

### Estimates, AC2 and AC4

| Run | Squares | Laptop time | VPS time | Peak memory, process and container |
|---|---|---|---|---|
| All Italy, new code, no limit | 717,104 | 4.3 min | 5.9 min | 188 and 441 MB |
| All Italy, new code, 384 MB | 717,104 | 4.2 min | 5.8 min | 194 and 270 MB |
| Tuscany, new code | 71,031 | 24.4 s | 34 s | 190 and 297 MB |
| Tuscany, code of 17 October | 71,031 | 237.0 s | 326.8 s, measured | 184 and 122 MB |
| All Italy, code of 17 October | 717,104 | not run | about 55 min | |

The estimates of all Italy finish inside 384 MB, so the largest region that
fits is all Italy. The container figure without a limit includes the file
cache, which the system gives back under a limit. Memory does not grow with
the number of squares, because each weather cell is calculated and stored on
its own. The largest cell has 396 squares.

The first night for all Italy also samples the JRC host tree maps for the
626,544 squares that have no stored values yet, and stores them. A pass that
sampled about 1,700 weather cells took 6 minutes longer than a normal night on
the laptop. This happens once and adds 274 MB to the database for good.

### The faster estimate calculation

A profile of one cell showed that 72% of the time went to the method and 22%
to building inputs for each square and day. In method v4 the moisture part of
the score depends only on the weather of the cell. Only the temperature part
depends on the square, through its altitude. Forest share only decides
whether a square gets a score, and host trees only add facts that are not
stored.

The new `calculate_v4_scores` in `src/sporameteo/forecast_method.py` does the
weather work once per cell and day and the altitude step per square.
`calculate_estimate_update` uses it for method v4. Details still use the full
`calculate_forecast`. Both versions ran on the same 363 real cells, all of
Tuscany plus 30 at random, 616,344 square-days in all. Every percentage,
every reason for a missing percentage, every host tree value and every input
fingerprint was the same. An earlier check of 633 cells gave the same result.
The calculation alone went from 0.372 to 0.039 seconds per cell. Reading and
storing the data now takes about half of the remaining time.

### Map cache warm-up, AC2

| Warm-up | Laptop time | VPS time | Peak memory |
|---|---|---|---|
| Before, all 3,497 tiles and the overview | 63 s | 87 s | 416 MB, container at the 384 MB limit |
| After, overview only, at 384 MB | 6.2 s | 9 s | 232 MB |

The old warm-up built every 10 km tile of the run ahead of time. To list the
tiles it read the corners of all 1.2 million squares of the build into Python.
The new warm-up builds only the run summary and the overview of all forest
squares, which the zoomed-out map needs. The overview is filled straight into
numpy arrays and stored compressed.

A tile is now built by the first request that needs it:

| Request, after the warm-up | First call | Next calls |
|---|---|---|
| Squares of a phone view in Tuscany, 15 by 30 km | 0.20 to 0.25 s | 0.004 s |
| Overview of all Italy | 0.11 s | 0.0006 s |
| 8 tiles in Piemonte, tile work only | 0.14 to 0.16 s | 0.013 s |

The first visitor of an area each night waits about 0.2 seconds more. The
squares API still answers only for Tuscany, so Piemonte was measured on the
tile functions directly. Serving other regions is issue #155.

### Database growth for one Italy night, AC3

| Part | Growth | Kept |
|---|---|---|
| Estimate results, one run | 102 MB, 717,104 rows | two assessment dates, so about 205 MB |
| Weather rows, first load of 38 days | 344 MB, 141,588 daily rows | about 30 days back, so about 345 MB stays |
| Weather rows, one night | about 80 MB of new rows, 33,534 daily rows | removed by the nightly cleanup after 30 days |
| Map cache, overview of one run | under 16 MB | until the cache reaches 50,000 entries |
| Map cache, tiles | built on demand, at most 136 MB for square tiles and 16 MB per run | until the cache reaches 50,000 entries |
| Host tree values | 274 MB, once | for good |

The night weather figure is the first load scaled by rows, because the
measured growth included dead rows from an earlier try. The VPS has 25 GB of
free disk, so storage is not a limit.

### Run time on the VPS, AC5

| Step | VPS time | Peak memory |
|---|---|---|
| Weather read, normal night | 8.1 min | 202 MB |
| Estimates | 5.8 min | 194 MB |
| Map cache warm-up | 9 s | 232 MB |
| Total | about 14 min | |

The night starts at 00:30 UTC, so it ends at about 00:45 UTC, well before the
first nightly check at 02:30 UTC. It no longer overlaps the weather cleanup
at 01:30 UTC. The first night for all Italy takes longer, about 13 minutes
for the 38-day weather read and a few minutes for the host tree values, and
still ends before 01:15 UTC.

The worker runs one task at a time in one process, so it uses one of the two
CPUs. The estimates kept that one CPU at 99% while they ran. The other CPU
stays free for the map, Postgres and book corners. Starting the worker with
`nice -n 10` in the `Procfile` would let web requests come first when both
want the CPU.

## Decision, AC6

All Italy at once. With the three changes, every step of an Italy night fits
in the 384 MB of the worker without swap, and the night ends more than an hour
and a half before the first check. One region at a time is not needed. It
would also read the same files once per region, about 20 reads of about 30 MB
each instead of one read of 111 MB.

The changes are in the pull request of this issue, so the later child issues
start from them.

## Repeat the run

```
uv run python experiments/italy_night_cost/run.py --steps database,weather
uv run python experiments/italy_night_cost/run.py --steps first_night,night,warmup_unlimited
uv run python experiments/italy_night_cost/run.py --steps night_384mb,warmup_384mb,tuscany
uv run python experiments/italy_night_cost/run.py --steps tuscany_old,weather_night,weather_night_384mb,weather_first_load_384mb
```

The settings, the steps and the VPS facts are in
`experiments/italy_night_cost/config.toml`. The database name must contain
`estimate_benchmark`. The first command creates it from `sporameteo_native`
and builds the app image if it is missing. Add `--rerun` with the step names
after a code change, and set `rebuild_image` so the container gets the new
code. `tuscany_old` builds a second image from `master`. The accuracy check of
the faster calculation runs on the laptop:

```
SPORAMETEO_DB_NAME=sporameteo_estimate_benchmark_20261017 SPORAMETEO_DB_PORT=5542 \
SPORAMETEO_FOREST_BUILD_VERSION=italy-forest-copernicus-2018-v1 \
uv run python experiments/italy_night_cost/phase.py compare --assessment-date 2026-10-17
```

The weather reads of this issue downloaded about 550 MB in all, in reads of
155 MB or less each, under the stop limit of 1 GB per read.
