# National terrain coverage

## Source and limits

The build uses the public AWS copy of Copernicus DEM GLO-30. The
[AWS collection record](https://registry.opendata.aws/copernicus-dem/) identifies
this copy as the 2021 release. It is separate from newer releases available
through the authenticated Copernicus service. The
[AWS readme](https://copernicus-dem-30m.s3.amazonaws.com/readme.html) describes
the public tiles and their naming.

GLO-30 records surface height. Trees and buildings can contribute to that
height. Its native spacing is one arc second, about 30 m. Heights use metres
above the EGM2008 reference, as described in the
[Copernicus collection information](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM).

SporaMeteo resamples the data onto a 25 m processing grid to calculate altitude,
slope and slope direction for the 500 m squares. Resampling does not create
finer source evidence. Each result joins the ISTAT grid by its build and cell
identity. A missing source remains unavailable and never becomes zero height.

The build reads bounded windows aligned to the native source grid. It samples
the same four neighbouring source pixels at each transformed destination
centre, independent of the processing rectangle. It includes neighbouring
pixels while calculating slopes, then removes those margins before storing
cell results. Cached source records retain their URLs, retrieval times,
checksums, source detail and credit.

## National run

The local run completed on 12 October 2026 on an Apple M2 Pro with 32 GiB of
memory and PostGIS in the project's Docker service. It used this command:

```sh
uv run python apps/application/manage.py build_national_terrain \
  --grid-build-version italy-500m-istat-2026-01-01-v1 \
  --build-version italy-terrain-glo30-2021-v2 \
  --cache-dir data/raw/mvp_terrain
```

The build ID is `8c3ba045-c47a-466a-b2e7-363dadfa1336`. Its input fingerprint is
`330f908703d75c401c8f8fe7bd04e4dc53b55ac87a24d14653eb39b0eddd2d04`.
The source manifest fingerprint is
`d428e9e5c0e8e039eaa3588ac1a43cf0a73370865cb7d18517f71d9c6cf85b5a`.

All 676 chunks completed. PostGIS holds 1,217,473 terrain rows, exactly one
for each grid membership. Every row has altitude and slope values with full
valid-pixel coverage. Direction is undefined on 401,778 squares whose mean
slope is below 5 degrees. A direction with a circular resultant below 0.3
keeps the pilot's low-quality indication. These are input-quality rules, not
claims about the accuracy of a mushroom percentage.

Review of the earlier test build found that its reprojection could change a
cell's values when processing rectangles changed. Version 2 fixes that
dependence. A real cached 50 km window and two adjacent 25 km windows produced
identical stored altitude, slope and direction values for all 5,000 squares.

The version 2 run processed all 676 chunks from cached source tiles. The
command measured 644.857 seconds on its monotonic timer. The process wall
time was 1,595.36 seconds while other local work was running. Peak resident
memory was 457,490,432 bytes, or 436.3 MiB. This is a complete processing run
with a warm download cache, not a fresh-download measurement.

The 86 available source tiles occupy 2,039,901,522 bytes. Five further tile
requests returned confirmed absence. The version 2 terrain rows occupied
190,822,856 bytes as measured by PostgreSQL row sizes. Allocated terrain tables
and indexes occupied 703,299,584 bytes with both the earlier test build and
version 2 retained. Repeating the completed command took 14.218 seconds,
processed zero chunks and downloaded zero tiles. It retained the build ID
and all row, value and source identities.

## Regional coverage

Each square belongs to one region for counting. Altitude and slope have the
same populated count. The missing column counts unavailable altitude or
slope. Undefined direction on flat ground is separate from missing source
data.

| Region | Squares | Altitude and slope populated | Direction populated | Missing |
|---|---:|---:|---:|---:|
| Piemonte | 102,247 | 102,247 | 68,013 | 0 |
| Valle d'Aosta | 13,283 | 13,283 | 13,176 | 0 |
| Lombardia | 96,040 | 96,040 | 45,144 | 0 |
| Trentino-Alto Adige | 54,831 | 54,831 | 53,142 | 0 |
| Veneto | 73,646 | 73,646 | 27,906 | 0 |
| Friuli-Venezia Giulia | 32,206 | 32,206 | 17,632 | 0 |
| Liguria | 22,224 | 22,224 | 21,317 | 0 |
| Emilia-Romagna | 90,241 | 90,241 | 43,922 | 0 |
| Toscana | 92,707 | 92,707 | 74,008 | 0 |
| Umbria | 33,814 | 33,814 | 27,842 | 0 |
| Marche | 37,549 | 37,549 | 33,073 | 0 |
| Lazio | 69,309 | 69,309 | 46,992 | 0 |
| Abruzzo | 43,372 | 43,372 | 38,103 | 0 |
| Molise | 17,804 | 17,804 | 15,626 | 0 |
| Campania | 55,039 | 55,039 | 41,072 | 0 |
| Puglia | 78,478 | 78,478 | 15,236 | 0 |
| Basilicata | 40,043 | 40,043 | 33,678 | 0 |
| Calabria | 61,250 | 61,250 | 52,365 | 0 |
| Sicilia | 104,785 | 104,785 | 79,006 | 0 |
| Sardegna | 98,605 | 98,605 | 68,442 | 0 |
| Italy | 1,217,473 | 1,217,473 | 815,695 | 0 |

## Representative checks

These are stored 500 m means at the listed coordinates. They check national
joins and plausible units. They are not surveyed point elevations.

| Place | Latitude | Longitude | Altitude m | Slope degrees | Direction degrees |
|---|---:|---:|---:|---:|---:|
| Alps near Cortina | 46.540 | 12.140 | 1,235.8 | 7.9 | 219.5 |
| Apennines near Abetone | 44.146 | 10.664 | 1,387.5 | 16.6 | 243.5 |
| Sicily near Etna | 37.750 | 14.990 | 3,197.4 | 18.9 | 265.1 |
| Sardinia near Fonni | 40.121 | 9.253 | 947.3 | 10.3 | 333.4 |
| Lampedusa | 35.5122 | 12.573 | 58.5 | 7.6 | 162.6 |
| Elba | 42.812 | 10.315 | 11.9 | 6.4 | 140.6 |

All six examples have full source coverage. Lampedusa's direction has low
quality because its pixel directions conflict. National mean elevations range
from -4.8 to 4,663.8 m, and slopes range from 0 to 59.0 degrees. All defined
directions fall between 0 and 359.9 degrees.

## Source gaps and repeatability

The source manifest records these confirmed missing tiles:

- `N35_00_E013_00`
- `N38_00_E011_00`
- `N39_00_E014_00`
- `N40_00_E010_00`
- `N43_00_E014_00`

The processing rectangles extend offshore. These absent tiles did not leave
missing pixels in any stored Italian grid square. The national source-gap
count is zero. A future absence that affects a square will retain its missing
fraction and detail instead of producing a sea-level value.

The repeat audit hashes row IDs, grid IDs, chunk links, values, quality and
missing details in cell order. Both audits produced
`ac3ce1d4d287feb544139d754fa4710068c1d40def414193fa0926ac99bb336c`.
The source manifest fingerprint also remained unchanged.

The focused terrain and habitat tests cover known tilted and flat surfaces,
north-crossing circular means, adjacent chunk margins, missing pixels,
interruption recovery, cache reuse and source provenance. They also cover a
sparse 25 km coastal chunk and direction rounding at north.

## Required credit

Article 6 of the [WorldDEM-30 licence](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf)
requires the source credit and the no-liability notice for derived terrain:

> produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved

> The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30

The build and each source record retain both notices. Keep them when exporting
the derived values or showing their source in an explanation. Do not imply
endorsement by the source organisations.
