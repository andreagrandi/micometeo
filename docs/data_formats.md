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
| coordinate_uncertainty_m | float | Reported position error in metres, empty if unknown. |
| coordinates_obscured | boolean | True if the source hid the exact position. |
| identification_quality | string | How the species was confirmed, for example photo checked by an expert. |
| licence | string | Licence of the record. |
| rights_holder | string | Who holds the rights to the record. |
| cell_id | string | ID of the grid square that holds the point. |
| retrieved_at | timestamp | When we downloaded the record, UTC. |
| duplicate_of | string | `record_id` of the record this one repeats, empty if not a duplicate. |

Obscured coordinates are never published.

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
