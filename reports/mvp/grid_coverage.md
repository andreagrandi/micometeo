# National grid coverage

## Source and licence

The build uses ISTAT's detailed administrative boundaries for 1 January 2026.
The [official source page](https://www.istat.it/notizia/confini-delle-unita-amministrative-a-fini-statistici-al-1-gennaio-2018-2/)
links the [original archive](https://www.istat.it/storage/cartografia/confini_amministrativi/non_generalizzati/2026/Limiti01012026.zip).
The archive contains 20 region geometries. All were valid before transformation.
The selected file is `Reg01012026/Reg01012026_WGS84.shp`. Its `.prj` identifies
EPSG:32632, which uses metres in UTM zone 32 north.

The archive was downloaded on 12 October 2026, Italian time. It contains
98,536,297 bytes and has SHA-256
`a9075f8d839dcb2b409099703da7bdd37cc214f8967fa7372b32305875ad046f`.
The server reported a last modification of 6 March 2026 at 09:47:36 UTC.

ISTAT's [legal terms](https://www.istat.it/note-legali/) apply
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) to its published
content unless it states otherwise. The archive contains no separate licence
or different restriction. Redistribution must credit ISTAT, link the licence
and identify changes. Use this credit with the derived grid:

> Source: ISTAT, administrative boundaries for statistical purposes, 1 January
> 2026, CC BY 4.0. Micometeo transformed the boundaries to EPSG:3035 and derived
> 500 m grid squares and their Italian land intersections.

No product grid geometry comes from GADM. Historical experiment files remain
separate and are not inputs to this command.

## Inclusion and reporting rules

Square corners are multiples of 500 m in EPSG:3035, an equal-area coordinate
system in metres. IDs record the lower-left corner. The build retains any
square with a positive Italian land intersection,
including coastal slivers and islands whose square centres lie at sea.
Sea-only squares are excluded. Full-square geometry and Italian land geometry
are stored separately.

The region with the greatest land intersection owns a square for reporting.
An exact tie goes to the lowest ISTAT region code. Each square therefore counts
once in the national total and once in the regional table. This ownership rule
does not erase its land in another region.

The 500 m grid is a display and join convention. It does not establish 500 m
prediction accuracy. Terrain, forest and weather builds retain their own
source dates, real detail and missing values.

## National run

The run completed on 12 October 2026, Italian time, on an Apple M2 Pro with
32 GiB of memory. PostGIS 17 with PostGIS 3.5 ran in the local Docker container.
The container uses the AMD64 image through emulation.

```sh
uv run python apps/application/manage.py migrate --noinput
/usr/bin/time -l uv run python apps/application/manage.py build_national_grid \
  data/raw/mvp_boundaries/Limiti01012026.zip \
  --build-version italy-500m-istat-2026-01-01-v1 \
  --expected-sha256 a9075f8d839dcb2b409099703da7bdd37cc214f8967fa7372b32305875ad046f \
  --downloaded-on 2026-10-12 \
  --chunk-size-m 25000 --progress
```

The final command result reported these values. Regional output follows in the
table below.

```json
{
  "build_id": "99f622dd-fd78-4fd9-b16b-1625205d862d",
  "build_version": "italy-500m-istat-2026-01-01-v1",
  "status": "completed",
  "cell_count": 1217473,
  "planned_chunk_count": 676,
  "completed_chunk_count": 676,
  "processed_chunks": 676,
  "reused_chunks": 0,
  "elapsed_seconds": 360.363,
  "peak_rss_mb": 447.7
}
```

The process took 361.60 seconds including startup. Its peak resident memory
was 469,401,600 bytes, or 447.7 MiB. The five grid tables and their indexes
occupied 1,170,563,072 bytes after the run. This includes full-square and land
geometries, regional source geometries, build records and checkpoints.

| ISTAT code | Region | Owned squares |
|---|---|---:|
| 01 | Piemonte | 102,247 |
| 02 | Valle d'Aosta/Vallée d'Aoste | 13,283 |
| 03 | Lombardia | 96,040 |
| 04 | Trentino-Alto Adige/Südtirol | 54,831 |
| 05 | Veneto | 73,646 |
| 06 | Friuli-Venezia Giulia | 32,206 |
| 07 | Liguria | 22,224 |
| 08 | Emilia-Romagna | 90,241 |
| 09 | Toscana | 92,707 |
| 10 | Umbria | 33,814 |
| 11 | Marche | 37,549 |
| 12 | Lazio | 69,309 |
| 13 | Abruzzo | 43,372 |
| 14 | Molise | 17,804 |
| 15 | Campania | 55,039 |
| 16 | Puglia | 78,478 |
| 17 | Basilicata | 40,043 |
| 18 | Calabria | 61,250 |
| 19 | Sicilia | 104,785 |
| 20 | Sardegna | 98,605 |
| Total | Italy | 1,217,473 |

All 20 regional counts are positive and their sum equals the distinct national
cell count. The build has no pilot-area filter. Sea-only cells are excluded by
the positive-area rule. Every positive source-land intersection remains in the
build, including very small slivers.

## Geometry and island checks

A PostGIS audit found no duplicate cell IDs, misaligned corners, squares with
an area other than 250,000 square metres, or invalid land geometries. Stored
land shares range from `7.452650689665957e-09` to `1.0`.

The sum of the cell land areas was 301,441,264,422.99194 square metres. The
union of the 20 stored source regions measured 301,441,264,423.0012 square
metres. The difference is 0.0093 square metres across the country.

The build retains 11,710 squares whose centres lie outside their Italian land
intersection. This count includes coast and international-border cells.
The Sardinian coastal square `500m_E4162000_N1961000` has 4.6182 percent Italian
land and its centre lies outside that land. It remains included.

These real coordinate lookups all returned `found` in the completed build.

| Place | Latitude | Longitude | Cell ID | Region |
|---|---:|---:|---|---|
| Palermo | 38.1157 | 13.3615 | `500m_E4617500_N1677000` | Sicilia |
| Cagliari | 39.2238 | 9.1217 | `500m_E4244500_N1793000` | Sardegna |
| Lampedusa | 35.5122 | 12.5730 | `500m_E4556500_N1388000` | Sicilia |
| Elba | 42.8120 | 10.3150 | `500m_E4346500_N2189500` | Toscana |

For example, repeat the small-island lookup with:

```sh
uv run python apps/application/manage.py lookup_national_grid \
  --build-version italy-500m-istat-2026-01-01-v1 \
  --latitude 35.5122 --longitude 12.5730
```

The source metadata names only the selected ISTAT archive and its selected
members. An audit of that record found no GADM reference. The product loader
reads the ISTAT ZIP directly and does not read the historical experiment
boundary files.

## Repeatability and software checks

Repeating the build command reused all 676 chunks and processed zero chunks.
It returned the same build ID and 1,217,473 cells in 1.066 seconds. The input
fingerprint is
`d1950c864bd97e1d22bc0bf8ed9846464f9211db74b61c35018f6a98bd9b455b`.

The focused command passed:

```sh
uv run pytest tests/app/test_national_grid.py tests/test_habitat.py
```

Fixtures cover mainland edges, a coastal sliver with its centre outside land,
a small island, Sicily, Sardinia, sea-only cells and region ownership ties.
Database tests check interrupted-build recovery, completed-build reuse,
unchanged IDs and timestamps, changed-input rejection, coordinate lookups,
outside coverage and invalid input. Django configuration and migration checks
also passed.
