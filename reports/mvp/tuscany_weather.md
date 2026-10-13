# Tuscany weather run

This report covers issue #98. It records the first real run of
`refresh_tuscany_weather` on the local database `micometeo` on 13 October 2026.
The forest build `italy-forest-copernicus-2018-v1` covers Italy, and the
command kept only the 71,031 forest squares of ISTAT region 09. They share 333
weather cells. No national request, new provider or deployment was part of
this run.

## Window

The assessment date was 13 October 2026. The window ran from 13 September to
20 October 2026: 30 completed days, today and 7 future days, 38 dates in all.

## Plan before the run

Before the run, 60 of the 333 cells already had a ready snapshot for 13
October, built from earlier visitor requests. Their history was reused and
nothing was asked again for them. The dry run made no write and no provider
call. The local database held 53 request attempts before and after it.

| Part | Dates | Cells | HTTP requests | Counted calls |
|---|---|---|---|---|
| History | 13 to 25 September | 273 | 3 | 273 |
| History | 26 September to 8 October | 273 | 3 | 273 |
| History | 9 to 12 October | 273 | 3 | 273 |
| Forecast | 13 to 20 October | 273 | 3 | 273 |
| Total | | | 12 | 1,092 |

## Calls and attempts

- When the worker started, it first ran 12 visitor requests that were already
  queued before this change. They took 36 counted calls within 5 seconds and
  filled part of the plan.
- The scheduled run then planned 1,062 counted calls in 12 HTTP requests. It
  made 12 attempts, all successful, and reserved 1,056 counted calls.
- Together the two sources used 1,092 counted calls, the same figure as the
  dry run. That is 12 percent of the 9,000 calls allowed per day.
- No request was refused, retried or sent twice.

## Timing

- The run started at 20:47:16 UTC and completed at 21:31:37 UTC.
- Consecutive requests started between 90.3 and 90.9 seconds apart, except
  around one interruption.
- The third request started late, at 21:05:30, because the local Docker
  engine was slow to answer. Soon after, the engine stopped answering and the
  worker stopped with a database connection timeout. After the engine
  restarted, running the command again resumed the
  same run at 21:19:28. The 3 finished batches were not requested again, so the
  run made exactly one attempt per batch.
- Without the interruption, 12 requests at 90 second intervals take about 17
  minutes.

## Stored size

| Measure | Before | After |
|---|---|---|
| Database size | 2,220 MB | 2,319 MB |
| Daily weather rows | 3,127 | 13,501 |
| Daily weather table with indexes | 7.8 MB | 66.6 MB |
| Snapshot, day link and summary tables | not measured | 13 MB |

The database growth also includes the 12 visitor requests and the new
migration.

## Result

- The run ended as `completed`. All 333 cells have a ready snapshot for 13
  October.
- A new dry run for 13 October plans 0 counted calls.
- A dry run for 14 October plans a normal night: 13 October from the history
  source and 14 to 21 October from the forecast source, 666 counted calls in 8
  HTTP requests.
