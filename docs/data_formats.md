# Data formats

## Coordinates

Points such as finds are stored as WGS84 latitude and longitude. This is
EPSG:4326, in decimal degrees. It is the system GPS and GBIF use.

Grid and area calculations use ETRS89 Lambert equal area for Europe. This is
EPSG:3035, in metres. Equal area means a square of the same size covers the
same ground in the north and the south, so counts and densities compare fairly.

## Grid

The grid uses 500 m squares aligned to the EPSG:3035 origin. Square corners are
multiples of 500 m.

The square ID is `500m_E{x}_N{y}`. Here x and y are the lower-left corner in
metres, for example `500m_E4321500_N2345000`.

If experiment P2 shows that another size fits better, the same rule applies
with that size as the prefix, for example `250m_...`. The change is recorded in
`docs/decisions.md`.

A square never claims more detail than its coarsest input. If a source only
knows an area of 1 km, the result for that area is not shown at 500 m.

## Find records

One row per reported find.

| Column | Type | Meaning |
|---|---|---|
| record_id | string | Our own stable ID for the row. |
| source | string | Name of the data source, for example GBIF. |
| source_record_id | string | ID of the record in that source. |
| dataset_key | string | ID of the dataset inside the source. |
| taxon_name | string | Scientific name as reported. |
| taxon_key | integer | Taxon ID in the source. |
| event_date | date | Day of the find in Italian time, `YYYY-MM-DD`. |
| latitude | float | WGS84 latitude in decimal degrees. |
| longitude | float | WGS84 longitude in decimal degrees. |
| published_latitude | float | For a blurred record, the latitude the source published. It is shifted or rounded, so latitude stays empty. |
| published_longitude | float | For a blurred record, the longitude the source published. |
| coordinate_uncertainty_m | float | Reported position error in metres, empty if unknown. |
| coordinates_obscured | boolean | True if the source hid the exact position. |
| identification_quality | string | How the species was confirmed, for example photo checked by an expert. |
| licence | string | Licence of the record. |
| rights_holder | string | Who holds the rights to the record. |
| cell_id | string | ID of the grid square that holds the point. |
| retrieved_at | timestamp | When we downloaded the record, UTC. |
| duplicate_of | string | `record_id` of the record this one repeats, empty if not a duplicate. |

A blurred record keeps its published point only in published_latitude and published_longitude, so it never counts as an exact find.

## Timing finds

One row per find that has a day and a species but a blurred position or a position error above 1 km. Each row holds a coarse square of 10 or 30 km and the rough point it was built from. That is enough to match a find with the weather around it, but not with habitat at 500 m.

| Column | Type | Meaning |
|---|---|---|
| record_id | string | `record_id` of the find record. |
| source | string | Name of the data source. |
| area | string | `home` or `comparison`. |
| in_pistoia | boolean | True if the find lies in Pistoia province. |
| event_date | date | Day of the find, `YYYY-MM-DD`. |
| year | integer | Year of the find. |
| season | string | Season of the find. |
| species_group | string | Always `porcini`, see decision D3. |
| taxon_name | string | Scientific name as reported. |
| square_id | string | ID of the coarse square in the same format as `cell_id`, for example `10000m_E4321000_N3210000`. |
| square_size_m | integer | Side of the square in metres, 10000 or 30000. |
| rough_latitude | float | Latitude the source published. The find lies somewhere near it, within about the square size. |
| rough_longitude | float | Longitude the source published. |
| failed_filter | string | Why the find is not an exact find, `blurred` or `low_accuracy`. |
| identification_quality | string | How the species was confirmed. |
| licence | string | Licence of the record. |

The square size follows the position error:

- A blurred iNaturalist find gets the 30 km square.
- A find with a position error up to 5 km gets the 10 km square. This includes GBIF records rounded to the Swiss 5 km grid, which report 3535 m.
- A find with a position error from 5 km up to 30 km gets the 30 km square.
- A find with a larger or unknown error is dropped.

The square holds the rough point. Duplicates, weakly identified finds, bad GBIF issues and points outside the area box are dropped as for exact finds.

## Test cases

`cases.parquet` from `experiments/p4_test_rules/`. One row per 500 m square and day with at least one reliable find. The rules are in `docs/test_rules.md`.

| Column | Type | Meaning |
|---|---|---|
| case_id | string | `cell_id` and day, for example `500m_E4465500_N2301000_2016-10-01`. |
| area | string | `home` or `comparison`. |
| cell_id | string | The 500 m square. |
| assessment_date | date | Day of the finds, `YYYY-MM-DD`. |
| year | integer | Year of the day. |
| block_id | string | 100 km block that holds the square's lower-left corner, for example `100km_E4300000_N2600000`. |
| block_group | string | `tuning`, `test` or `final` for the comparison area, `home` for the home area. |
| set | string | `tuning`, `test`, `final`, `buffer`, `home_test` or `home_final`. Cases marked `buffer` are left out. |
| record_ids | list of strings | `record_id` of each find in the case. |
| find_count | integer | Number of finds in the case. |
| latitude | float | Latitude of the square's centre. |
| longitude | float | Longitude of the square's centre. |

## Comparison points

`comparison_points.parquet` from `experiments/p4_test_rules/`. One row per random place matched to a test case. Nobody reported a find there on that day.

| Column | Type | Meaning |
|---|---|---|
| case_id | string | The case the point belongs to. |
| set | string | Set of the case. |
| area | string | Area of the case. |
| point_kind | string | `forest` for a random forest square, `known_spot` for a square with a find on another day. |
| cell_id | string | The 500 m square of the point. |
| latitude | float | Latitude of the square's centre. |
| longitude | float | Longitude of the square's centre. |
| assessment_date | date | Day of the case. |

## File formats

| Use | Format |
|---|---|
| Tables | Parquet |
| Points and shapes | GeoParquet |
| Raster maps | GeoTIFF |
| Small tables that people read | CSV |
| Run records | JSON |
| Experiment settings | TOML |

All text files use UTF-8.

## Dates

A day runs from midnight to midnight Italian time, Europe/Rome. This holds on
the days when summer time starts and ends, which have 23 and 25 hours.

- Dates are stored as `YYYY-MM-DD` in Italian time.
- Timestamps are stored as ISO 8601 in UTC with `Z`, for example
  `2026-10-10T15:30:00Z`.
- Column names are `assessment_date`, `target_date` and `days_ahead`.
- The 7 days before an `assessment_date` are the 7 full days ending the day
  before it. The same holds for 14 and 30 days.
- Only data that existed before midnight Italian time at the start of
  `assessment_date` may be used. Weather published later is not used, even if
  it describes earlier days.
- Request Open-Meteo daily values with `timezone=Europe/Rome`.
