# P1: How many reliable porcini finds are recorded

Issue #3. Assumption A1: enough reliable, dated porcini finds with a location exist.

## Short answer

Tuscany and the Apennines have 85 reliable finds. That is too few to learn a link
between weather and finds from this area alone. Switzerland and Austria have 4,747
reliable finds, which is enough for that. A1 is INCONCLUSIVE: the data is enough
in the comparison area and not enough at home.

## What was done

- Species: the four porcini species as one group, decision D3 in `docs/decisions.md`.
- Areas: decision D4. The home area is Tuscany plus the Emilia-Romagna side of the
  Apennines, south of latitude 44.30. Pistoia province is counted on its own. The
  comparison area is Switzerland plus Austria.
- Sources:
  - One GBIF bulk download, key `0019331-260928105237408`, citable as
    [doi:10.15468/dl.gw48at](https://doi.org/10.15468/dl.gw48at). It holds 11,811 records.
  - The iNaturalist API for the same species and places, all quality levels.
  - OpenStreetMap extracts from Geofabrik, data of 8 October 2026, for roads and paths.
  - GADM 4.1 outlines, to draw random places inside each area.
- Script: `experiments/p1_observations/run.py`, run with
  `uv run sporameteo run p1_observations`. It rebuilds every table and the map from the
  saved downloads.
- Run record: `reports/runs/p1_observations/20261010T181005Z-696b43.json`. It holds the
  GBIF download key and DOI, the iNaturalist query settings, the download dates, the
  licence counts and the date of each map extract. The run took 154 seconds.

## Records removed as duplicates

A duplicate is the same find counted twice. Rules run in this order.

| Rule | Home | Pistoia | Comparison |
|---|---:|---:|---:|
| Same record from two place searches | 0 | 0 | 0 |
| GBIF copy of an iNaturalist record | 80 | 11 | 1,140 |
| Same GBIF observer, same day, within 100 m | 0 | 0 | 714 |
| Same iNaturalist user, same day, within 100 m | 16 | 1 | 89 |

For the GBIF rule, the Austrian Mycological Society names itself as the observer instead of
the person. That rule therefore also merges finds by different people at the same spot
on the same day. For a model that works per place and day, those are one event anyway.

## Records removed by the filters

Filters run in this order on records that are not duplicates. Each record counts once,
at the first filter it fails. Full numbers are in `reports/p1_dropped.csv`.

| Filter | Home | Pistoia | Comparison |
|---|---:|---:|---:|
| Not a mushroom seen in the field, such as a soil DNA sample | 28 | 0 | 10 |
| Date missing or only month or year | 5 | 1 | 336 |
| Date before 1990 or in the future | 0 | 0 | 767 |
| Blurred or hidden location | 21 | 0 | 5,230 |
| Point outside its area or flagged as wrong by GBIF | 0 | 0 | 2 |
| Position error above 1 km | 20 | 2 | 172 |
| Species not confirmed by the iNaturalist community | 19 | 2 | 166 |

Two findings changed the counts:

- **Soil samples at home.** 28 home records come from a GBIF dataset called Global soil
  organisms. They are DNA from soil taken at one spot on 9 September 2019, not porcini
  that someone saw.
- **The Swiss databank.** 5,088 of the blurred records come from the Swiss National Fungi
  Databank. Under a national agreement it publishes only the 5 km square of each find.
  These records cannot be used at 500 m, but they could support a check at 5 km.

## Finds that passed

| | Home | Pistoia | Comparison |
|---|---:|---:|---:|
| Records downloaded | 274 | 27 | 13,373 |
| After duplicates | 178 | 15 | 11,430 |
| Reliable finds | 85 | 10 | 4,747 |
| Separate 500 m squares | 75 | | 2,500 |
| Separate square and day pairs | 81 | | 4,515 |
| Separate observers | 55 | | 961 |

- **Years.** At home, 76 of the 85 finds are from 2019 to 2026, and no year has more than
  24. In the comparison area, finds cover every year from 1990 to 2026, with 150 to 310 a
  year since 2019.
- **Seasons.** At home, 66 finds are from autumn and 18 from summer. In the comparison
  area, finds split almost evenly between summer and autumn.
- **Places.** At home, finds spread from the Apennine ridge north of Pistoia to southern
  Tuscany, with clusters around a few active observers. In the comparison area, most
  reliable finds are in Austria. Few Swiss finds pass, because the Swiss databank's
  rounded records fail the blur filter. See `reports/p1_map.png`.
- **Position error.** At home, 49 finds are within 100 m, 21 within 1 km and 15 unknown.
  In the comparison area, 716 are within 100 m, 398 within 1 km and 3,633 unknown. Most
  of the unknown ones are Austrian society records, which give no position error. This
  does not matter for weather, which changes over kilometres, not metres. It only matters
  for habitat details at 500 m, such as tree type or slope.
- **Sources.** At home, 84 of the 85 finds come from iNaturalist. In the comparison area,
  3,749 come from GBIF datasets other than iNaturalist and 998 from iNaturalist.

Counts by year, season, source, position error, blur, identification and licence, before
and after cleaning, are in `reports/p1_counts.csv`.

A blurred record keeps the point its source published in `published_latitude` and
`published_longitude`. That point is shifted or rounded, so the record never gets a
`latitude`, a 500 m square or a dot on the map. The test `tests/test_p1_observations.py`
checks this.

## Timing finds from blurred and rounded records

Issue #16. Weather changes over kilometres, so a find with a day and a rough area can
still show when porcini come up. The script now keeps records that fail only because
the position is blurred or the position error is above 1 km. Each one keeps its rough
point and gets a coarse square that shows how rough the point is:

- 10 km for a position error up to 5 km. This covers the Swiss databank records rounded
  to 5 km.
- 30 km for a blurred iNaturalist find or a position error from 5 to 30 km.

Records with a larger or unknown error are left out, and so are records that fail any
other filter. The table is `timing_finds.parquet` under `data/processed/p1_observations/`,
with columns described in `docs/data_formats.md`. Run record:
`reports/runs/p1_observations/20261011T075009Z-796984.json`. The run took 159 seconds.

| | Home | Pistoia | Comparison |
|---|---:|---:|---:|
| Reliable finds, from above | 85 | 10 | 4,747 |
| Timing finds | 34 | 2 | 5,347 |
| From iNaturalist | 34 | 2 | 362 |
| From GBIF datasets other than iNaturalist | 0 | 0 | 4,985 |
| Blurred, with a 30 km square | 16 | | 236 |
| Blurred, with a 10 km square | 0 | | 4,966 |
| Position error above 1 km | 18 | | 145 |
| Separate coarse squares | 26 | | 482 |
| Separate square and day pairs | 33 | | 4,344 |

- **Home.** The home area gains 34 timing finds, all from iNaturalist. 30 are from 2019
  or later. 23 are from autumn and 10 from summer. Seven more blurred or vague home
  records were left out because the community had not confirmed the species.
- **Comparison.** The comparison area more than doubles its usable finds. Almost all of
  the gain is the Swiss databank, whose rounded records now count with a 10 km square.
  This fills the gap in Switzerland noted above.
- Counts by year, season and source are in `reports/p1_counts.csv`, at the stage
  `timing`.

The home area gains fewer than 50 timing finds, which is the stop rule of issue #16.
Home now has 119 dated finds in total, still too few to learn timing from. Timing should
be learned in Switzerland and Austria and from P1c, issue #17, and the home finds used only to
check the result.

## Do finds sit near roads and paths

Each find and each random place gets its distance to the nearest road, and to the
nearest road or path, from OpenStreetMap. Distances stop at 1 km. The table compares the
reliable finds with 500 random places in the same area. The comparison area uses a
random sample of 500 of its finds. The range is the 95 percent uncertainty range from
redrawing the points 1,000 times.

| Area | Group | Typical distance to road or path | Share within 100 m of a road or path | Typical distance to a road |
|---|---|---|---|---|
| Home | Finds | 36 m, range 24 to 57 | 73%, range 64 to 82 | 189 m, range 101 to 281 |
| Home | Random places | 83 m, range 71 to 94 | 57%, range 53 to 61 | 228 m, range 179 to 270 |
| Comparison | Finds | 38 m, range 32 to 41 | 84%, range 81 to 87 | 276 m, range 234 to 311 |
| Comparison | Random places | 64 m, range 57 to 72 | 66%, range 61 to 70 | 288 m, range 245 to 384 |

Finds sit closer to paths and tracks than random places do, in both areas, and the
ranges do not overlap. For roads alone, the ranges overlap, so finds are not clearly
closer to roads. People find and record porcini along the paths they walk. A model must
not read "no record far from a path" as "no porcini there".

Limits of this check:

- **Where the random places fall.** They are spread over the whole area, including
  towns, fields and lakes, where porcini cannot grow. A fairer test draws random places
  inside forest only. That needs the forest map from P2.
- **Position error.** Many finds have a position error of tens or hundreds of metres,
  which is close to the distances measured.

## Problems met on the way

- **Overpass.** The first version asked the public Overpass server for roads near each
  point. That server limits heavy use and was overloaded, and every query failed for
  more than 20 minutes. The script now reads Geofabrik extracts on the laptop. They are about
  2.4 GB to download once, and reading them takes about 3 minutes.
- **Sleep and the time limit.** The runner's 30 minute limit does not count time while
  the laptop sleeps. A run that started at 18:45 was still alive at 19:30. Long runs
  should use `caffeinate -i` on macOS. Fixing the runner belongs to the P0 setup, not
  to this issue.

## Conclusion

The home area has too few reliable finds to train or test a weather model:

- 85 finds in total, 81 distinct square and day pairs.
- Most from the last eight years, from 55 people.

Pistoia alone has 10. Widening to the rest of central Italy would not change this, as GBIF
has about 1,100 records of the four species for all of Italy.

Switzerland and Austria have 4,747 reliable finds:

- 2,500 squares and 37 years.
- Enough to test whether weather explains when porcini appear.

Most Swiss data is rounded to 5 km, so the comparison finds come mainly from Austria.
That is fine for weather. Habitat checks at 500 m should use the finds with a stated
position error.

Recommendations:

- Use Switzerland and Austria to test the weather signal in P3 and P4. Use the 85 home
  finds only to check whether a model trained there also ranks Tuscan finds well.
- Repeat the road and path check with random places inside forest once P2 has a forest
  map.
- For roads or habitat for every square, read the Geofabrik extracts already
  downloaded instead of a shared online server.
