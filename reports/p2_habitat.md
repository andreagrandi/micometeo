# P2 habitat: terrain and soil

Issue #4. This section covers terrain, soil and rock type. Forest cover comes in
issue #5.

## Question

Can we build a repeatable sample grid of the study area with terrain and soil
data whose origin we can trace?

## Answer

Yes. One command builds a grid of 504 squares of 500 m from scratch in 6 minutes
40 seconds. All 504 squares have altitude, slope steepness, slope direction,
soil acidity and soil texture, and 494 have a rock type. Every value has a
source column and a reliability column.

Elevation and rock type are detailed enough for 500 m squares. Soil from
SoilGrids has enough pixels, but its values are too uncertain to tell squares
apart. The 90 percent uncertainty range for soil acidity is 2.7 to 4.3 pH units
in every square, while the soil acidity itself only varies from pH 5.4 to 7.0
across the whole area.

## Sample area

- Box: 10.66 to 10.80 east, 44.05 to 44.14 north, from Cutigliano to San
  Marcello Pistoiese. The squares that cover it run from 4,373,500 to 4,385,500
  east and 2,326,500 to 2,337,000 north in EPSG:3035.
- The grid has 24 columns and 21 rows of 500 m squares, with IDs as in
  `docs/data_formats.md`.
- Altitude runs from 425 m to 1,734 m, with a median of 1,007 m. The median
  slope is 24 degrees.

## How to rebuild

```
uv run micometeo run p2_habitat
```

- The grid is written to `data/processed/p2_habitat/<run_id>/grid.parquet` and
  is not kept in Git.
- Raw downloads are kept in `data/raw/p2_habitat/`. A second run reuses them
  and takes about 1 second.
- The run from scratch is
  [20261010T184316Z-3b2c48](runs/p2_habitat/20261010T184316Z-3b2c48.json). The
  final run with the tables below is
  [20261010T190132Z-5fa16e](runs/p2_habitat/20261010T190132Z-5fa16e.json).

## Layers

The full list with URL, version, download date, file format and coordinate
system is in [data/p2_layers.csv](../data/p2_layers.csv).

| Layer | Used for | Licence | Stated detail |
|---|---|---|---|
| Copernicus DEM GLO-30, an elevation map from radar satellites | altitude, slope steepness, slope direction | Copernicus WorldDEM-30 licence, free of charge and worldwide, with a credit line | about 30 m |
| ISRIC SoilGrids 2.0, soil values predicted by a model from field samples | soil acidity, clay, sand and silt at 5 to 15 cm | CC BY 4.0 | 250 m |
| Regione Toscana geology database, the regional 1:10,000 geology map | rock type | CC BY, version not stated in the metadata record | 1:10,000 map |

All three licences allow this use. Rock type is included. Slope and slope
direction are derived from the elevation map, so anything published with them
must carry the credit line that starts with "produced using Copernicus
WorldDEM-30", as Article 6 of the licence requires.

The Tuscany map service gives the rock unit under a point but no shapes, so the
script asks for 4 points per square, at the centres of its four 250 m quarters.
That is 2,016 questions, about 5 minutes. The full regional download is a
290 MB archive and was not needed.

## How each value is filled

- Every layer is moved onto 25 m pixels in EPSG:3035, so each square holds
  exactly 20 by 20 pixels.
- Altitude and slope steepness are the mean of the pixels. Slope direction is
  the average direction in degrees clockwise from north, so 180 means the slope
  faces south.
- Soil values are the area mean of the 250 m SoilGrids pixels. Acidity is in pH
  units and texture in percent.
- Rock type is the unit found at most of the 4 points. A tie goes to the first
  in the order south-west, south-east, north-west, north-east.

## Reliability

| Value | high | medium | low | empty |
|---|---|---|---|---|
| altitude_m | 504 | 0 | 0 | 0 |
| slope_deg | 504 | 0 | 0 | 0 |
| aspect_deg | 466 | 0 | 38 | 0 |
| soil_ph, clay_pct, sand_pct, silt_pct | 0 | 0 | 504 | 0 |
| rock_unit_code | 277 | 88 | 129 | 10 |

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

- Elevation is far finer than a square.
- Soil changes every 260 to 400 m, finer than a square. Its pixels are not the
  problem. Its uncertainty is, see the reliability section.
- The script flags rock type, because a rock unit runs on for 925 m on average.
  That figure measures how large the rock formations are, not how coarse the
  map is. The map still shows two or more units inside 39 percent of the
  squares. The 4
  points per square only see changes down to 250 m, so this check cannot
  measure finer detail.

No layer is coarser than a square, so the 500 m size stays. There is no change
to `docs/decisions.md`.

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

## Coverage and gaps

From [p2_coverage.csv](p2_coverage.csv):

| Value | Squares with a value | Share |
|---|---|---|
| altitude_m, slope_deg, aspect_deg | 504 of 504 | 100% |
| soil_ph, clay_pct, sand_pct, silt_pct | 504 of 504 | 100% |
| rock_unit_code | 494 of 504 | 98% |

The 10 squares without rock type are listed in [p2_gaps.csv](p2_gaps.csv). They
sit in the north-east corner, at 1,440 to 1,630 m, across the main ridge in
Emilia-Romagna. The Tuscany map stops at the regional border. Covering that
side needs the Emilia-Romagna geology map.

Of the 2,016 points asked, 103 had no unit. Points inside Tuscany with no unit
lower a square's rock reliability but do not empty it.

## Rock types found

There are 23 units. The most common are quarzose-feldspathic sandstone of the
Macigno formation, MAC, MAC1 and MAC2, in 205 squares, and turbidites of the
Cervarola and Modino units, CEV1, CEV2 and MOD, in 188 squares. Turbidites are
layers of sandstone and siltstone laid down by underwater landslides.

## What this means for A2

A2 says tree and habitat data help at regional level. This half supports it for
terrain and rock type. Soil from SoilGrids gives values everywhere, but they
are too uncertain here to separate one square from the next. The status of A2
stays NOT TESTED until issue #5 adds forest cover.

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
