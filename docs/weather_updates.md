# Weather updates

The application stores weather by 0.1 degree weather cell and Italian assessment date. The assessment date uses `Europe/Rome`, so the date changes at Rome midnight on both daylight saving clock-change days. Weather is prepared ahead by a scheduled run, described below. The map, overview and details read the published Tuscany run and never start a provider request, as described in `docs/api.md`.

The window of a snapshot is 38 dates: the 30 completed Italian days before the assessment date, the assessment date and the following seven dates. Completed days come from the historical source, `MICOMETEO_WEATHER_HISTORY_ENDPOINT`, which defaults to the Open-Meteo archive. Today and the next seven days come from the forecast source. The planner asks for completed days in pieces of at most 13 days, so a full first load is pieces of 13, 13 and 4 days plus one forecast of 8 days. A normal night asks for yesterday plus one forecast of 8 days.

Completed days are stored once and read from the database before any request is planned. A stored day counts as history only when it came from the historical source, has the status complete or checked known missing, and carries the current `history_version` in its metadata. If several rows exist for one date, the oldest one is used. A forecast row for a date that has passed is never history, so the next night fetches that day from the historical source. The reused rows are attached to the new fetch as completed parts with the reason `stored_history` and no request, and the snapshot is built from them. A day that was reused needs no provider request after a restart.

`WEATHER_HISTORY_VERSION` in `src/micometeo/weather/policy.py` is the explicit correction switch. Raising it stops the reuse of older rows. The next run fetches the history again and stores new rows. The older rows and the snapshots built from them stay in the database. Cleanup never deletes rows from the historical source.

The new snapshot is written only after every expected date is present or has a checked known gap. A known gap remains a ready snapshot with a null value and its reason. A refused or interrupted request remains pending and never becomes a known gap, and it stores no rows.

Compatible cells share one request. Each request has at most 100 cells and carries its complete date, variable, model, time zone and provider option identity. The #44 quota reservation runs before every network attempt, including a retry. A 429 response keeps the full provider message, the retry time and the counted reservation. A request that completed at Open-Meteo but failed before daily storage may be fetched again only after the service confirms that no ready snapshot exists.

The on-demand service `request_weather` remains in `weather_on_demand/services.py`, but no page request calls it since #100. A caller waits for up to three seconds using a monotonic deadline while the worker continues the durable task. A slow or pending fetch returns the last ready snapshot with its real assessment date, fetch time, source and snapshot ID. A cell with no ready snapshot returns `not_available_yet` with a stable reason code. The service stores only a SHA-256 visitor hash. One hash may start at most 100 newly triggered cell and assessment-date fetches in a rolling 60-second window. Current snapshots, previous readable snapshots and already pending cells do not consume that allowance. A stale cell that needs a new assessment does consume one allowance.

The queue worker owns provider calls. It claims a durable batch under sorted logical advisory locks and stores each successful date part before assembling the member snapshot. A stopped worker moves an abandoned running batch to pending, keeps its #44 quota reservation, and queues it after two minutes or the provider retry time. The weather task uses `run_after` for delayed retries. A permanent provider refusal stays failed until an explicit reopen. The `configure_estimate_callback` hook runs after the ready snapshot transaction commits. It receives `snapshot_id`, `cell_key`, `assessment_date` and `forest_build_version` as keyword values and is optional, so a weather fetch does not import the estimate code. A callback failure is retried from the ready snapshot without another provider request. The `configure_cleanup_callback` adapter receives `cleanup_date` as a keyword value and returns snapshot IDs still protected by estimate updates before weather snapshots are pruned.

Cleanup makes no provider requests. Keep the newest two snapshots per cell and any snapshot IDs supplied by the later estimate service. Delete only unreferenced daily rows older than 30 days before the cleanup date, and never a row from the historical source. A current or previous snapshot reference protects all of its daily rows even when that snapshot is older. Keep #44 request attempts for 31 days, then remove older attempts. The date-keyed cleanup task is idempotent and can be queued with:

```sh
uv run python apps/application/manage.py cleanup_weather
```


For a local LaunchAgent, run the command once each night after the worker is available:

```xml
<key>ProgramArguments</key>
<array>
  <string>/Users/andrea/Projects/micometeo/.venv/bin/python</string>
  <string>/Users/andrea/Projects/micometeo/apps/application/manage.py</string>
  <string>cleanup_weather</string>
</array>
<key>StartCalendarInterval</key>
<dict>
  <key>Hour</key>
  <integer>3</integer>
  <key>Minute</key>
  <integer>10</integer>
</dict>
```

The status command reports fetches by assessment date, weighted provider calls
and a separate attempt count. It also reports refused requests with their full
messages, pending cells and the last cleanup:

```sh
uv run python apps/application/manage.py weather_on_demand_status
```

## Scheduled Tuscany refresh

`refresh_tuscany_weather` prepares the 38-day window for every weather cell that holds a Tuscany forest square. It accepts only region code `09`. A weather cell shared by several forest squares is counted once. The forest build comes from `MICOMETEO_FOREST_BUILD_VERSION` unless `--forest-build-version` is given. The assessment date is today in Europe/Rome unless `--assessment-date` is given.

Print the plan first. The dry run reads the database only. It writes nothing and makes no provider call. It prints the mode, the number of cells, the cells that are already ready for the date, the counted calls and the HTTP requests for each date range:

```sh
uv run python apps/application/manage.py refresh_tuscany_weather --dry-run
```

Start the run without `--dry-run`. The command stores a `ScheduledWeatherRun` for the region and date, plans the batches of at most 100 cells, queues one task and prints the run ID:

```sh
uv run python apps/application/manage.py refresh_tuscany_weather
```

The run is in `initial` mode while no Tuscany cell has a ready snapshot for an earlier date, and in `refresh` mode afterwards. The initial load costs 1,332 counted calls for 333 cells: three history pieces of 13, 13 and 4 days and one forecast of 8 days, which is 4 calls per cell. A normal night costs 666 counted calls: yesterday and one forecast of 8 days, which is 2 calls per cell. Counted calls and HTTP requests are different numbers. With 333 cells the initial load sends 16 HTTP requests and a normal night sends 8, because each piece needs one request per 100 cells.

The queued task takes one batch, runs it, and then queues itself again. It starts the next provider request at least 90 seconds after the previous start, so only one request of the run is in progress. The shared quota reservation still runs before every attempt, with limits of 540 per minute, 4,500 per hour, 9,000 per day and 270,000 per 31 days. When a reservation is refused or the provider asks for a delay, the whole run waits until the retry time. A restart does not repeat completed parts. Running the command again for the same date resumes the same run and creates no second run, batch or request. The worker recovery command also queues a task again for an unfinished run.

A run ends as `completed` when every Tuscany cell has a snapshot for the date. It ends as `failed` with a reason when a batch is refused for good. A failed run never deletes or replaces stored rows or snapshots. After `reopen_weather_fetch` has reopened the failed batches, running the command again resumes the run. The run record keeps the planned counted calls, the planned HTTP requests, the number of provider attempts and the start and end times. The database size can be read with `pg_database_size` before and after a run.

The nightly schedule is an external cron entry that calls the command. For example, to start at 02:30 Europe/Rome:

```cron
CRON_TZ=Europe/Rome
30 2 * * * cd /path/to/micometeo && uv run python apps/application/manage.py refresh_tuscany_weather
```

The background worker must be running, for example `run_background_worker`, because the command only plans and queues the run.

## Live worker check

On 12 October 2026, a map request near Abetone queued the missing weather cell
at 44.15, 10.65. The normal `run_background_worker --batch` process made one
provider request at `2026-10-12T02:08:41.172757Z`. It stored 29 daily rows and
eight summaries, then handed the snapshot to the estimate task. The estimate
task stored 340 forest-square rows.

The next map response returned six available squares. Its selected-area
response used the same saved update UUID. Repeating the request made no
provider call. An Italy-wide view created no weather fetch. The source attempt
was `b4d638f5-fef5-4561-891b-3fcd40a343ac` and the snapshot was
`c98dd3ba-6290-4711-a791-b84113ffed79`.

The ignored local evidence is
`data/processed/map_checks/micometeo-live-pipeline-verified.json`.
This bounded check used real provider data for one weather cell. The separate
national estimate benchmark used synthetic weather and made no HTTP requests.
