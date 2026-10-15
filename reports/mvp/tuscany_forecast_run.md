# Tuscany estimate run

This report covers issue #99. It records the first real run of
`run_tuscany_forecast` on the local database `sporameteo` on 14 October 2026.
The run used the weather that the #98 run stored for 13 October. The forest
build `italy-forest-copernicus-2018-v1` covers Italy, and the run kept only
the 71,031 forest squares of ISTAT region 09. No national calculation, new
provider or deployment was part of this run.

## Inputs

| Input | Version |
|---|---|
| ISTAT administrative geometry | `italy-500m-istat-2026-01-01-v1` |
| Copernicus forest | `italy-forest-copernicus-2018-v1` |
| Copernicus terrain | `italy-terrain-glo30-2021-v2` |
| JRC host trees | `d8998582df944b32f134ef85beb51380e255e4702d6714ebb01b5bd3029ddd0a` |
| Formula | `porcini-experimental-v4`, unchanged |

This database has no `TuscanyInputSet` row, because #97 recorded its row in
the Tuscany-only database `sporameteo_tuscany_56`. The run stores the forest,
terrain and host-tree versions itself and links an input set only when one
matches.

## Plan before the run

The dry run wrote nothing. It listed 333 weather cells, all with ready
weather for 13 October, and 71,031 Tuscany forest squares. The target dates
were 13 to 20 October 2026, eight dates in all.

## Result

- The run ended as `published` and became the current published run. There
  was no earlier run, so the previous run is empty.
- All 333 cells completed. The run stored 333 estimate updates and 71,031
  result rows, one per Tuscany square with eight values each.
- No cell had a recorded weather gap.
- The database held 77 provider request attempts before and after the run.
  The calculation made no remote request.
- Running the command again for the same date returned the same published run
  in 1.5 seconds. It added no update and no result row.

## Time and memory

| Measure | Value |
|---|---|
| Calculation time recorded by the run | 144 seconds |
| Whole command, including start-up | 147 seconds |
| Peak memory recorded by the run | 142 MB |
| Peak memory of the whole process | 200 MB |

## Stored size

| Table with indexes | Size after the run |
|---|---|
| Estimate updates | 8.1 MB |
| Estimate results | 14 MB |
| Runs | 96 KB |
| Run cells | 200 KB |
| Whole database | 2,336 MB |

The estimate tables also hold 356 older updates from visitor requests. Most
of the update table size comes from the host-tree values stored with each
update.

## Limits

- The map, overview and details still read per-cell updates. They ignore the
  run results until #100 makes them read the published run.
- Each finished weather cell still starts the older single-cell estimate from
  #48. That estimate covers every square of the cell, including squares
  outside Tuscany.

## Command

```sh
uv run python apps/application/manage.py run_tuscany_forecast --dry-run --assessment-date 2026-10-13
uv run python apps/application/manage.py run_tuscany_forecast --assessment-date 2026-10-13
```
