# P2 habitat: terrain, soil, rock and forest

Issues #4 and #5. Issue #4 built the grid with terrain, soil and rock type.
Issue #5 adds forest cover, broadleaf or conifer, and the regional forest type.

## Question

Can we build a repeatable sample grid of the study area with terrain, soil and
forest data whose origin we can trace? Can forest and tree maps we can
reproduce separate places that might suit porcini from places that do not?

## Answer

Yes. One command builds a grid of 504 squares of 500 m from scratch in about
7 minutes. All 504 squares have altitude, slope steepness, slope direction,
soil acidity, soil texture, forest share and broadleaf or conifer. 494 have a
rock type and 491 have a regional forest type. Every value has a source column
and a reliability column.

Elevation, rock type and forest cover are detailed enough for 500 m squares.
Soil from SoilGrids has enough pixels, but its values are too uncertain to tell
squares apart. The 90 percent uncertainty range for soil acidity is 2.7 to 4.3
pH units in every square, while the soil acidity itself only varies from pH 5.4
to 7.0 across the whole area.

For forest there are two kinds of answer:

- The Copernicus forest map of 2018 is current and has 10 m pixels. It tells
  forest from open land and broadleaf from conifer. It does not name any tree.
  In this area 478 of 504 squares come out as broadleaf, so on its own it
  barely separates one square from the next.
- The Tuscany forest inventory names the forest type at one point every
  400 m: beech, chestnut, Turkey oak, downy oak, hop hornbeam, silver fir and
  others. It tells beech, chestnut and oak woods apart at a useful scale. Its
  field survey dates from 1985 to 1993. In 59 of its 68 pasture squares,
  forest now covers at least 30 percent of the square.

The stop rule in issue #5 does not apply, because one available layer does
tell beech, chestnut and oak woods apart. A map that only shows broadleaf or
conifer would still be worth testing as a habitat map. It would separate
forest from open ridges and pastures, and conifer plantations from broadleaf
woods. It would not separate beech from chestnut.

## Sample area

- Box: 10.66 to 10.80 east, 44.05 to 44.14 north, from Cutigliano to San
  Marcello Pistoiese. The squares that cover it run from 4,373,500 to 4,385,500
  east and 2,326,500 to 2,337,000 north in EPSG:3035.
- The grid has 24 columns and 21 rows of 500 m squares, with IDs as in
  `docs/data_formats.md`.
- Altitude runs from 425 m to 1,734 m, with a median of 1,007 m. The median
  slope is 24 degrees.
- Forest covers a median of 98 percent of a square. Only 10 squares, on the
  open ridge in the north-east, have less than 10 percent forest.

## How to rebuild

```
uv run sporameteo run p2_habitat
```

- The grid is written to `data/processed/p2_habitat/<run_id>/grid.parquet` and
  is not kept in Git.
- Raw downloads are kept in `data/raw/p2_habitat/`. A second run reuses them
  and takes a few seconds.
- The run from scratch for terrain, soil and rock is
  [20261010T184316Z-3b2c48](runs/p2_habitat/20261010T184316Z-3b2c48.json). The
  two forest downloads add about 15 seconds. The final run with the tables
  below is
  [20261010T192011Z-c4f95b](runs/p2_habitat/20261010T192011Z-c4f95b.json).

## Layers

The full list with URL, version, download date, file format and coordinate
system is in [data/p2_layers.csv](../data/p2_layers.csv).

| Layer | Used for | Licence | Stated detail |
|---|---|---|---|
| Copernicus DEM GLO-30, an elevation map from radar satellites | altitude, slope steepness, slope direction | Copernicus WorldDEM-30 licence, free of charge and worldwide, with a credit line | about 30 m |
| ISRIC SoilGrids 2.0, soil values predicted by a model from field samples | soil acidity, clay, sand and silt at 5 to 15 cm | CC BY 4.0 | 250 m |
| Regione Toscana geology database, the regional 1:10,000 geology map | rock type | CC BY, version not stated in the metadata record | 1:10,000 map |
| Copernicus forest type 2018, a forest map from satellite images | forest share, broadleaf share, broadleaf or conifer | Copernicus Land Monitoring Service data, free and open access, with a credit line | 10 m |
| Inventario forestale della Toscana, the regional forest inventory | regional forest type | CC BY-SA 4.0 | one survey point per 400 m cell |

All five licences allow this use. Two of them add conditions:

- Slope and slope direction are derived from the elevation map, so anything
  published with them must carry the credit line that starts with "produced
  using Copernicus WorldDEM-30", as Article 6 of the licence requires.
- The forest inventory is CC BY-SA 4.0. Anything published that is derived
  from `regional_forest_type` must be shared under the same licence. This is
  fine for an experiment. It matters if the app ever ships this value.

The Copernicus forest map comes from the public EEA image service, which needs
no login. The script asks for the grid area in 10 m pixels in EPSG:3035. The
map counts land as forest when trees cover at least 10 percent of at least
0.5 ha. The service also offers tree cover density and the dominant leaf type.
The forest type map was enough for the values below.

The forest inventory is a 10 MB download. Field teams visited one point at the
centre of every 400 m cell between 1985 and 1993 and recorded the forest
category and the main trees in about 5,000 square metres around it. The
dataset was revised in 2009. The script reads only its table of points.

Three other forest sources were checked and not used:

- The Tuscany land cover map of 2019, at 1:10,000 and under CC BY, only says
  broadleaf woods or conifer woods in this area. It is used in the hand check
  below.
- The Tuscany forest vegetation map of 1999, under CC BY-SA 4.0, names beech,
  chestnut and oak woods too, but on 250 m cells drawn from a 1:250,000 map. It
  is coarser and older than the inventory.
- The JRC European Atlas of Forest Tree Species gives, for each species, the
  chance that it grows in a 1 km cell, as predicted by a model. It is coarser
  than a square and the inventory already answers the question, so it was
  left out.

## How each value is filled

- Every raster layer is moved onto 25 m pixels in EPSG:3035, so each square
  holds exactly 20 by 20 pixels.
- Altitude and slope steepness are the mean of the pixels. Slope direction is
  the average direction in degrees clockwise from north, so 180 means the slope
  faces south.
- Soil values are the area mean of the 250 m SoilGrids pixels. Acidity is in pH
  units and texture in percent.
- Rock type is the unit found at most of the 4 points. A tie goes to the first
  in the order south-west, south-east, north-west, north-east.
- `forest_share` is the share of the 400 pixels that are forest on the
  Copernicus map. Pixels the map marks as outside its area or unclassifiable
  count as missing.
- `broadleaf_share` is the share of the forest pixels that are broadleaf. It is
  empty when the square has no forest pixel.
- `leaf_type` is "no forest" when forest covers less than 10 percent of the
  square. Otherwise it is "broadleaf" from 75 percent broadleaf, "conifer" up
  to 25 percent broadleaf, and "mixed" in between. These three values only
  ever say broadleaf or conifer and never name a tree.
- `regional_forest_type` is the forest type found at most of the inventory
  points inside the square. A square holds 1 to 4 points. A tie goes to the
  point nearest the square centre. `regional_forest_points` gives the number
  of points. The Italian categories are kept in English, such as "beech woods"
  for Faggete. Points with no forest category become "not woodland", and
  "terreni saldi" becomes "open grassland or pasture".

## Reliability

| Value | high | medium | low | empty |
|---|---|---|---|---|
| altitude_m | 504 | 0 | 0 | 0 |
| slope_deg | 504 | 0 | 0 | 0 |
| aspect_deg | 466 | 0 | 38 | 0 |
| soil_ph, clay_pct, sand_pct, silt_pct | 0 | 0 | 504 | 0 |
| rock_unit_code | 277 | 88 | 129 | 10 |
| forest_share | 504 | 0 | 0 | 0 |
| broadleaf_share | 494 | 0 | 3 | 7 |
| leaf_type | 500 | 0 | 4 | 0 |
| regional_forest_type | 88 | 308 | 95 | 13 |

The rules are:

- Terrain is high when at least 95 percent of the square's pixels have a value
  and low from 50 to 95 percent. Below 50 percent the value is left empty.
- Slope direction is also low when the mean slope is under 5 degrees, or when
  the slopes inside the square face many ways. The 38 low squares are of the
  second kind, such as ridges and valley floors.
- Soil is never high, because SoilGrids values come from a model. It is medium
  when the range between the 5 and 95 percent values is at most 1.5 pH units
  or 20 percentage points of texture, and low otherwise. Every square is low.
  The median range is 3.5 pH units for acidity and 53 to 68 percentage points
  for texture.
- Rock type is high when all 4 points agree, medium when 3 agree and low
  otherwise.
- Forest values follow the same pixel coverage rule as terrain. Broadleaf
  share is low when forest covers less than 10 percent of the square. Leaf type
  is low when forest covers 10 to 30 percent, because the forest is then a
  small part of the square.
- Regional forest type is checked against the Copernicus map. It is low when
  the two disagree: a broadleaf type where Copernicus says conifer, a conifer
  type where it says broadleaf, a forest type where it says no forest, or open
  land where Copernicus finds at least 30 percent forest. A Copernicus value of
  "mixed" never counts as a disagreement. Without a disagreement the type is
  high when the square has at least 2 points that all agree, and medium
  otherwise.

Of the 95 low forest types, 59 are inventory pasture where forest now covers at least 30 percent, and
14 are silver fir where Copernicus says broadleaf. Beech and chestnut woods
are never low: 69 are high and 214 medium. Most are medium because 281
squares hold only one inventory point.

## Real detail compared with the square size

Real detail is the size of the smallest area a layer actually tells apart. The
script measures it as the average length of a stretch of identical values along
rows and columns of the layer's own pixels. It also counts the share of squares
that hold more than one value. The numbers are in
[p2_detail.csv](p2_detail.csv).

| Layer | Stated detail | Real detail | Squares with more than one value | Coarser than a 500 m square |
|---|---|---|---|---|
| Elevation | about 30 m | 28 m | 100% | no |
| Soil acidity | 250 m | 402 m | 99% | no |
| Clay | 250 m | 260 m | 100% | no |
| Sand | 250 m | 263 m | 100% | no |
| Silt | 250 m | 260 m | 100% | no |
| Rock type | 1:10,000 map | 925 m | 39% | no, see below |
| Copernicus forest type | 10 m | 416 m | 72% | no |
| Tuscany forest inventory | one point per 400 m cell | 400 m | 53% | no |

- Elevation is far finer than a square.
- Soil changes every 260 to 400 m, finer than a square. Its pixels are not the
  problem. Its uncertainty is, see the reliability section.
- The script flags rock type, because a rock unit runs on for 925 m on average.
  That figure measures how large the rock formations are, not how coarse the
  map is. The map still shows two or more units inside 39 percent of the
  squares. The 4 points per square only see changes down to 250 m, so this
  check cannot measure finer detail.
- The Copernicus forest map changes class every 416 m on average because the
  woods here are large and continuous. 72 percent of the squares still hold
  forest and another class, such as a meadow, a road or a patch of conifers.
- The forest inventory cannot see anything smaller than its 400 m point
  spacing. Of the 210 squares with two or more points, 53 percent hold two
  different forest types, so forest type often changes within a square.

No layer is coarser than a square, so the 500 m size stays. There is no change
to the grid decision D1 in `docs/decisions.md`.

## Spot checks

- Altitude at the Abetone pass reads 1,375 m. The official height is 1,388 m.
- For 6 squares spread over the area, the slope direction was worked out again
  from the altitude 200 m east, west, north and south of the centre. It agrees
  with the grid within 3 to 10 degrees in all 6.
- For 6 squares with high rock reliability, the map service was asked again at
  the square centre. All 6 gave the same unit as the grid.
- All 10 squares without rock type fall inside Emilia-Romagna on the GADM
  region outlines.

The soil values were not checked against field samples. None are available for
this area in the repository.

### Forest hand check

Six very different squares were checked by hand on 2026-10-10. Each was
compared with a satellite photo of the square from the Esri World Imagery
service, viewed only and not stored, and with the Tuscany land cover map of
2019 at the centre and the four quarter centres. The Tuscany aerial photo
service returned blank images for this area, so it could not be used.

| Square | Altitude | Grid values | Land cover map 2019 | What the photo shows | Verdict |
|---|---|---|---|---|---|
| A `500m_E4379000_N2331000` | 1,321 m | forest 100%, broadleaf 100%, beech woods from 4 points, high | broadleaf woods at 4 points, no answer at 1 | Closed broadleaf canopy over the whole square, with even rounded crowns and no clearing. | Agrees. |
| B `500m_E4376500_N2327500` | 568 m | forest 100%, broadleaf 100%, chestnut woods from 4 points, high | broadleaf woods at all 5 points | Closed broadleaf woods on two slopes either side of a valley. | Agrees on broadleaf. A photo cannot confirm chestnut. |
| C `500m_E4375000_N2335000` | 1,300 m | forest 100%, broadleaf 89%, silver fir woods from 2 points, low | broadleaf woods at all 5 points | Broadleaf crowns, some already brown, mixed with scattered dark pointed crowns that look like conifers. | Both partly right. Fir grows here as a minority in broadleaf woods. The inventory points fell on fir. |
| D `500m_E4381000_N2335000` | 1,145 m | forest 100%, broadleaf 100%, open grassland or pasture from 4 points, low | broadleaf woods at 3 points, no answer at 2 | Closed woods over almost all the square. Two small meadows and a few houses in the south-west corner. | The inventory is out of date. The pasture of 1985 to 1993 is forest now. |
| E `500m_E4384500_N2335000` | 1,678 m | forest 0%, no forest, open grassland or pasture from 2 points, high | natural pasture and grassland at all 5 points | Open grassland on the main ridge with tracks, bare patches and a few dark shrubs. | Agrees. |
| F `500m_E4380500_N2328000` | 1,012 m | forest 100%, broadleaf 68%, mixed, plantations of other non-native trees from 2 points, high | broadleaf woods at 3 points, conifer woods at 1, no answer at 1 | Darker fine-grained conifer stands in straight blocks next to lighter broadleaf woods. | Agrees on mixed. |

What the check shows:

- The three sources agree where the woods are pure broadleaf and where the land
  is open, as in A, B and E.
- The Copernicus map seems to undercount conifers mixed into broadleaf woods.
  All 23 inventory silver fir squares are at least 47 percent broadleaf on the
  Copernicus map, and no square in the area comes out as conifer. The 2019 land
  cover map also calls square C broadleaf.
- The inventory shows its age where farming has stopped. Square D, and most of
  the 68 inventory pasture squares, are now woods.
- The 2019 land cover map service gave no answer at 4 of the 30 points. It
  also missed 9 of 25 points when it was first explored. The cause was not
  traced.

## Coverage and gaps

From [p2_coverage.csv](p2_coverage.csv):

| Value | Squares with a value | Share |
|---|---|---|
| altitude_m, slope_deg, aspect_deg | 504 of 504 | 100% |
| soil_ph, clay_pct, sand_pct, silt_pct | 504 of 504 | 100% |
| rock_unit_code | 494 of 504 | 98% |
| forest_share, leaf_type | 504 of 504 | 100% |
| broadleaf_share | 497 of 504 | 99% |
| regional_forest_type | 491 of 504 | 97% |

The squares with gaps are listed in [p2_gaps.csv](p2_gaps.csv).

- The 10 squares without rock type sit in the north-east corner, at 1,440 to
  1,630 m, across the main ridge in Emilia-Romagna. The Tuscany map stops at
  the regional border. Covering that side needs the Emilia-Romagna geology
  map.
- The same 10 squares have no regional forest type, for the same reason. Three
  more squares on the Tuscany side of the border hold no inventory point.
  Covering Emilia-Romagna would need its own regional forest map.
- The 7 squares without broadleaf share are open ridge with no forest pixel at
  all. An empty value is correct there.

Of the 2,016 rock points asked, 103 had no unit. Points inside Tuscany with no
unit lower a square's rock reliability but do not empty it.

## Rock types found

There are 23 units. The most common are quarzose-feldspathic sandstone of the
Macigno formation, MAC, MAC1 and MAC2, in 205 squares, and turbidites of the
Cervarola and Modino units, CEV1, CEV2 and MOD, in 188 squares. Turbidites are
layers of sandstone and siltstone laid down by underwater landslides.

## Forest types found

| Regional forest type | Squares | Median altitude |
|---|---|---|
| beech woods | 143 | 1,273 m |
| chestnut woods | 140 | 839 m |
| open grassland or pasture | 68 | 1,038 m |
| hop hornbeam woods | 50 | 789 m |
| silver fir woods | 23 | 1,337 m |
| black locust woods | 16 | 579 m |
| Turkey oak woods | 14 | 857 m |
| not woodland | 13 | 731 m |
| plantations of other non-native trees | 10 | 1,408 m |
| downy oak woods | 7 | 651 m |
| other types, 1 or 2 squares each | 7 | |

Beech woods start where chestnut woods end. Half of the beech squares lie
between 1,157 and 1,409 m, and half of the chestnut squares between 732 and
953 m. Here altitude alone already separates most beech squares from most
chestnut squares.

## What this means for A2

A2 says tree and habitat data are useful at regional scale. The PRD measures
this with a sample grid you can rebuild, values with their sources, coverage
and real detail. The grid meets all four for terrain, rock type and forest:

- Forest cover and broadleaf or conifer are current, cover every square and
  are finer than a square.
- Forest type by tree comes only from the Tuscany inventory. It is detailed
  enough, but 30 to 40 years old, and stops at the regional border.
- Soil from SoilGrids gives values everywhere, but they are too uncertain here
  to separate one square from the next.

The status of A2 is VALIDATED, with these limits. Whether these values help
predict porcini finds is a separate question for P4, issues #8 and #9.

## Limits

- One sample area of about 11 by 10 km. Other parts of the Apennines may
  differ.
- Soil is read at one depth, 5 to 15 cm. Other depths were not checked.
- Elevation is surface height, including trees. In closed forest it can be
  10 to 20 m above the ground. This barely changes altitude at 500 m, but it
  adds some noise to slope steepness.
- The rock units come from the map service as it answered on 2026-10-10. The
  service gives no version number, so the layer list cites the metadata record
  instead.
- The forest inventory was surveyed from 1985 to 1993. Pastures abandoned
  since then are now woods, and other changes, such as chestnut woods turning
  into mixed woods, are likely but were not measured.
- A square holds 1 to 4 inventory points, each describing about 5,000 square
  metres. One point cannot describe a 500 m square well when the forest type
  changes inside it.
- The Copernicus forest map shows conifer mixed into broadleaf woods as
  broadleaf more often than the inventory and the photos suggest. Its 2018
  date is also eight years old.
- The hand check covers 6 squares and uses photos, which show broadleaf or
  conifer but not which broadleaf tree. It cannot confirm beech or chestnut.
