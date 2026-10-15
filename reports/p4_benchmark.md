# P4b weather and habitat against simple guesses

Issue #9. Test rules in `docs/test_rules.md`, changes D6 to D10 in
`docs/decisions.md`.

## Question

Do weather and habitat point to porcini better than simple guesses?

## Answer

Weather points to when porcini appear. Habitat as we can map it today does
not yet point to where.

- Rain in the 2 to 4 weeks before a day is the clearest signal. In a German
  beech forest counted day by day for 10 years, 95 percent of porcini days had
  at least 30 mm of rain from 30 to 8 days before, against 78 percent of days
  without porcini. Rain over the last 30 days put 39 percent of porcini days in
  the top fifth of days, against 16 percent for a random ranking.
- In Switzerland and Austria the same rain over 30 days put 30 percent of find
  days in the top fifth of the 90 days around them, against 21 percent for a
  random ranking.
- Rain of the last 7 days alone shows nothing. It is too recent.
- Weather cannot pick one place over another inside a valley. The rain data
  comes in cells of 25 km.
- The only model that passed the place test learned habitat from the finds.
  Its strongest input is flat ground, where roads and paths run. It most
  likely learned where people walk, not where porcini grow.
- On the final set of 2025 and 2026, scored once at the end, that model fell
  to 24 percent and failed. The weather rules from published studies reached
  27 percent, and rain of the last 30 days put 41 percent of find days in the
  top fifth.

A5 is INCONCLUSIVE. See the last section.

## Data and split

| Item | Value |
|---|---|
| Finds | P1 reliable finds, from 2017 on, decision D6 |
| Test cases | 1,192: tuning 2017 to 2021 with 392, test 2022 to 2024 with 737, Tuscany 2017 to 2024 with 63 |
| Final cases | 667 from 2025 and 2026, scored once at the end |
| Comparison places | 100 random forest squares and up to 50 known spots per case, drawn by P4a |
| Weather | ERA5 reconstructed past weather, hourly, 380 cells of 25 km, summed into Italian days |
| Habitat | Forest share and broadleaf share from the Copernicus 2018 forest map at 100 m, altitude and slope from the Copernicus 90 m elevation map |
| Dropped | 20 cases and 4,810 places without complete weather or habitat |

Temperature from a 25 km cell is moved to the height of each square at 6.5
degrees per 1,000 m, using the ERA5 ground height of the cell, decision D10.

## Rules from published knowledge

The user decided that the rules must follow published studies, because the
finds only show where people looked. Each threshold and its source is in
`experiments/p4b_benchmark/config.toml`.

| Rule | Source |
|---|---|
| At least 30 mm of rain from 30 to 8 days before | Regione Piemonte, "Funghi & tartufi risorse del bosco", sheet for *B. edulis*, 2019: at least 30 mm, porcini 12 to 15 days later |
| Last 7 days at least 1 degree cooler than the last 30 | Same sheets: fruiting needs a sudden cooling after warmth. The 1 degree is our choice |
| Mean of the last 14 days from 10 to 15 degrees | Brejon Lamartiniere and Hoffman 2026, bioRxiv 10.64898/2025.12.12.693895, not peer reviewed |
| From 15 June to 15 November | Piemonte sheets, and Buentgen and others 2013, Global Change Biology, Swiss fruiting about 12 days later after 1991 |
| Altitude from 200 to 2,000 m | Piemonte sheets for *B. aereus* and *B. edulis* |

Acid, well-drained soil matters too. P2 found the soil maps too uncertain to
use.

## Which place on one day

Share of finds in the top 10 and top 20 percent of places on the same day, test
set 2022 to 2024, 724 cases in 66 groups of one block and one year. The range
is the 95 percent uncertainty range.

| Prediction | Forest squares, top 10 | Forest squares, top 20 | Known spots, top 20 |
|---|---:|---:|---:|
| Random ranking | 10% | 20%, 18 to 24 | 21%, 18 to 24 |
| Rain of the last 7 days | 10% | 19%, 15 to 26 | 23%, 18 to 29 |
| Most forest | 15% | 28%, 24 to 32 | 22%, 19 to 25 |
| Rules, weather | 11% | 21%, 18 to 25 | 24%, 20 to 28 |
| Rules, weather and habitat | 11% | 22%, 18 to 26 | 23%, 20 to 27 |
| Logistic regression, weather | 16% | 29%, 20 to 38 | 22%, 14 to 31 |
| Logistic regression, habitat | 21% | 37%, 29 to 44 | 24%, 18 to 30 |
| Logistic regression, both | 20% | 37%, 29 to 44 | 25%, 19 to 31 |

Logistic regression is a simple statistical model that weighs each input,
fitted on the tuning set only.

Checks on the test set, forest squares:

- Logistic regression with both passes S1 with 37 percent, lower end 29, and
  S2 with 18 points over the rain guess, lower end 5.
- It fails S3. Weather adds 0.1 points to habitat alone.
- The rules fail S1 and S2.

Why the passing model does not show porcini:

- Its largest weight is on slope: the flatter, the higher. P1 found that 84
  percent of finds lie within 100 m of a road or path.
- Against known spots, where people already search, every prediction stays
  close to random: 22 to 25 percent.
- Tuning finds lie lower than random forest squares, at a median of 687 m
  against 941 m, and in thinner forest.
- Leaving out one 100 km block at a time inside the tuning set, weather alone
  scores 5 percent. What it learns in one area does not carry to another.

## Which day in one place

Decision D7. Each find day is ranked against every other day from 45 days
before to 45 days after in the same square. Days with another find there are
left out.

| Prediction | Test, top 20 | Tuscany, top 20 |
|---|---:|---:|
| Random ranking | 21%, 18 to 24 | 27%, 17 to 36 |
| Calendar guess | 11%, 6 to 17 | 6%, 2 to 13 |
| Rain of the last 7 days | 21%, 18 to 24 | 21%, 9 to 33 |
| Rain of the last 14 days | 25%, 21 to 29 | 27%, 12 to 42 |
| Rain of the last 30 days | 30%, 24 to 35 | 33%, 17 to 50 |
| Rules, weather | 25%, 22 to 29 | 32%, 21 to 45 |
| Logistic regression, weather | 25%, 20 to 29 | 41%, 29 to 55 |

- Rain of the last 14 days was chosen on the tuning set. On the test set it
  fails T1, 25 percent against 30, with a lower end of 21. It passes T2 against
  the calendar guess, but the calendar guess is worse than random, so T2 says
  little.
- Rain of the last 30 days scores 30 percent but was not the choice made on the
  tuning set, so it does not count.
- People also go out after a wet spell, so part of this signal is when people
  search.

## Days counted in one forest

Brejon Lamartiniere and Hoffman counted every porcino at a beech forest near
Bielefeld, Germany, 2 to 4 times a week from August to November, 2015 to 2024.
Their data is open on Zenodo, record 20591123, under CC BY 4.0. It records the
days with no porcini, so it is free of the bias of where people search.
`uv run sporameteo run p4b_bielefeld` scores our rules on it with our own ERA5
weather, from 5 August to 21 November of each year.

| Prediction | Porcini days in top 20 percent of days |
|---|---:|
| Random ranking | 16%, 9 to 24 |
| Rain of the last 30 days | 39%, 22 to 54 |
| Rules, weather | 32%, 19 to 50 |

| Rule | Porcini days that meet it | Other days that meet it |
|---|---:|---:|
| At least 30 mm from 30 to 8 days before | 95% | 78% |
| 14-day mean at least 10 degrees | 91% | 80% |
| 14-day mean at most 15 degrees | 65% | 52% |
| Last week 1 degree cooler than the month | 54% | 56% |

The rain rule comes from Piedmont and holds in a German forest. The
temperature band comes from this same dataset, so it passes partly by
construction. The cooling rule shows nothing here. There are 155 porcini days
in 10 years in one forest, so the ranges are wide.

## Failures and limits

- The first run left out every known spot because P4a and the scoring code
  named them differently. The run now stops on an unknown name.
- The first rules counted a tie as half the span. A rule gives few distinct
  values, so a find tied with many places always landed just outside the top
  20 percent and a rule could score 0. Ties now count as a random tie break,
  decision D9.
- The first habitat rule took its altitude band from tuning finds, which
  follows where people search. It was replaced, decision D8.
- Rules, thresholds and the timing test were changed after test scores had been
  seen. Each change is in `docs/decisions.md` with its reason. The final set was
  scored once, after all of them.
- Finds are blurred to about 1 km and record only where someone looked. No
  data here can check a prediction for a 50 m patch.
- Gradient-boosted trees were not scored, decision D6: 392 tuning cases from 5
  seasons are too few for a flexible model.

## Run time and memory

| Command | Run time | CPU | Peak memory |
|---|---:|---:|---:|
| `uv run sporameteo run p4b_benchmark`, weather saved | 22 to 24 s | 25 to 29 s | 1.2 GB |
| `uv run sporameteo run p4b_bielefeld`, first run with one ERA5 download | 84 s | 1.7 s | 0.2 GB |
| ERA5 download, 380 cells, once | about 50 minutes | | |

The ERA5 time series service of the Copernicus data store answers one place
per request and runs 3 requests at a time. A free ECMWF account is needed. The
weather files take 296 MB in `data/raw/p4b_weather/`.

Run records:

- [p4b_benchmark 20261011T105039Z-5950ac](runs/p4b_benchmark/20261011T105039Z-5950ac.json), the final run. The score tables in `reports/` come from it and hold the tuning, test and final rows.
- [p4b_benchmark 20261011T100307Z-c88cd0](runs/p4b_benchmark/20261011T100307Z-c88cd0.json), the same settings without the final set. Its tuning and test scores match the final run.
- [p4b_bielefeld 20261011T101125Z-c3dfaf](runs/p4b_bielefeld/20261011T101125Z-c3dfaf.json).
- Earlier runs of the same day, before D8, D9 and D10:
  [094728Z-384ff4](runs/p4b_benchmark/20261011T094728Z-384ff4.json),
  [095416Z-dd5902](runs/p4b_benchmark/20261011T095416Z-dd5902.json),
  [095557Z-cba314](runs/p4b_benchmark/20261011T095557Z-cba314.json).

Score tables: `reports/p4b_scores.csv`, `p4b_checks.csv`,
`p4b_timing_scores.csv`, `p4b_timing_checks.csv`, `p4b_coefficients.csv`,
`p4b_summary.csv`, `p4b_bielefeld_scores.csv` and `p4b_bielefeld_rules.csv`.

## Recommendation

Use hand-written rules from published studies, not machine learning on finds.

- Finds record where people look as much as where porcini grow. A model fitted
  on them learns paths and towns.
- Published rules on rain, temperature and season can be checked on data that
  records empty days, like the Bielefeld counts. The rain rule passed that
  check.
- For where, the app needs finer habitat maps, not more finds: the 10 m
  Copernicus forest maps, the 30 m elevation map for slope and the direction a
  slope faces, and tree species where a regional inventory names them. Weather
  can say which area and which weeks. Habitat can then point to patches of 30
  to 50 m inside that area. No data can check a percentage for such a patch, so
  the app should show where conditions match published knowledge, not a chance
  of finding porcini.

## Models named for the final set

Named on 11 October 2026, before the final set was scored:

- Place test: logistic regression with weather and habitat, the only model
  that met S1 and S2 on the test set. A5 status follows its S1 and S2 result.
- Timing test: rain of the last 14 days, chosen on the tuning set, for T1 and
  T2.
- The weather rules from published studies, the recommendation of this report,
  are reported next to them.

All other scores of the run are reported too, but none of them can change the
named models after the final scores are seen.

## Final set, first and only use

Run [20261011T105039Z-5950ac](runs/p4b_benchmark/20261011T105039Z-5950ac.json),
from commit d82bb09 with `score_final = true`. The record marks uncommitted
changes because two run records of earlier issues lay untracked in
`reports/runs/`. Every setting of this run was committed. 642 of the 656
comparison final cases were scored, in 64 groups. 14 cases from the last days
before 9 October 2026 had no complete weather. The 11 Tuscan final cases are
too few to read and are left out here.

Place test, top 20 percent:

| Prediction | Forest squares | Known spots |
|---|---:|---:|
| Random ranking | 20%, 16 to 22 | 21%, 19 to 24 |
| Logistic regression, both, named | 24%, 19 to 28 | 23%, 19 to 27 |
| Rules, weather | 27%, 24 to 31 | 26%, 23 to 30 |
| Rules, weather and habitat | 28%, 25 to 31 | 26%, 23 to 30 |

Timing test, top 20 percent:

| Prediction | Find days |
|---|---:|
| Random ranking | 21%, 17 to 23 |
| Rain of the last 14 days, named | 25%, 21 to 29 |
| Rules, weather | 27%, 24 to 30 |
| Rain of the last 30 days | 41%, 36 to 46 |

- The named place model fails S1 on the final set: 24 percent, lower end 19.
  What it learned from the 2017 to 2021 finds did not hold in 2025 and 2026.
- The named timing choice fails T1 again, 25 percent, and passes T2.
- The weather rules from published studies beat a random ranking in every
  final column, with lower ends of 23 to 24 percent. They miss the 30 percent
  bar of S1. Among known spots, where people already search, they reach 26
  percent against 21, the first weather signal there.
- Rain of the last 30 days puts 41 percent of find days in the top fifth. It
  was not the named choice, so it counts only as a pointer for later work.

## Status of A5

INCONCLUSIVE, by the rule written in advance: a model met S1 and S2 on the test
set but not on the final set.

- Logistic regression with weather and habitat met S1 and S2 on the test set
  and failed S1 on the final set. Its gain came from habitat that follows where
  people walk.
- Weather points to when. Rain of the last 30 days doubles the share of
  porcini days in the top fifth at Bielefeld, and puts 30 percent of find days
  in the top fifth in the test set and 41 percent in the final set, against
  about 20 for a random ranking.
- The weather rules from published studies stay above a random ranking on
  every set that was never used to set them, but below the 30 percent bar.
