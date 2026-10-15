# Tuscany input readiness

This report covers issue #97. It records one run of `prepare_tuscany_inputs`
on the local Tuscany database `sporameteo_tuscany_56` on 13 October 2026. No
national processing, new provider or deployment was part of this run.

## Source versions

| Source | Version | State |
|---|---|---|
| ISTAT administrative geometry | `tuscany-grid-italy-500m-istat-2026-01-01-v1-56` | ready |
| Copernicus forest | `tuscany-forest-italy-forest-copernicus-2018-v1-56` | ready |
| Copernicus terrain | `tuscany-terrain-italy-terrain-glo30-2021-v2-56` | ready |
| JRC host trees | `d8998582df944b32f134ef85beb51380e255e4702d6714ebb01b5bd3029ddd0a` | ready |

The JRC version is the SHA-256 of its manifest. The run recorded these four
versions in one `TuscanyInputSet` row.

## Coverage

- The grid holds 92,707 squares, all owned by ISTAT region 09.
- Every square has a forest row and a terrain row.
- 71,031 squares meet the forest threshold. Each of them has stored host-tree
  values under the current JRC version.
- The forest build references 71 source chunks and its 2 km layer file. The
  terrain build references 11 available source tiles. All files were present
  and matched their stored checksums.

Earlier worker runs had already stored host-tree values for all 71,031
squares, so this run sampled nothing new. Before reusing them, a fresh sample
of all 71,031 squares from the same checked JRC files was compared with the
stored rows. All 71,031 rows matched exactly. A repeat run also made no
request, added no rows and kept one `TuscanyInputSet` row.

## Time

- Dry run: 1.6 seconds.
- Real run with all inputs stored: 2.2 seconds, including the checksum checks
  of the forest, terrain and JRC files.
- Sampling all 71,031 squares from the local JRC files, measured separately
  without writing: 37.9 seconds. This is the cost of a first preparation or of
  a new JRC version.

## Size

Database tables in `sporameteo_tuscany_56`, including indexes:

| Table | Size |
|---|---|
| `estimate_updates_hosttreecache` | 30.4 MB |
| `estimate_updates_tuscanyinputset` | 64 KB |
| `national_grid_gridbuildcell` | 49.2 MB |
| `national_grid_gridcell` | 27.3 MB |
| `national_grid_gridregion` | 1.3 MB |
| `national_forest_forestcell` | 31.7 MB |
| `national_terrain_terraincell` | 27.5 MB |

The whole database, which also holds weather and estimates, is 357 MB.

Source files on disk:

- JRC host-tree folder: 643 MB, for all of Europe.
- Forest chunks used by Tuscany: 456 MB. The shared forest cache folder holds
  3.8 GB for Italy.
- Terrain tiles used by Tuscany: 354 MB. The shared terrain cache folder holds
  1.9 GB for Italy.
- Tuscany forest layer file: 204 KB.

## Command

```sh
SPORAMETEO_DB_NAME=sporameteo_tuscany_56 \
SPORAMETEO_FOREST_BUILD_VERSION=tuscany-forest-italy-forest-copernicus-2018-v1-56 \
SPORAMETEO_TERRAIN_BUILD_VERSION=tuscany-terrain-italy-terrain-glo30-2021-v2-56 \
uv run python apps/application/manage.py prepare_tuscany_inputs
```
