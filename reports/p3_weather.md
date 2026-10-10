# P3a weather before each find

Issue #6.

## Question

For a past date, can we rebuild the weather someone would have known that day
when deciding where to look for porcini?

## Answer

Yes, with one limit on the last 6 days. One command rebuilds the rain,
temperature, evaporation, soil moisture and soil temperature of the 7, 14 and
30 days before each of 300 finds. It takes about 10 minutes on the first run
and 8 seconds once the downloads are cached. All 300 finds get complete
totals when we look back with the weather that actually happened.

Reconstructed past weather runs 5 to 6 days behind. On the morning of a find
the app could not have used it for the last 5 or 6 days. A second source,
the ECMWF weather model values for past hours, covers those days and is
complete up to yesterday. It only goes back to 2017, so 131 of the 300 finds
have no complete "on that morning" totals.

Swapping the last 6 days changes the rain total of a window by a median of
4.5 mm and by 18.7 mm or more for one place in ten. Different weather models
disagree much more than that about the last few days. On 10 October 2026, near
Lucca, the archive gave 108 mm of rain for the last 7 days and the Forecast
API default gave 1 mm.

## What was done

- The sample is all 85 finds in Tuscany and 215 finds drawn at random from
  Switzerland and Austria with seed 42, all from the P1 run
  `20261010T181005Z-696b43`.
- Each find becomes a place with `assessment_date` and `target_date` equal to
  the day of the find, and `days_ahead` equal to 0.
- `build_weather_features` in `src/micometeo/weather/features.py` returns one
  row per place, view and window. The experiment is
  `experiments/p3_weather/`.
- Each row has `assessment_date`, `target_date`, `days_ahead`, `view`,
  `window_days`, `source`, `dataset`, `value_kind`, the five weather totals,
  and the number of complete, reconstructed and model days.
- The full table is `weather_windows.parquet` in the run output folder. It is
  kept out of Git and rebuilt by the command below.

## How to rebuild

```
uv run micometeo run p3_weather
```

Run records:

- [first run, no cache](runs/p3_weather/20261010T195440Z-a38289.json)
- [second run, from cache](runs/p3_weather/20261010T200424Z-b095fd.json)
- [third run, from cache](runs/p3_weather/20261010T200448Z-323d30.json)
- [fourth run, from cache, after skipping empty requests, which wrote the CSV files](runs/p3_weather/20261010T210035Z-f76e51.json)

## Sources

| Source | Dataset | What it is | Level of detail | Years | Licence |
|---|---|---|---|---|---|
| Open-Meteo Historical Weather API | `era5_seamless` | Reconstructed past weather. ERA5 and ERA5-Land are produced by the European weather centre ECMWF for the Copernicus programme. They combine past measurements with a weather model. | About 9 km for temperature and soil, from ERA5-Land. About 25 km for rain and evaporation, from ERA5, because ERA5-Land has no rain in this API. | 1940 onward | CC BY 4.0 through Open-Meteo. The underlying Copernicus data asks for attribution. |
| Open-Meteo Historical Weather API | `ecmwf_ifs` | The ECMWF weather model's values for past hours, kept as they were published. | About 9 km | 2017 onward | CC BY 4.0 |
| Open-Meteo Forecast API, `past_days` | `best_match` | The values of the weather model that Open-Meteo picks for the place, for past hours. | Depends on the model picked | The last 92 days only | CC BY 4.0 |

The free Open-Meteo API is for non-commercial use only. Nothing in this
experiment is labelled as a forecast. Every `value_kind` is either
"reconstructed past weather", "reconstructed past weather and model values
for past hours", or "model values for past hours".

No weather station was compared. That stays open, see Limits.

## Day boundary and time zone

- A day runs from midnight to midnight Italian time, Europe/Rome, as set in
  `docs/data_formats.md`. Swiss and Austrian finds use the same time zone.
- The code asks Open-Meteo for hourly values in UTC and groups them into
  Italian days itself. The day when summer time ends has 25 hours and the day
  it starts has 23. A day counts as complete only when all its hours have a
  value.
- The 7 days before an `assessment_date` are the 7 complete days ending the
  day before it. The same holds for 14 and 30 days. Nothing from the
  assessment date itself is used, because on that morning the day is not over.
- The requests never ask for a date on or after the assessment date. The code
  also drops any day on or after it and raises an error if a window would
  include one. The test
  `test_look_back_totals_match_hand_sums_and_ignore_later_days` fills every
  hour from the assessment date on with 1,000 mm of rain and checks that none
  of it reaches a total.

## How late each source publishes

Checked on 10 October 2026 at 20:04 UTC and again at 21:00 UTC at one point
in the Pistoia sample area, with the same result, file `p3_delays.csv`:

| Source | Last complete day | Days missing before today |
|---|---|---|
| `era5_seamless` | 4 October | 5 |
| `era5` | 4 October | 5 |
| `ecmwf_ifs` | 9 October | 0 |
| Forecast API `best_match` | 9 October | 0 |

The archive also returns values for today from `ecmwf_ifs`, including hours
that have not happened yet. The code never asks for today, so these values
are never used.

The check ran in the evening. In the morning the newest reconstructed day may
not be out yet, so the experiment treats the last 6 days as missing from
reconstructed past weather. The setting is `reconstructed_missing_days` in
`experiments/p3_weather/config.toml`.

## Look back compared with what was known that morning

The run keeps two views apart:

- `look_back` uses reconstructed past weather for every day. It is the
  weather that actually happened, as known today. The app could not have had
  all of it on the morning of the find.
- `on_the_morning` uses reconstructed past weather up to 7 days before the
  assessment date, and `ecmwf_ifs` model values for the last 6 days. This is
  what the app could have used that morning.

Complete totals, file `p3_summary.csv`:

| Area | Places | Complete look back | Complete on that morning |
|---|---|---|---|
| Tuscany | 85 | 85 | 78 |
| Switzerland and Austria | 215 | 215 | 91 |

The missing "on that morning" totals are finds from before 2017, when
`ecmwf_ifs` has no data.

How far the two views differ for the same find, file
`p3_view_differences.csv`:

| Window | Finds compared | Median rain difference | Rain difference for 1 find in 10 | Median temperature difference |
|---|---|---|---|---|
| 7 days | 169 | 4.5 mm | 18.7 mm or more | 0.37 °C |
| 14 days | 169 | 4.5 mm | 18.7 mm or more | 0.18 °C |
| 30 days | 169 | 4.5 mm | 18.7 mm or more | 0.09 °C |

The rain difference is the same for every window, because only the last 6
days change. For a 7 day window those 6 days are almost the whole total.

## What is really available this morning

For the Pistoia point and 4 Tuscan find places, the run built the "on that
morning" totals for today, 10 October 2026, in two ways, file
`p3_today_check.csv`:

| Place | 7 day rain, Forecast API `best_match` | 7 day rain, archive `era5_seamless` and `ecmwf_ifs` |
|---|---|---|
| Pistoia point | 24.5 mm | 49.4 mm |
| `inat:63692615` | 87.4 mm | 34.2 mm |
| `inat:143452391` | 1.9 mm | 83.7 mm |
| `inat:125896300` | 47.4 mm | 46.1 mm |
| `inat:244269377` | 1.0 mm | 107.8 mm |

This is not a bug. For `inat:244269377`, near Lucca, the daily rain for 7 to
9 October was:

| Model | 7 October | 8 October | 9 October |
|---|---|---|---|
| `ecmwf_ifs` | 13.8 mm | 75.3 mm | 18.5 mm |
| `ecmwf_ifs025` | 10.3 mm | 43.2 mm | 34.9 mm |
| `italia_meteo_arpae_icon_2i` | 19.4 mm | 5.5 mm | 0.9 mm |
| `icon_seamless` | 0.3 mm | 0.5 mm | 0.0 mm |
| `best_match` | 0.2 mm | 0.7 mm | 0.1 mm |

The `ecmwf_ifs` values from the Forecast API and from the archive are the
same, so the archive does hold what the app could fetch that morning. The
models still disagree by up to 100 mm about how much rain fell at one place
in the last few days.

## Cost and speed

First run, 20261010T195440Z-a38289, with an empty cache:

- 600 requests for the 300 finds, two per find. See "Fewer requests" below
  for the 131 that were not needed.
- 447 seconds spent waiting for Open-Meteo, 579 seconds for the whole run.
- About 964 calls counted against the free plan. A request with more than 14
  days counts as more than one call. The free plan allows 600 calls a minute,
  5,000 an hour and 10,000 a day.
- 19 more requests, about 32 calls, for the delay check and today check.

Second run, 20261010T200424Z-b095fd, with the cache:

- 0 requests and 600 cache hits for the 300 finds, 0.5 seconds.
- The delay check and today check always ask again, because their point is
  to see the latest data. They took 7.6 seconds.

`p3_metrics.csv` holds the numbers of the latest run. The cache is in
`data/raw/p3_weather/cache/`, one JSON file per request.

### Fewer requests

The first run asked `ecmwf_ifs` about 131 finds from before 2017. That
dataset starts on 1 January 2017 at 00:00 UTC, so those 131 answers were
empty. The code now skips them. The fourth run gives the same
`weather_windows.parquet` with 469 requests instead of 600. With an empty
cache this sample would now cost about 833 free plan calls instead of 964.

Grouping finds that share a weather cell was also measured and is not worth
it for this sample:

- Rain comes from a grid about 25 km wide. The 85 Tuscan finds fall into 29
  of its cells and the 4,747 Swiss and Austrian finds into 250.
- A request can only be shared when the cell and the dates match. The finds
  span 1990 to 2026, so few of them match. Grouping finds in the same cell
  within 30 days of each other cuts the 300 ERA5 requests of this sample to
  271, and their calls by about 5 percent.
- On all 4,832 finds the same grouping would cut the ERA5 calls by about 40
  percent.
- Moving each place to the centre of its cell would also change its
  temperature, because Open-Meteo corrects temperature for the altitude of
  the exact place.

Open-Meteo accepts several places in one request, which cuts the number of
requests. This experiment did not check whether the free plan counts such a
request once or once per place.

### What the app would need

The app would not ask Open-Meteo once per user or per find. For a fixed area
it would download each day's weather once, either for the few dozen weather
cells that cover the area or as one regional file. ERA5 can be downloaded for
a whole region from the Copernicus data store, and ECMWF publishes its model
output as files. The app would then work out the conditions for every square
on its own server. P5 tests serving those precomputed results.

## What this means for A3

A3 says past weather is enough to judge conditions today. The PRD asks for up
to 30 days of weather before each date and place, with a record of where each
value came from and what it cost. This holds:

- 30 days of rain, temperature, evaporation, soil moisture and soil
  temperature exist for every find in the sample.
- Each row names its source, dataset and kind of value.
- The cost is at most 2 requests and about 3.2 free plan calls per find, and
  the cache makes repeat runs free.

Three findings shape how later experiments use it:

- The weather the app can use on a morning is not the weather that actually
  happened. The last 6 days come from a weather model and can differ a lot
  from the reconstructed values that appear later.
- Finds before 2017 can only be studied with the look back view.
- Rain detail is about 25 km in the reconstructed past weather. That cannot
  separate one mountain valley from the next.

## Limits

- No weather station was compared. Tuscany's regional hydrological service
  and the Swiss and Austrian weather services publish station data. Their
  licences and access were not checked here.
- The 6 missing days come from one evening check, not from a record of
  publication times over months.
- The archive's `ecmwf_ifs` values are assumed to be the values that were
  online on the morning of each find. For today they match the Forecast API.
  For past dates this was not checked.
- A find from the last 6 days before a run gets incomplete reconstructed
  values, and the cache keeps them. Delete its cache file to fetch it again.
- The sample is 300 finds. The free plan would allow a larger one.
