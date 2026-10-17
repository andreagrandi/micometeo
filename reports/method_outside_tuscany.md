# The season and altitude rules outside Tuscany

Issue #156.

## Question

Do the temperature, frost and season rules of the estimate method give
sensible results outside Tuscany, in the Alps, the south, Sicily and Sardinia?

## Answer

In the Alps and the northern Apennines, yes. In the south and on the islands,
two rules give a wrong season.

- Val di Fiemme in the high Alps gets the clearest result. The estimate stays
  at 5 from December to April and rises above 50 on every day of August. It
  was 58 to 94 on the days of 26 of the 28 finds nearby in the last 12
  months, and 35 on the day of the other 2.
- A frozen Alpine January and a dry Sicilian August both give 5, as they
  should.
- The water store rule misses summer and early autumn finds in the southern
  mountains. At Sila, 6 finds in June, July and October 2026 fell on days with
  estimates of 5 to 9.
- The temperature rule lets mild, wet winters on Etna and in the Gennargentu
  reach 30 or more on 8 to 24 days a month from December to March. No find
  nearby was ever reported in those months, and the method's sources describe
  no winter season.

Recommendation: the method can be used as it is in the Alps and the northern
Apennines. For the south and the islands, change the water store rule first,
then the cold side of the temperature rule. Each change gets its own issue.

Run: `reports/runs/method_outside_tuscany/20261017T091921Z-2d0adb.json`.
Script: `experiments/method_outside_tuscany/run.py`.

## Which rules the current method has

`docs/forecast_method.md` describes version 2, with a frost rule. The code
runs version 4, `porcini-experimental-v4`, from `src/sporameteo/moisture_method.py`.
Version 4 has three parts:

- Temperature: the mean over the 7 days before the target day of a band score
  for each day's mean temperature, after the altitude correction of 0.65 °C
  per 100 m. The score is 0 at 0 °C, 0.1 at 5 °C, 0.4 at 8 °C, 1 from 12 to
  18 °C, 0.7 at 22 °C, 0.3 at 25 °C and 0 at 30 °C.
- Water store: it starts at 40 mm 30 days before the target day. Each day it
  keeps 95 percent of its water, gains the rain up to 25 mm and loses half of
  the evapotranspiration. It holds at most 80 mm. The factor is the store
  divided by 40, at most 1. The method takes the lower of the last day's
  factor and the mean factor of the last 7 days.
- Estimate: 5 plus 90 times the water factor times the temperature factor.

Version 4 has no frost rule, no season rule and no altitude limit. It shows
host trees but leaves them out of the estimate. Forest must cover at least a
tenth of a square. The frost section of `docs/forecast_method.md` therefore
does not describe the estimates the app publishes.

## How the check was done

For each place, the script took the weather cell with forest nearest to the
chosen point, in forest build `italy-forest-copernicus-2018-v1`. It read the
hourly weather of these 10 cells from the `ecmwf_ifs` files and made days with
the app's own code. Then it ran the app's summary and estimate code for every
forest square and every day from 17 October 2025 to 16 October 2026, as an
estimate for the same day. Nothing was written to the database.

| What was read | Requests | MB | Minutes |
|---|---|---|---|
| `ecmwf_ifs` files, 160 files, 17 September 2025 to 16 October 2026 | 3,262 | 11.3 | 4.5 |
| GBIF search, porcini in Italy | 4 | 7.2 | under 1 |
| iNaturalist, porcini in Italy | 9 | not counted | under 1 |

No Open-Meteo API call was made. The files held every hour for all 10 cells,
from 16 September 2025 at 22:00 UTC to 16 October 2026 at 22:00 UTC. No day
lacks weather, so the stop rule about missing months was not reached. A
smaller read-ahead of 4 KB instead of 32 KB kept the download at 11 MB.

GBIF and iNaturalist gave 2,796 records. 1,627 remain after removing 988 GBIF
copies of iNaturalist records, 100 repeated records within one source, 59
museum samples and 22 records without a full date. The duplicate rules are
those of P1. 405 of them have a blurred position and use the published one. A find
counts as nearby when it lies within 30 km of the weather cell centre.

## AC1: the places

| Place | Region | Altitude of the squares, m | Forest squares | Main trees | Finds nearby, all years | Finds nearby, last 12 months |
|---|---|---|---|---|---|---|
| Val di Fiemme | Trentino | 1,273 to 2,170, median 1,827 | 252 | spruce and fir 0.47, beech 0.10 | 257 | 28 |
| Campo dei Fiori | Lombardy | 237 to 1,141, median 491 | 282 | chestnut 0.32, beech 0.14 | 63 | 6 |
| Valle Gesso | Piedmont | 773 to 2,281, median 1,304 | 301 | beech 0.24, pines 0.10 | 36 | 3 |
| Borgotaro | Emilia-Romagna | 386 to 1,429, median 759 | 328 | oaks 0.36, chestnut 0.34 | 39 | 4 |
| Pescasseroli | Abruzzo | 1,127 to 1,887, median 1,494 | 357 | beech 0.41, oaks 0.24 | 0 | 0 |
| Pollino | Basilicata | 675 to 2,056, median 1,287 | 353 | beech 0.17, oaks 0.10 | 3 | 0 |
| Sila | Calabria | 1,150 to 1,742, median 1,381 | 273 | beech 0.20, chestnut 0.18 | 39 | 10 |
| Nebrodi | Sicily | 447 to 1,803, median 1,131 | 364 | beech 0.26, oaks 0.26 | 7 | 3 |
| Etna north | Sicily | 437 to 2,033, median 951 | 280 | oaks 0.11, chestnut 0.07 | 14 | 3 |
| Gennargentu | Sardinia | 639 to 1,080, median 870 | 366 | oaks 0.13 | 1 | 0 |

Altitudes come from terrain build `italy-terrain-glo30-2021-v2`. Tree shares
come from the JRC tree species maps and range from 0 to 1. The cells lie 1.1
to 6.5 km from the chosen points. 37 of the 328 Borgotaro squares are in
Tuscany, and 28 of the 353 Pollino squares are in Calabria. Every row is in
`reports/method_outside_tuscany_places.csv`.

The JRC maps fit Sicily and Sardinia poorly. They give oaks a share of only
0.11 on Etna and 0.13 in the Gennargentu, where oak woods are common. This
does not change any estimate, because version 4 leaves host trees out.

## AC2: months of high estimates, the season in the sources and the finds

A high month here has at least 10 days with a median estimate of 50 or more.
The sources of `docs/forecast_method.md` give the season only in general
terms. The Piemonte material describes autumn fruiting and spring fruiting for
some species, and *B. aereus* fruiting into December in southern oak woods.
The Bielefeld study followed one German beech forest from early August to the
first heavy frost. No source gives a season for a single region.

| Place | High months | Months with most finds, all years | Finds nearby, last 12 months, estimate on the day |
|---|---|---|---|
| Val di Fiemme | June to September 2026 | August 130, July 70, September 49 | 26 finds at 58 to 94, 2 at 35 |
| Campo dei Fiori | October and November 2025, May, June and September 2026 | September 25, October 21 | 6 finds, 37 to 88 |
| Valle Gesso | none | July 12, September 7 | 3 finds in June, 11 to 16 |
| Borgotaro | November 2025, May 2026 | October 14, September 12 | 4 finds, 12 to 36 |
| Pescasseroli | none | no find | none |
| Pollino | October 2025, April and May 2026 | 3 finds in all years | none |
| Sila | none | October 11, September 10, June 6, July 6 | 4 in autumn 2025 at 19 to 43, 6 in summer and October 2026 at 5 to 9 |
| Nebrodi | October and November 2025, April 2026 | October 4 | 2 in autumn 2025 at 63 and 65, 1 in July 2026 at 8 |
| Etna north | October and November 2025, April and May 2026 | October 6, September 4 | 2 in October 2025 at 91 and 93, 1 in July 2026 at 24 |
| Gennargentu | November 2025, March and May 2026 | 1 find in all years | none |

The monthly numbers are in `reports/method_outside_tuscany_months.csv`. The
daily estimates and factors are in `reports/method_outside_tuscany_days.csv`.
The temperatures and frost days of the months file are at the height of the
weather cell centre. The method corrects them to each square's altitude, so
the Val di Fiemme squares are about 3.6 °C warmer than that file shows.

What fits:

- Val di Fiemme follows its finds closely. 26 of the 28 finds of July to
  September 2026 fell on days with a median estimate of 58 or more. The other
  2 came on 30 September, at 35. Cooler days had brought the temperature
  factor down to 0.47 and the water factor to 0.70.
- Campo dei Fiori and the autumn of 2025 at Nebrodi and Etna north match their
  finds, with estimates of 63 to 93 on the days of the finds.
- Cold works as intended. Val di Fiemme stays at 5.0 to 5.1 from December to
  March. Valle Gesso and Pescasseroli stay at 5 to 10 in January.
- Summer heat and drought work as intended. Nebrodi, Etna north, Pollino and
  the Gennargentu stay at 5 to 6 in August.

## AC3: rules that give a wrong season

### The water store empties in the southern summer and does not refill

At Sila, the temperature factor was 0.59 to 0.96 on the summer days of finds,
but the water factor was 0 to 0.06. Rains of 3 to 9 mm in June and July did
not lift it. A store that loses half the evapotranspiration every day and
needs 40 mm to reach its full value cannot answer to short summer storms.

| Place | Month | Finds nearby | Median estimate on the find days | Water factor |
|---|---|---|---|---|
| Sila | June 2026 | 1 | 5 | 0 |
| Sila | July 2026 | 3 | 5 to 9 | 0 to 0.06 |
| Sila | October 2026 | 2 | 5 | 0 |
| Valle Gesso | June 2026 | 3 | 11 to 16 | 0.07 to 0.13 |

At Valle Gesso the water factor fell from 1.0 on 22 May to 0.1 on 2 June,
after 11 dry days with means of 15 to 20 °C. The finds of 7 to 11 June came
after 1 to 7 mm of rain a day. Of the 39 finds near Sila in all years, 13 came in
June to August and 21 in September and October. Its estimate reached 50 on
only 10 days of the 12 months, none of them from June to October 2026.

The weather cells are about 9 km wide, so they can miss local storms. This
check cannot separate a missed storm from a store that drains too fast. It
can say that the same pattern appears at two places 800 km apart.

### Mild, wet winters keep the estimate up on Etna and in the Gennargentu

| Place | Month | Days at 30 or more | Days at 50 or more | Finds nearby in that month, all years |
|---|---|---|---|---|
| Etna north | February 2026 | 18 | 0 | 0 |
| Etna north | March 2026 | 15 | 0 | 0 |
| Gennargentu | December 2025 | 23 | 5 | 0 |
| Gennargentu | January 2026 | 16 | 0 | 0 |
| Gennargentu | February 2026 | 23 | 3 | 0 |
| Gennargentu | March 2026 | 24 | 14 | 0 |

The cause is the cold side of the temperature rule. A day at 8 °C still scores
0.4. A week of such days with a full water store gives an estimate of about
41, and January to March were wet at both places. The Piemonte material
allows December for *B. aereus*. No source describes January to March, and
Etna north has 14 finds from June to October and none from November to May.
For the Gennargentu, 1 find in all years is too few to judge, so that row
rests on the sources alone.

### Weaker signs, not counted as wrong

- Spring highs. Pollino, Nebrodi and Etna north had 14 to 19 days at 50 or
  more in April or May 2026, with 1 find in those months across all years.
  The Piemonte material describes spring fruiting for some species, so the
  sources do not rule these months out.
- Early Alpine start. Val di Fiemme had 26 days at 50 or more in June. Its
  finds in all years number 3 in June and 70 in July. The season may start a
  few weeks early.
- Pescasseroli never reached 50. It has no find nearby in any year, so the
  check cannot say whether that is wrong. September 2026 brought 21 mm of rain
  there.

## AC4: recommendation

The method can be used as it is in the Alps and the northern Apennines. The
rules that change the season elsewhere should be changed in this order:

1. The water store. It should answer to summer storms in the southern
   mountains. Sila and Valle Gesso show finds on days when it was empty.
2. The cold side of the temperature rule. Days of 5 to 10 °C should score
   less, or need a run of warmer days, so that mild wet winters in Sicily
   and Sardinia stay low from January to March.

A frost rule or a season rule is not needed for the Alps. The temperature
rule already brings a frozen Alpine winter to 5. `docs/forecast_method.md`
should describe version 4, because it still lists the frost rule of version 2.

## Limits of this result

- One year of weather. A wetter summer or a drier winter could give a
  different picture.
- Few finds in the south. Pescasseroli, Pollino and the Gennargentu have 0 to
  3 finds in all years. Nebrodi has 7. A month with no find is weak evidence that nobody
  picked porcini there.
- Finds within 30 km cover many altitudes. A find at 600 m is compared with a
  cell whose squares reach 2,000 m.
- 405 finds have a blurred position, up to a few kilometres off.
- One weather cell per place. The places were chosen by hand from known
  porcini areas, not at random.
