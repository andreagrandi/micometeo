# Test rules for P4

Issue #8. These rules say how issue #9 will decide whether weather and habitat
point to porcini finds better than simple guesses, assumption A5. They were
written and committed before any prediction was scored. A change after that goes
in `docs/decisions.md` with the date and the reason, and the report of issue #9
lists it.

The split and the comparison points are built by
`uv run micometeo run p4_test_rules`, from `experiments/p4_test_rules/`. The
output goes to `data/processed/p4_test_rules/<run_id>/` and stays out of Git.
The same seed and the same P1 run give the same files.

## What the data can and cannot say

The finds only record where someone found porcini. Nobody records where they
looked and found nothing. A place with no find may have had porcini that nobody
saw. For that reason:

- Results are reported as rankings: how high a find ranks among other places on
  the same day.
- Results are never reported as a percentage of correct yes or no answers, and
  never as a chance that porcini grow at a place.

## Which finds count

The finds are the reliable finds of P1, issue #3, from
`data/processed/p1_observations/20261011T075009Z-796984/finds.parquet`. A
reliable find has a day, a species confirmed by the iNaturalist community or
recorded by a GBIF dataset, a position error of at most 1 km, and a date from
1990 on. P1 removed duplicates before this step.

The timing finds of issue #16 are left out. Their position is only known to 10
or 30 km, so they cannot be ranked against 500 m squares. They can still serve a
separate check of season timing, which does not count toward A5.

## One test case

One test case is one 500 m square on one day with at least one reliable find.
Several finds in the same square on the same day are one case. Its ID is the
square ID and the day, such as `500m_E4465500_N2301000_2016-10-01`.

A prediction for a case may only use data that existed on the morning of that
day. Weather values stop at the day before. Habitat values come from maps that
do not depend on the finds.

## Areas kept aside

The comparison area, Switzerland and Austria, is cut into blocks of 100 km by
100 km in the 500 m grid's coordinates, EPSG:3035. Each block that holds at
least one case gets a group, tuning, test or final. The script shuffles the
blocks with seed 42 and fills the tuning group up to 60 percent of the cases,
then the test group up to 80 percent, and puts the rest in the final group.

The blocks are large so that finds close to each other do not end up on both
sides:

- Rain in the reconstructed past weather has a real level of detail of about
  25 km, see `reports/p3_weather.md`. A block is four times that wide.
- A tuning case within 25 km of a test or final block is left out of every set.
  So no tuning find shares a weather cell with a find kept aside.
- Finds of one active observer tend to sit in one valley or around one town.
  Those clusters stay inside one block, so the observer's habits do not help a
  model score well on a block it never saw.

## Years kept aside

- Tuning years: 1990 to 2021.
- Test years: 2022 to 2024.
- Final years: 2025 and 2026.

Porcini seasons end before winter, so a season never runs across two sets.
Forecasts published in the past exist from March 2024, see issue #7. So the
7-day forecast test has 2024 in the test set and 2025 to 2026 in the final set.

### Only cases from 2017 on are scored

Decision D6 of 11 October 2026, before any prediction was scored. Issue #9
scores only cases from 2017 on. Tuning uses 2017 to 2021, test 2022 to 2024 and
final 2025 and 2026. The split of blocks and the comparison points stay as the
script drew them. Cases before 2017 are not scored.

- P3 found that the weather values a real morning needs exist only from 2017.
  A test from 2017 uses the kind of weather the app could see.
- Weather for every comparison point comes from about 380 cells of 25 km. Each
  cell is one download, and ten years keep the download short.
- The test and final sets keep 737 and 656 cases, well above the 200 and 100
  below which A5 is INCONCLUSIVE.
- Tuning drops to 392 cases from 5 seasons. That is enough to set the
  thresholds of hand-written rules and to fit logistic regression, but not a
  more flexible model, see the end of "Success thresholds".

## Which set a case belongs to

The first rule that matches wins.

Comparison area:

1. Final, if the year is 2025 or later, or the block is in the final group.
2. Test, if the year is 2022 or later, or the block is in the test group.
3. Left out, marked `buffer`, if the square lies within 25 km of a test or
   final block.
4. Tuning, otherwise.

Home area, Tuscany and the Apennines:

- The home area has 85 finds, too few to tune anything, see
  `reports/p1_observations.md`. No home case is ever used for tuning.
- Home cases up to 2024 form the home test set. Home cases from 2025 form the
  home final set.
- The home sets check whether a model tuned on Switzerland and Austria also
  ranks Tuscan finds well.

The script checks before it writes anything that no find appears in two sets,
that no tuning case lies in or within 25 km of a test or final block, and that
no home case is in the tuning set. The test
`tests/test_p4_test_rules.py` checks the same rules. The script stops if a check
fails.

## Size of each set

From run
[20261011T082136Z-06759a](../reports/runs/p4_test_rules/20261011T082136Z-06759a.json),
which took 17 seconds once the forest map was saved. The full tables are
`reports/p4a_split_counts.csv` and `reports/p4a_point_counts.csv`.

26 blocks hold a comparison case. 16 are tuning blocks with 2,784 cases, 5
are test blocks with 1,274 cases and 5 are final blocks with 457 cases. Blocks
differ a lot in size, so the shares come out at 62, 28 and 10 percent instead
of 60, 20 and 20.

| Area | Set | Cases | Finds | Cases before 2022 | Cases 2022 to 2024 | Cases 2025 and later |
|---|---|---:|---:|---:|---:|---:|
| Comparison | Tuning | 1,319 | 1,358 | 1,319 | 0 | 0 |
| Comparison | Test | 1,504 | 1,596 | 1,041 | 463 | 0 |
| Comparison | Final | 772 | 854 | 189 | 189 | 394 |
| Comparison | Left out | 920 | 939 | 920 | 0 | 0 |
| Home | Home test | 70 | 73 | 25 | 45 | 0 |
| Home | Home final | 11 | 12 | 0 | 0 | 11 |

The 25 km gap costs 920 cases, about 4 in 10 of the old cases in tuning blocks.
That is the price of keeping tuning finds out of the weather cells of the finds
kept aside. The tuning set still has more than 1,000 cases.

Every case outside the left-out group has 100 forest points, 550,850 points in
all. Every comparison case and every home test case also has 50 known spots.
The 11 home final cases have none, because the set holds only 11 squares.

The forest map counts 2,361 of the 2,500 squares with a comparison find as
forest, and all 75 home squares. The rest lie at forest edges or come from
finds with a position error of a few hundred metres. They stay in as cases.

## Comparison points

Each case gets two kinds of comparison points. Both are on the same day as the
case, in the same area, and in the same block group. Home cases use the whole
home area as one group. A comparison point is never a square with a find on that
day. The script draws them with seed 42, in a fixed order of cases, so a new run
gives the same points.

1. Forest points. 100 random 500 m squares where forest covers at least 10
   percent of the square, the same rule as P2. Forest comes from the Copernicus
   forest type map of 2018 at 100 m pixels, the map P2 used. These points answer
   the question of the app: on this day, which forest squares in the area are
   most worth a visit. Only blocks that hold at least one case supply forest
   points. For a tuning case, forest squares within 25 km of a test or final
   block are skipped, by the same rule as the finds.
2. Known spots. Up to 50 squares that hold a case of the same set on another
   day. A case with fewer than 20 such squares gets no known spots and is left
   out of this score only. These points answer a narrower question: among
   places where people do find porcini, which ones produce on this day.

## Where people search

People do not search at random. P1 found that 84 percent of finds in the
comparison area lie within 100 m of a road or path, against 66 percent of
random places. Finds also cluster around active observers and towns. A model
can score well by learning where people walk, not where porcini grow.

The two kinds of comparison points deal with this in different ways:

- Forest points remove open land, towns and lakes, where nobody looks for
  porcini. They do not remove the pull of paths and towns. A good habitat score
  against forest points may partly measure where people walk.
- Known spots are places people already search and find porcini. Most of the
  difference in effort and habitat between a find and a known spot is gone, so
  what is left is mainly the day. Weather is the main thing that can rank them.

The report of issue #9 shows both scores side by side. A habitat signal that
appears with forest points and vanishes with known spots is expected. A weather
signal should appear with both.

## Scores

For each case, a prediction gives a value to the find's square and to each
comparison point. The rank position of the case is the share of comparison
points with a higher value, counting ties as half. A rank position of 0 means
the find's square came first.

Decision D9: when the find ties with other places, the top 10 and top 20
percent scores count the tie as a random tie break. A find tied with 40 percent
of the places, with none above, counts as half a hit for the top 20 percent.
Counting a tie as half the span would put it at 0.20, never inside. Models
with continuous values do not tie, so only the hand-written rules change.

The main scores, for each set and each kind of comparison point:

- Top 10 percent: the share of cases with a rank position below 0.10.
- Top 20 percent: the share of cases with a rank position below 0.20.

A random ranking puts 10 percent of cases in the top 10 percent and 20 percent
in the top 20 percent. The script of issue #9 also scores a real random ranking
with seed 42, as a check of the code.

Each score comes with a 95 percent uncertainty range. The range comes from
redrawing groups of cases with replacement 1,000 times, with seed 42. A group
is all cases in one 100 km block and one year. Cases in a group share weather
and often one observer, so they are not drawn one by one. The difference
between two predictions is computed on the same redrawn groups.

The simple guesses are:

- A random ranking.
- Where it rained most in the 7 days before the case's day. The window is the 7
  days that end the day before, from reconstructed past weather, fixed before
  scoring.
- Best habitat only, if the P2 values support it.

## Success thresholds

The thresholds use the top 20 percent score with forest points in the
comparison area. Top 10 percent and known spots are reported next to it.

- S1, better than random: the top 20 percent score is at least 30 percent, and
  the lower end of its range is above 20 percent.
- S2, better than the rain guess: the score is at least 5 points higher than
  the rain guess's score, and the lower end of the range of the difference is
  above 0.
- S3, weather adds to habitat: the model with weather and habitat beats the
  model with habitat alone by at least 5 points, and the lower end of the range
  of the difference is above 0. The same test with known spots compares weather
  alone with a random ranking, using S1.

Status of A5:

- VALIDATED: on the comparison test set, the chosen model with weather and
  habitat meets S1 and S2, and on the final set it meets S1 and S2 again.
- REJECTED: the test is valid and no model meets S1 and S2 on the comparison
  test set.
- INCONCLUSIVE: the comparison test set has fewer than 200 cases, the final set
  has fewer than 100 cases, or a model meets S1 and S2 on the test set but not
  on the final set.

The report also says whether S3 holds, so it is clear whether weather adds
anything on top of habitat. The home test and home final scores are reported
with their ranges. They do not change the status of A5. With about 40 cases a
set, they show at most whether a model clearly fails at home.

Issue #9 does not score gradient-boosted trees, LightGBM, a more flexible
machine learning model. Decision D6 replaced the earlier conditions. With 392
tuning cases from 5 seasons, such a model would learn the quirks of those
seasons rather than a rule that holds in other years. Hand-written rules and
logistic regression fit the size of the data.

## Tuning

- Model fitting, thresholds of hand-written rules, the choice of weather
  windows and any other setting use the tuning set only. To check a setting
  inside the tuning set, leave out one 100 km block at a time.
- The test set compares the approaches. Its scores may be looked at more than
  once, but its finds are never used to fit or adjust a model. Each change of a
  setting after a test score has been seen goes in `docs/decisions.md`.
- Before the final run, the report of issue #9 names the one model that will be
  scored on the final set.

## Timing test

Decision D7 of 11 October 2026, added after the first test scores and before
any timing score was seen. The comparison above ranks places on one day. Every
find day is already a day after rain in most of the region, and rain comes in
cells of 25 km, so that comparison cannot show whether rain decides when
porcini appear. The timing test asks that question.

- For each case, the comparison days are every other day from 45 days before to
  45 days after the case's day, in the same square. A day with a find in the
  same square is never a comparison day. Days without complete weather are
  left out.
- The find day is ranked among those days, with the same rank position, top
  10 and top 20 percent scores and uncertainty ranges as above.
- Simple guesses: a random ranking, and a calendar guess that ranks a day
  higher the closer it is to the middle day of the year of tuning finds. Rain
  must beat the calendar, or it only shows the season.
- Weather predictions: rain of the last 7, 14 and 30 days on their own, the
  hand-written weather rules, and logistic regression on the six weather
  values, fitted on tuning find days against their comparison days.
- T1: the best weather prediction, chosen on the tuning set, has a top 20
  percent score of at least 30 percent on the test set, with the lower end of
  its range above 20 percent.
- T2: it beats the calendar guess by at least 5 points, with the lower end of
  the range of the difference above 0.

People also search more after rain, so a timing signal is partly a signal of
when people go out. The report says so next to the result.

## The final set

The final set is the comparison final set plus the home final set: every case
from 2025 and 2026, and every case in a final block.

- It is used once, after all tuning has finished and the model is named.
- The final run uses settings committed to Git. Its run record holds the commit.
- Its run record and its scores are committed whatever they show.
- If a bug is found after the final run, the fix and a second run go in
  `docs/decisions.md`. The report shows both results and labels the first one
  as the first use.

## If the data is too thin

- If the comparison test set has fewer than 200 cases or the final set has
  fewer than 100, A5 is INCONCLUSIVE and issue #9 reports the scores as a
  smaller test.
- The home sets are always a smaller test, as said above.
- If the data does not allow a fair test, that is the result. It is not a
  reason to try more complex models.
