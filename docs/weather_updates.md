# Weather updates

The application stores weather by 0.1 degree weather cell and Italian assessment date. The assessment date uses `Europe/Rome`, so the date changes at Rome midnight on both daylight saving clock-change days. The service requests a cell only when its current assessment snapshot is missing.

The first request for a cell asks Open-Meteo for 21 previous completed Italian days, the assessment date and the following seven dates. A later assessment reuses the exact previous ready snapshot for dates that were already completed on that assessment date. It refreshes the new current and forecast dates with an 11-day request. If an older forecast has become a completed date, the service requests that missing history in pieces of at most 13 days before the 11-day request. The new snapshot is written only after every expected date is present or has a checked known gap. A known gap remains a ready snapshot with a null value and its reason. A refused or interrupted request remains pending and never becomes a known gap.

Compatible cells share one request. Each request has at most 100 cells and carries its complete date, variable, model, time zone and provider option identity. The #44 quota reservation runs before every network attempt, including a retry. A 429 response keeps the full provider message, the retry time and the counted reservation. A request that completed at Open-Meteo but failed before daily storage may be fetched again only after the service confirms that no ready snapshot exists.

A visitor waits for up to three seconds using a monotonic deadline while the worker continues the durable task. A slow or pending fetch returns the last ready snapshot with its real assessment date, fetch time, source and snapshot ID. A cell with no ready snapshot returns `not_available_yet` with a stable reason code. The service stores only a SHA-256 visitor hash. One hash may start at most 100 newly triggered cell and assessment-date fetches in a rolling 60-second window. Current snapshots, previous readable snapshots and already pending cells do not consume that allowance. A stale cell that needs a new assessment does consume one allowance.

The queue worker owns provider calls. It claims a durable batch under sorted logical advisory locks and stores each successful date part before assembling the member snapshot. A stopped worker moves an abandoned running batch to pending, keeps its #44 quota reservation, and queues it after two minutes or the provider retry time. The weather task uses `run_after` for delayed retries. A permanent provider refusal stays failed until an explicit reopen. The `configure_estimate_callback` hook runs after the ready snapshot transaction commits. It receives `snapshot_id`, `cell_key`, `assessment_date` and `forest_build_version` as keyword values and is optional, so a weather fetch does not import the estimate code. A callback failure is retried from the ready snapshot without another provider request. The `configure_cleanup_callback` adapter receives `cleanup_date` as a keyword value and returns snapshot IDs still protected by estimate updates before weather snapshots are pruned.

Cleanup makes no provider requests. Keep the newest two snapshots per cell and any snapshot IDs supplied by the later estimate service. Delete only unreferenced daily rows older than 21 days before the cleanup date. A current or previous snapshot reference protects all of its daily rows even when that snapshot is older. Keep #44 request attempts for 31 days, then remove older attempts. The date-keyed cleanup task is idempotent and can be queued with:

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
