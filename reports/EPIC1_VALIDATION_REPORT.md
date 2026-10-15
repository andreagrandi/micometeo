# Epic 1 validation report

Issue #13. Written on 11 October 2026 from the experiments P1 to P6 on
`master` at commit b7971ca.

## 1. Decision

PIVOT.

SporaMeteo can be built as a free web map that shows where weather and habitat
match published knowledge about porcini, and which weeks look good. Epic 1
found no data that says where someone will find porcini or how likely a find
is.

Reasons:

- Weather points to when porcini appear. In a German beech forest where every
  porcini day was counted for 10 years, 95 percent of porcini days had at least
  30 mm of rain from 30 to 8 days before, against 78 percent of other days.
  Rain over the last 30 days put 39 percent of porcini days in the top fifth of
  days, against 16 percent for a random ranking. In Switzerland and Austria
  the same rain put 41 percent of find days in the top fifth of the 90 days
  around them on the final set of 2025 and 2026, against 21 percent for a
  random ranking.
- Nothing tested points to where inside a valley. Rain comes in cells of 25 km.
  The only model that ranked places better than the simple guesses learned
  flat ground near paths, which is where people walk, and it failed on the
  final set.
- Tuscany and the Apennines have 85 reliable finds, too few to learn from or
  to test a model at home. Tests ran in Switzerland and Austria, with 4,747
  reliable finds, and at the Bielefeld forest.
- The weather rules from published studies beat a random ranking on every set
  never used to set them, at 26 to 28 percent of finds in the top fifth
  against 20 to 21. They stay below the 30 percent bar fixed before the test.
- Serving scores to a phone is cheap. A full screen of squares is 7.4 KB and
  the API uses about 40 MB of memory.
- No data licence stops a free app with no ads and no subscriptions. A server
  with backups costs 7.20 to 9.74 euro a month with VAT among the servers that
  could be ordered on 11 October 2026.

The pivot changes the ambition, not the species or the area. The app shows
conditions for porcini in Tuscany and the Apennines, based on rules from
published studies.

After reading this report, the project owner made three decisions, D12 to
D14 in `docs/decisions.md`:

- The app is web first, works on a phone and has a full desktop layout.
- The map shows a percentage for each square. Epic 1 measured no such
  percentage, so the work that builds it must say what it measures and check
  it on data that records days without porcini.
- The background map uses OpenStreetMap data.

Why not GO: the PRD asks for a useful gain over the simple guesses. The gain
exists for timing and is missing for places, and no test used the weather
that the app will really have on a morning, see section 4.

Why not NO-GO: the data, the licences and the costs all allow a conditions
map, and the rain rule held in a forest where empty days were recorded too.

The backup and server move test, issue #12, was left out of Epic 1 by the
project owner. The decision does not depend on it.

## 2. Assumptions

The same status is in `docs/decisions.md`.

| ID | Assumption | Status | Evidence | Limits | Next step |
|---|---|---|---|---|---|
| A1 | Enough trustworthy, dated, located porcini finds exist. | INCONCLUSIVE | [P1 report](p1_observations.md), [P1c report](p1c_flush_signs.md) | Enough in Switzerland and Austria, 4,747 reliable finds. Not enough at home, 85, and Pistoia has 10. Finds cluster within 100 m of paths: 73 percent at home against 57 for random places. | Test rules away from home. Use Tuscan finds and Google searches for "porcini" only to check season timing. |
| A2 | Tree and habitat data help at regional level. | VALIDATED | [P2 report](p2_habitat.md) | One sample area of 11 by 10 km. The Tuscany forest inventory dates from 1985 to 1993 and stops at the border. SoilGrids soil is too uncertain to separate squares. | Build the grid for the whole home area. Find an Emilia-Romagna forest and rock map. |
| A3 | Past weather is enough to judge conditions today. | VALIDATED | [P3 report](p3_weather.md) | The weather of a real morning exists only from 2017. The last 6 days come from a weather model, and models disagree by up to 100 mm on recent rain. Rain detail is about 25 km. | Score the rules with the weather of a real morning, see section 4. |
| A4 | A forecast 7 days ahead can be tested without knowing the outcome. | VALIDATED | [P3 report, forecasts published in the past](p3_weather.md#forecasts-published-in-the-past) | Possible only for finds from 14 March 2024 on, 765 finds, 36 in Tuscany. Rain on a single day 6 to 7 days ahead is a weak match for the rain that fell. | Score the rules with forecasts published in the past on finds of 2024 to 2026. |
| A5 | Weather and habitat signals beat a simple guess. | INCONCLUSIVE | [P4b report](p4_benchmark.md) | The model that passed on the test set failed on the final set. Weather shows when, not where. Rules from published studies stay above random but below the 30 percent bar. | Build the conditions map on published rules, not on a model fitted to finds. |
| A6 | Precomputed results can be served efficiently on a phone. | VALIDATED | [P5 report](p5_phone_map.md) | Scores were made up. The prototype page froze on an iPhone 15 with Safari, while the API answered every request. One phone was tried. | Try a lighter background map on the iPhone. |
| A7 | Licences and running costs allow a free small service. | VALIDATED | [P6 report](p6_cost_licence_portability.md), [licence table](p6_licences.csv) | Holds only while the app has no ads and no subscriptions. GADM outlines must be replaced. Cheaper servers were sold out. Backup and server move were not tested. | Ask Open-Meteo in writing whether the app counts as non-commercial. |

## 3. Evidence list

### Git commit and machine

Every report and run record named here is on `master` at commit b7971ca.
Each run record stores the commit it ran from:

| Experiment | Run record | Commit of the run | Run time | Peak memory |
|---|---|---|---|---|
| P1 finds | [20261010T181005Z-696b43](runs/p1_observations/20261010T181005Z-696b43.json) | 54361eb | 154 s | |
| P1 timing finds | [20261011T075009Z-796984](runs/p1_observations/20261011T075009Z-796984.json) | 0709671 | 159 s | |
| P1c Google searches | [20261011T080539Z-692d26](runs/p1c_flush_signs/20261011T080539Z-692d26.json) | ec1bdcf | 1 s | |
| P2 habitat, from scratch | [20261010T184316Z-3b2c48](runs/p2_habitat/20261010T184316Z-3b2c48.json) | 81e9642 | 399 s | |
| P2 habitat, final | [20261010T192011Z-c4f95b](runs/p2_habitat/20261010T192011Z-c4f95b.json) | 977a076 | 13 s | |
| P3a past weather | [20261010T195440Z-a38289](runs/p3_weather/20261010T195440Z-a38289.json) | 4a2611c | 578 s | |
| P3b past forecasts | [20261011T070425Z-d61547](runs/p3b_forecasts/20261011T070425Z-d61547.json) | 4580750 | 744 s | |
| P4a test rules | [20261011T082136Z-06759a](runs/p4_test_rules/20261011T082136Z-06759a.json) | b221ab6 | 16 s | |
| P4b with the final set | [20261011T105039Z-5950ac](runs/p4b_benchmark/20261011T105039Z-5950ac.json) | d82bb09 | 29 s | 1.2 GB |
| P4b Bielefeld | [20261011T101125Z-c3dfaf](runs/p4b_bielefeld/20261011T101125Z-c3dfaf.json) | ae9c20d | 83 s | 0.2 GB |
| P5 phone map | [20261011T111704Z-e8170c](runs/p5_phone_map/20261011T111704Z-e8170c.json) | f197129 | under 1 s | 45 MB |
| P6 costs | [20261011T142322Z-4fe9ea](runs/p6_costs/20261011T142322Z-4fe9ea.json) | 1dd5c22 | 2 s | 138 MB |

Every run record marks uncommitted changes. In each case these were run
records of earlier runs lying untracked in `reports/runs/`. All settings were
committed. Runs before P4b did not record peak memory.

All runs used one laptop: Apple arm64, 10 processor cores, 32 GB of memory,
macOS 26.5. No GPU. Every run listed stayed under the 30 minute limit.

### Commands

Install with `uv sync`. Each command rebuilds the tables and figures of its
report from the saved downloads, or downloads them again when they are
missing.

| Result | Command | Needs |
|---|---|---|
| P1 finds, roads and paths, timing finds | `uv run sporameteo run p1_observations` | GBIF download `0019331-260928105237408`, Geofabrik extracts of about 2.4 GB |
| P1c search timing | `uv run sporameteo run p1c_flush_signs` | Trends CSV files saved in `experiments/p1c_flush_signs/trends_exports/` |
| P2 habitat grid | `uv run sporameteo run p2_habitat` | Nothing, all layers are public downloads |
| P3a past weather | `uv run sporameteo run p3_weather` | Nothing, Open-Meteo needs no login |
| P3b past forecasts | `uv run sporameteo run p3b_forecasts` | Nothing |
| P4a test cases and split | `uv run sporameteo run p4_test_rules` | P1 outputs and GADM files, and the public Copernicus forest map |
| P4b scores | `uv run sporameteo run p4b_benchmark` | P4a outputs and a free Copernicus Climate Data Store account. The first download of 380 weather cells takes about 50 minutes and resumes across runs |
| P4b Bielefeld counts | `uv run sporameteo run p4b_bielefeld` | Zenodo record 20591123 |
| P5 API sizes and memory | `uv run sporameteo run p5_phone_map` | Nothing |
| P6 sizes and requests | `uv run sporameteo run p6_costs` | Nothing, it downloads the GADM outlines |

The final set of P4b is locked again in `experiments/p4b_benchmark/config.toml`.
Scoring it a second time needs `score_final = true`, which the test rules
forbid.

### Sources

The full table, with URL, licence, use limits and the date checked for all 23
sources, is [p6_licences.csv](p6_licences.csv). The P2 layers with version,
download date and coordinate system are in
[data/p2_layers.csv](../data/p2_layers.csv).

| Source | Version or date | Licence | Used in |
|---|---|---|---|
| GBIF occurrence download | key `0019331-260928105237408`, [doi:10.15468/dl.gw48at](https://doi.org/10.15468/dl.gw48at) | per record: CC BY, CC BY-NC, CC0 | P1 |
| iNaturalist API | queried 10 October 2026 | per record, some with no licence | P1 |
| OpenStreetMap through Geofabrik | data of 8 October 2026 | ODbL 1.0 | P1 |
| GADM outlines | 4.1 | GADM licence, no redistribution | P1, P4a, P6 |
| Google Trends, Tuscany | 3 CSV exports downloaded 11 October 2026 | Google terms of service | P1c |
| Copernicus DEM | GLO-30 and GLO-90 | Copernicus WorldDEM licence | P2, P4b |
| Copernicus forest type | 2018 | Copernicus free and open data | P2, P4b |
| SoilGrids | 2.0 | CC BY 4.0 | P2 |
| Regione Toscana geology | 1:10,000 database, no version stated | CC BY | P2 |
| Inventario forestale della Toscana | survey 1985 to 1993, revised 2009 | CC BY-SA 4.0 | P2 |
| Open-Meteo Historical Weather, Forecast, Previous Runs, Single Runs, Historical Forecast | queried 10 and 11 October 2026 | CC BY 4.0, free plan non-commercial | P3a, P3b |
| ERA5 hourly time series, Copernicus Climate Data Store | 380 cells of 25 km, up to early October 2026 | CC BY 4.0 | P4b |
| Bielefeld daily porcini counts | Zenodo record 20591123 | CC BY 4.0 | P4b |
| MapLibre GL JS | 4.7.1 | BSD 3-Clause | P5 |
| OpenFreeMap | "liberty" style | free, ODbL map data | P5 |

## 4. Prediction comparison

### Three kinds of weather, kept apart

The PRD asks to keep three things apart. Epic 1 tested them separately, and
only one of them was scored against finds.

| Kind | What it uses | What Epic 1 showed | Scored against finds |
|---|---|---|---|
| Look back at past days | Reconstructed past weather, ERA5, for every day up to the day before. This is the weather that actually happened, known only later. | Complete 30-day totals for all 300 sampled finds, P3a. | Yes. Every P4b score below uses this kind. |
| Conditions today, based on the weather of the last 7 to 30 days | Reconstructed past weather up to 7 days before, and weather model values for the last 6 days, because reconstructed weather runs 5 to 6 days behind. | The data exists from 2017. Swapping the last 6 days changes a window's rain by a median of 4.5 mm and by 18.7 mm or more for 1 find in 10, P3a. | No. |
| Forecast up to 7 days ahead | Forecasts published before the assessment date, from the Open-Meteo Single Runs API. | Possible for finds from 14 March 2024. The 30-day rain total with 7 days of forecast in it agrees with the look back total at a correlation of 0.90, P3b. | No. |

So every score in this section shows what the weather that actually happened
says about porcini. The app will have less: model values for the last 6 days
and forecasts for the days ahead. The 30-day rain signal should survive that
swap, because the swapped days are a small part of 30 days, but no test has
shown it.

### Test setup

The rules were written in [docs/test_rules.md](../docs/test_rules.md) before
any prediction was scored, decision D5.

- One test case is a 500 m square on one day with at least one reliable find.
- Comparison area only, Switzerland and Austria, cut into blocks of 100 km. A
  tuning case within 25 km of a block kept aside is dropped.
- Only cases from 2017 on, decision D6: tuning 2017 to 2021 with 392 cases,
  test 2022 to 2024 with 737, final 2025 and 2026 with 656. 63 Tuscan cases
  from 2017 to 2024 are scored on their own.
- The final set was scored once, at the end, after the models had been named.
- Two tests:
  - Place test: rank the find square against 100 random forest squares and up
    to 50 places where someone found porcini on another day, on the same day.
  - Timing test, decision D7: rank the find day against the other days from 45
    days before to 45 days after, in the same square.
- Score: the share of finds that fall in the top 20 percent. A random ranking
  gives about 20. Finds only show where someone looked, so only rankings are
  fair, not accuracy.
- Pass bars, fixed in advance: at least 30 percent with the lower end of the
  uncertainty range above 20, S1 and T1, and a clear gain over the rain
  guess, S2 and T2.
- Uncertainty ranges cover 95 percent and come from redrawing groups of one
  block and one year.

### Simple guesses and models

- Simple guesses: a random ranking, rain of the last 7 days, the most forest,
  and a calendar guess for the timing test.
- Rules from published studies, decision D8 and D10: at least 30 mm of rain
  from 30 to 8 days before, a week at least 1 degree cooler than the month, a
  14-day mean of 10 to 15 degrees, 15 June to 15 November, and altitude from
  200 to 2,000 m.
- Logistic regression, a simple statistical model that weighs each input,
  fitted on the tuning set with weather alone, habitat alone and both.
- Gradient-boosted trees were not tried. 392 tuning cases from 5 seasons are
  too few, decision D6.

### Scores

Test set, 2022 to 2024, share of finds in the top 20 percent:

| Prediction | Place, forest squares | Place, known spots | Timing |
|---|---:|---:|---:|
| Random ranking | 20%, 18 to 24 | 21%, 18 to 24 | 21%, 18 to 24 |
| Rain of the last 7 days | 19%, 15 to 26 | 23%, 18 to 29 | 21%, 18 to 24 |
| Rain of the last 30 days | | | 30%, 24 to 35 |
| Rules, weather | 21%, 18 to 25 | 24%, 20 to 28 | 25%, 22 to 29 |
| Logistic regression, weather | 29%, 20 to 38 | 22%, 14 to 31 | 25%, 20 to 29 |
| Logistic regression, habitat | 37%, 29 to 44 | 24%, 18 to 30 | |
| Logistic regression, both | 37%, 29 to 44 | 25%, 19 to 31 | |

Final set, 2025 and 2026, scored once:

| Prediction | Place, forest squares | Place, known spots | Timing |
|---|---:|---:|---:|
| Random ranking | 20%, 16 to 22 | 21%, 19 to 24 | 21%, 17 to 23 |
| Logistic regression, both, named in advance | 24%, 19 to 28 | 23%, 19 to 27 | |
| Rain of the last 14 days, named in advance | | | 25%, 21 to 29 |
| Rules, weather | 27%, 24 to 31 | 26%, 23 to 30 | 27%, 24 to 30 |
| Rules, weather and habitat | 28%, 25 to 31 | 26%, 23 to 30 | |
| Rain of the last 30 days | | | 41%, 36 to 46 |

Bielefeld forest, every porcini day counted, 2015 to 2024:

| Prediction | Porcini days in the top 20 percent of days |
|---|---:|
| Random ranking | 16%, 9 to 24 |
| Rain of the last 30 days | 39%, 22 to 54 |
| Rules, weather | 32%, 19 to 50 |

### What the scores mean

- Weather and habitat, compared: weather alone adds 0.1 points to habitat
  alone in the place test. Habitat learned from finds carries the place
  score, and that score fell from 37 to 24 percent on the final set.
- The habitat model's largest weight is on flat ground. P1 found that 84
  percent of comparison finds lie within 100 m of a road or path. Against
  known spots, where people already search, every prediction on the test set
  stays at 22 to 25 percent.
- Rain of the last 30 days is the strongest timing signal on every set, but it
  was not the choice named on the tuning set. It counts only as a pointer.
- 11 Tuscan final cases are too few to read. On the 63 Tuscan cases of 2017
  to 2024, the timing ranges are 19 to 33 points wide.

### Errors and changes made after seeing scores

- The first run left out every known spot because two scripts named them
  differently. The run now stops on an unknown name.
- A tie between a find and many places first counted as half the span, so a
  rule could score 0 even when right. Ties now count as a random tie break,
  decision D9.
- The first habitat rule took its altitude band from tuning finds. It was
  replaced by rules from published studies, decisions D8 and D10.
- These changes came after test scores had been seen, and each is logged with
  its reason in `docs/decisions.md`. The final set was scored after all of
  them.

### How where people search shapes the data

- Finds sit near paths: 73 percent within 100 m of a road or path at home and
  84 percent in the comparison area, against 57 and 66 percent for random
  places.
- Tuning finds lie lower than random forest squares, at a median of 687 m
  against 941 m.
- Searches for "porcini" in Tuscany peak within 14 days of the middle find
  date in 5 of 7 years. People search, and record finds, when they expect a
  good season. Part of the timing signal is therefore when people go out.
- The Bielefeld counts record empty days, so they are free of this bias. The
  rain rule held there, on 155 porcini days in one forest.

### Run time

The P4b scoring run takes 22 to 29 seconds and 1.2 GB of memory once the
weather is saved. The first ERA5 download of 380 cells takes about 50 minutes,
3 requests at a time. The P6 run scored one day of the whole home area with
the published rules in 0.03 seconds.

## 5. Hosting and costs

All numbers come from the [P6 report](p6_cost_licence_portability.md), which
uses measurements from P2, P3b and P5.

### Memory and disk

| Item | Value | Measured or estimated |
|---|---|---|
| 500 m squares in the home area | 112,814 | measured, P6 |
| API memory | 35 to 42 MB | measured, P5 |
| Peak memory of a daily scoring run | 146 MB | measured, P6 |
| Scores for one day | 0.3 MB | measured, P6, made-up scores |
| Habitat grid of the home area | about 9 MB | estimated from P2 |
| Weather answers, one year | about 2.1 GB | estimated from P3b |
| Operating system, database and web server | about 0.6 GB of memory, about 3 GB of disk | estimated, typical values |

A server with 2 GB of memory and 20 GB of disk is enough. The scenarios below
use 4 GB and 40 GB or more, to leave room for other projects.

### Daily work and requests

- The daily work is the weather download: about 1,036 Open-Meteo calls for 392
  cells of 9 km, about 7 minutes. Scoring takes under a second.
- At 100 active users the API gets about 2,400 requests a day, 72,000 a month,
  and sends under 1 GB a month. Users do not change the server size or cost
  between 10 and 100.

### API limits

- The free Open-Meteo plan allows 600 calls a minute, 5,000 an hour, 10,000 a
  day and 300,000 a month. The app needs about 1,036 a day. The free plan is
  for non-commercial use: no ads and no subscriptions.
- The app needs only the Forecast API. Past weather and forecasts published in
  the past were needed only for testing.
- The P5 page asks for squares only from zoom 11, and the API refuses requests
  over 4,000 squares.
- OpenFreeMap has no limit on map views and no uptime promise. The MapTiler
  free plan, at 5,000 map sessions a month, would run out at 100 users.

### Monthly costs

Prices checked on 11 October 2026, with 22 percent Italian VAT.

| Scenario | Per month | Could be ordered |
|---|---|---|
| Netcup VPS 500, 24-month contract, Backblaze B2 free backup | 7.20 euro | Yes |
| Netcup VPS 500, 12-month contract | 8.47 euro | Yes |
| Netcup VPS 500, month by month | 9.74 euro | Yes |
| OVH VPS-1, 12-month contract | 4.65 euro | No, sold out in Europe |
| Hetzner CX23 with Hetzner backups | 8.65 euro | No, marked unavailable |

Only the 24-month Netcup contract is inside the provisional target of 5 to 8
euro. Doubling memory to 8 GB costs 3.66 to 7.35 euro more a month.

Left out of these figures:

- the domain
- an Open-Meteo paid plan, 29 euro a month for Standard, if the app turns
  commercial
- running our own Open-Meteo server, not measured
- our own background map if OpenFreeMap stops
- Cloudflare or another service in front of the server
- email, legal advice and the time to run the service
- the one-time habitat build for the whole area, not measured
- future price rises. Hetzner raised prices twice in 2026

### Licence conditions for the app

- No ads and no subscriptions, to stay on the free Open-Meteo plan.
- Replace GADM outlines with ISTAT or OpenStreetMap borders.
- Keep finds and their photos out of the app.
- Share anything published from the Tuscany forest inventory under CC BY-SA
  4.0.
- Show the credit lines for Copernicus, ERA5, Open-Meteo, OpenStreetMap and
  OpenFreeMap.

## 6. Open risks

- No test used the weather the app will really have. All scores use weather
  that actually happened. Conditions today use weather model values for the
  last 6 days, which can be 100 mm off, and forecasts beyond 5 days are a weak
  match for the rain that fell on a single day.
- No test was run in Tuscany with enough finds. The rules were checked in
  Switzerland, Austria and one German forest. Whether they hold in the
  Apennines is not known, and 85 home finds cannot tell.
- The rules beat a random ranking but missed the bar set in advance. At
  Bielefeld 78 percent of days without porcini met the rain rule, so good
  conditions will often come with no porcini.
- Nothing tested can rank places inside a 25 km weather cell. A habitat layer
  can say beech or chestnut wood, but no data can check whether one patch is
  better than the next.
- The timing signal is partly a signal of when people go out. Only the
  Bielefeld counts are free of that, and they cover one forest.
- The Tuscany forest inventory is 33 to 41 years old. Pastures since then have
  become woods.
- The home area runs into Emilia-Romagna, where the Tuscan forest and rock
  maps stop.
- The free Open-Meteo plan depends on how Open-Meteo reads non-commercial.
  Donations, a VAT number or paid links are not covered by its terms.
- Cheaper servers were sold out, and prices rose twice in 2026.
- The prototype page froze on an iPhone 15 with Safari. The cause is not
  known.
- Backup, restore and moving servers were not tested.
- Changes to rules, thresholds and the timing test were made after test
  scores had been seen. They are logged, and the final set was scored once,
  but the test scores are less clean than the final ones.

## 7. What to build next

Only capabilities that Epic 1 tested. No tickets are created by this report.

- A daily job that downloads weather for the home area from the Open-Meteo
  Forecast API, with the last 30 days from `past_days` and the next 7 days in
  the same request, about 1,036 calls a day.
- Scoring of every 500 m square with the rules from published studies,
  decisions D8 and D10, showing which rules each square meets and the
  percentage of decision D13.
- A habitat layer from the Copernicus forest map, the Copernicus elevation map
  and the Tuscany forest inventory, built once on a laptop.
- The API of P5 with real scores, and a web map with a phone layout and a
  full desktop layout, decision D12, on an OpenStreetMap background, decision
  D14. Each square shows the labels "conditions" or "forecast", reliability
  by days ahead, and credit lines.

Checks to run before the app shows any of this to users:

- Check the percentage of D13 on data that records days without porcini,
  such as the Bielefeld counts, before showing it.
- Score the rules with the weather of a real morning, for finds from 2017,
  and with forecasts published in the past, for finds from 14 March 2024.
- Compare the season timing in Tuscany with the Google search peaks of past
  years.
- Fix or work around the iPhone freeze, starting with a lighter background map.
- Ask Open-Meteo in writing whether the app counts as non-commercial.
