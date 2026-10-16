# Reading the Italy weather from Open-Meteo files on AWS

Issue #125, part of epic #123.

## Question

Can a read of Open-Meteo files on AWS give our weather variables for every
Italian weather cell, both for a first load of 38 days and for one night, at a
size and speed a small server can handle, with the same values as the API?

## Answer

Yes. One read of the `ecmwf_ifs` files gave all eight variables for the 3,726
Italy weather cells that hold forest. It took 133 MB and 2 minutes for the
first load of 38 days, and 89 MB and 1.3 minutes for one night. File values
for 20 Tuscany cells match the API with `models=ecmwf_ifs` within the API's
rounding, on every hour of every variable, for past days and for days ahead.
No stop rule was reached.

Four findings matter for the next issues:

1. The grid point match copies the API exactly. It picked the same point as
   the archive API for all 353 Tuscany cells with stored answers, and for the
   20 compared cells in both APIs.
2. A night costs two thirds of a first load, not a quarter. The files store
   each grid point's 504 hours, 21 days, as one compressed block. Reading one
   hour costs the same as reading all 504 hours of that file.
3. The files hold every hour from 30 days back to 15 days ahead. The newest
   hour on the day of the read was 31 October 2026 at 00:00 UTC.
4. The bucket answers over plain HTTPS with each file's last change time. No
   AWS account is needed for this.

Run: `reports/runs/bulk_weather/20261016T095133Z-7934cd.json`, on 16 October
2026 from a laptop in Italy. Script: `experiments/bulk_weather/run.py`.

## What was read

- Cells: the 3,726 weather cells of the `italy-forest-copernicus-2018-v1`
  forest build, exported from the local database. 333 of them are in Tuscany.
- Assessment date: 16 October 2026. The 38 days are 16 September to
  23 October in Rome time, from 15 September 22:00 to 23 October 21:00 UTC.
- The night covers the newest completed day, today and 7 days ahead:
  15 to 23 October in Rome time.
- Variables: `precipitation`, `temperature_2m`, `soil_moisture_0_to_7cm`,
  `soil_temperature_0_to_7cm`, `dew_point_2m`, `shortwave_radiation`,
  `wind_u_component_10m` and `wind_v_component_10m`.
- Library: `omfiles` 1.2.0, the Python reader from Open-Meteo, added to the
  project dependencies.

### How the files are laid out

Each variable has one file per 21 days, named `chunk_<n>.om`. File `n` starts
at hour `n * 504` counted from 1 January 1970 UTC. `meta.json` gives
`chunk_time_length` as 504. The 38 days fall in files 986, 987 and 988. The
night falls in files 987 and 988.

Each file holds one array of 6,599,680 grid points by 504 hours. The points
run row after row from the North Pole, as the issue 124 report describes. The
array is stored in blocks of 6 neighbouring points by all 504 hours. One block
of temperature is about 2.2 KB.

`omfiles` reads part of a file without trouble. It asks for one block per
HTTP request. The blocks of one latitude row sit next to each other in the
file, so the script fetches 32 KB after each requested range and serves the
next blocks from that. This cut the request count several times over.

## AC1: size, requests and time

The script reads only the grid points that the 3,726 cells use: 2,819 points.
Points less than 12 apart in a row are read as one range. Eight files are read
at the same time.

| Read | Files | MB | HTTP requests | Minutes |
|---|---|---|---|---|
| Heights, once | 14 | 22.3 | 710 | 0.6 |
| First load, 38 days | 24 | 133.2 | 4,138 | 2.0 |
| One night, 9 days | 16 | 88.6 | 2,752 | 1.3 |

Source: `reports/bulk_weather_reads.csv`.

The heights are the place heights from the Copernicus 90 m elevation files
and the grid point heights from `HSURF.om`. They never change, so a server
reads them once and keeps them. Most of the 22 MB is the 32 KB fetched after
each place height. A smaller read-ahead for these files would cut it.

The first load is 133 MB, far below the 1 GB stop rule. It is 8 variables,
3 files each, and about 5.6 MB per file for all of Italy.

The night reads 2 files per variable instead of 3, because the 9 days cross
from file 987 into file 988. It downloads all 504 hours of both files. A night
on a day where the 9 days fit in one file would cost about 44 MB. File 988
starts on 22 October at 00:00 UTC, so the nights of 24 October to 4 November
need only that file.

Over a month, 8 nights in every 21 cross two files and the other 13 read one.
That averages about 61 MB a night and about 1.8 GB a month for all of Italy.
The bucket is public and charges the reader nothing, so the only cost is the
server's own traffic.

### What a server keeps

Nothing downloaded needs to stay on disk. The script reads a file, takes the
grid points it needs and drops the rest. What a server keeps for all of Italy
stays the same size every night, as long as days older than the 38-day window
are deleted:

| What is kept | Size |
|---|---|
| Grid point and height correction for each of the 3,726 cells | under 0.1 MB, kept for good |
| Hourly values, 38 days, 8 variables, 2,819 grid points, 4 bytes each | about 82 MB |
| The same hourly values stored as 2-byte numbers | about 41 MB |
| Daily values only, 38 days, 6 values per cell | about 3.4 MB |

Values are kept per grid point, not per cell, because several cells share one
point.

The app's current table is much larger than the weather it holds. In the local
database, `weather_summaries_weatherdaily` holds 13,501 daily rows in 66 MB,
about 4.9 KB per row. Most of it is source details, JSON metadata and indexes.
At that size, the 141,588 daily rows of all of Italy would take about 690 MB.
The size of each daily row, not the weather, decides how much the app keeps.

## AC2: matching a cell centre to a grid point

The script copies the API's choice for `cell_selection=land`, as the issue 124
report describes it:

1. Read the place height from `data/copernicus_dem90/static/lat_<whole degree>.om`,
   row `(latitude * 1200 + 108000) mod 1200` and column
   `(longitude + 180) * 1200`, with 32-bit floating point numbers as the API
   uses.
2. List the 3 by 3 grid points around the place on the evenly spaced rows of
   the API's O1280 grid, and find the nearest one.
3. If the nearest point's height in `HSURF.om` is within 100 m of the place
   height, use it with no correction.
4. Otherwise score each land point as the height gap plus 30 m per km, and
   take the lowest score. Then correct `temperature_2m`, `dew_point_2m` and
   `soil_temperature_0_to_7cm` by adding
   `(grid point height - place height) * 0.0065` °C.

The code is in `choose_point` and `surrounding_points` in the script.

Checks:

- For all 353 Tuscany cells with archive answers stored in the local
  database, the script picked the grid point the archive API returned. The
  place height equalled the stored `elevation` in every cell.
- For the 20 compared cells, the grid point matched the latitude and longitude
  of both the archive answer and the forecast answer. See
  `reports/bulk_weather_grid_match.csv`.
- 10 of the 20 cells were chosen because their grid point is not the nearest
  one. These are the cells where a plain nearest point would go wrong. The
  height correction for them runs from -4.17 °C to +2.79 °C.

In all of Italy, 1,082 of 3,726 cells use a point other than the nearest, and
1,885 cells get a height correction.

## AC3: file values against API values

The script asked both APIs once for all 20 cells, with `models=ecmwf_ifs`,
`cell_selection=land` and wind speed in m/s:

- archive API: 16 September to 15 October, 14,400 cell hours
- forecast API: 16 to 23 October, 3,840 cell hours

That cost 2 HTTP requests and about 63 counted calls, below the limit of 100.
The answers are saved in `data/raw/bulk_weather/api/2026-10-16/`.

| Variable | Typical gap | Largest gap | API decimals | Hours within rounding |
|---|---|---|---|---|
| `precipitation` | 0 mm | 0 mm | 1 | all |
| `temperature_2m` | 0.02 °C | 0.05 °C | 1 | all |
| `soil_moisture_0_to_7cm` | 0 | 0 | 3 | all |
| `soil_temperature_0_to_7cm` | 0.03 °C | 0.05 °C | 1 | all |
| `dew_point_2m` | 0.03 °C | 0.05 °C | 1 | all |
| `shortwave_radiation` | 0 W/m² | 0 W/m² | 0 | all |
| wind speed at 10 m | 0.002 m/s | 0.005 m/s | 2 | all |

The typical gap is the median of the absolute differences. The numbers are the
same for the archive and the forecast API. Every gap is at most half of the
API's last decimal, so all differences come from the API's rounding. Wind speed
from the files is `sqrt(u * u + v * v)`. Per API and variable numbers are in
`reports/bulk_weather_differences.csv`. Every hourly pair is in the run's
`hourly_pairs.csv` under `data/processed/`.

The API answers also hold `et0_fao_evapotranspiration` for issue 126. This
issue does not compare it, because the files do not store it.

## AC4: which hours the files hold

On 16 October 2026 at 09:52 UTC, the files read held:

| What | Hour, UTC |
|---|---|
| First hour of file 986 | 10 September 00:00 |
| First hour needed | 15 September 22:00 |
| Last hour needed | 23 October 21:00 |
| Last hour with a value | 31 October 00:00 |

All eight variables had a value for every cell and every hour of the 38 days.
`meta.json` gave the latest run as 16 October 00:00 UTC, available from 06:32
UTC, and `data_end_time` as 31 October 01:00 UTC. That is the end of the
latest run's 360 hours. The 30 past days, today and the 7 days ahead are all
in the files. Source: `reports/bulk_weather_coverage.csv`.

This read came after a 00 UTC run. The app's night starts at 00:30 UTC, when
the newest run is the 12 UTC run of the day before, which also reaches 360
hours. The question from issue 124 about the shorter 06 and 18 UTC runs did
not come up in this read.

Files 987 and 988 changed at about 08:30 UTC on the day of the read. File 986
last changed on 1 October. Each file's last change time comes back in the
`Last-Modified` header of a plain HTTPS request, so issue 128 can check for
new data without an AWS account.

## AC5: needed variables missing from the files

None. All eight variables are in `data/ecmwf_ifs/`, with no missing hour in
the 38 days. Evapotranspiration is not stored in FAO-56 form, as issue 124
found, and must be calculated from the inputs read here.

## Limits of this result

- One assessment date and one read time. Values for past hours may change
  when the archive loader rewrites them, as issue 124 found. The file and the
  API read the same files, so they still agree.
- The comparison covers 20 Tuscany cells. The grid match covers 353 Tuscany
  cells. Cells elsewhere in Italy use the same code but were not checked
  against the API.
- Times come from a laptop in Italy on a home connection. A server will see
  different times, but the same bytes and request counts.
