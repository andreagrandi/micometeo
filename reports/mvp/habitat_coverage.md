# National forest coverage

## Source and meaning

The national forest build uses the Copernicus High Resolution Layer Forest
Type 2018 map through the [EEA image service](https://image.discomap.eea.europa.eu/arcgis/rest/services/GioLandPublic/HRL_ForestType_2018/ImageServer).
Requests use its native 10 m pixels, EPSG:3035 coordinates and nearest-pixel
sampling. The build records exact request bounds and options, download times,
checksums, the release and the returned coordinate-system description.

The 2018 map distinguishes broadleaf and conifer forest. It does not identify
tree species or describe current ground conditions. No Tuscany inventory
values are included. National coverage therefore does not depend on that
regional inventory, and this output contains no inventory derivatives under
its CC BY-SA terms.

`forest_share` divides forest pixels by valid classified pixels.
`broadleaf_share` divides broadleaf pixels by forest pixels. It is null when
no forest exists. Code 0 is valid non-forest land, codes 1 and 2 are broadleaf
and conifer, and codes 254 and 255 remain unclassifiable or outside coverage.
At least 95 percent valid coverage gives high input quality, 50 to 95 percent
gives low quality, and less than 50 percent leaves the square unavailable.

At least 10 percent forest marks a square as eligible for an estimate. The
test uses integer pixel counts before rounding. A broadleaf share of at least
75 percent gives the broadleaf class, at most 25 percent gives conifer, and
the interval between them gives mixed forest. These classes never imply a
named tree species.

Each eligible 500 m square uses the 0.1 degree weather cell containing its
centre. The stored coordinates identify the centre of that weather cell.
Several regions can share a weather cell, so regional weather counts cannot
be added to obtain the national distinct count.

## Build command

```sh
uv run python apps/application/manage.py build_national_forest \
  --grid-build-version italy-500m-istat-2026-01-01-v1 \
  --build-version italy-forest-copernicus-2018-v1 \
  --cache-dir data/raw/mvp_forest \
  --output-dir data/processed/mvp_forest \
  --max-source-chunk-m 40000 \
  --output-format jsonl
```

The command stores each completed chunk before continuing. Repeat it after
an interruption to reuse completed rows and validated downloads. A build
becomes complete only after its simplified forest layer has been written.

## National measurements

The completed build is `italy-forest-copernicus-2018-v1`, with ID
`1b1c26dc-4774-43dc-bf44-cdaab392d029`. Its fingerprint is
`e1263b0baeb79c8ef1ee03070888050d054348cf467eb4e4afc163b4b1239b66`.
It uses the completed `italy-500m-istat-2026-01-01-v1` grid.

| Measurement | Result |
| --- | ---: |
| Stored 500 m squares | 1,217,473 |
| Completed source chunks | 676 |
| Squares with at least 10 percent forest | 717,104 |
| Squares below the forest threshold | 498,617 |
| Squares with insufficient source coverage | 1,752 |
| Squares with any missing source pixels | 10,171 |
| Squares with low input quality | 6,166 |
| Distinct weather cells containing forest | 3,726 |
| Downloaded raster bytes | 4,050,466,392 |
| Cache bytes including source metadata | 4,052,180,046 |
| Forest tables and indexes, bytes | 349,315,072 |
| Unique 2 km layer polygons | 74,047 |
| Uncompressed forest layer, bytes | 22,169,307 |
| Gzip forest layer, bytes | 3,377,975 |

The table and index size was measured before the estimate service added its
separate weather-cell lookup index. Estimate storage measurements include
that additional index separately.

The source downloads ran from 2026-10-12 00:08:43 to 00:42:31 UTC. Every
chunk retains its original retrieval time, raster checksum, native coordinate
description and request metadata. The service returns the older EPSG:3035
description with the ETRS89 datum. The reader verifies that description and
records it without changing the source pixels.

The build started at 00:01:00 UTC and recorded completion at 00:43:32 UTC.
This interval includes interrupted work and is not a clean runtime benchmark.
The final cached reconciliation took 35.164 seconds inside the command and
41.74 seconds of wall time. It reused all 676 chunks, processed no new chunks
and peaked at 348,061,696 bytes of resident memory. Other local work ran
concurrently on an Apple M2 Pro with 32 GiB of memory.

The 1,752 unavailable squares remain explicit gaps. They are not counted as
zero forest. An early chunk failed validation because the reader did not yet
recognize the source's older EPSG:3035 description. The corrected reader
resumed that chunk and completed the build. The source pixels in unavailable
squares do not provide the minimum valid coverage.
In total, 10,171 squares have some missing source pixels. This includes 2,253
squares with at least 95 percent coverage, 6,166 with 50 to 95 percent
coverage, and the 1,752 unavailable squares. Input quality describes the
classified pixels and does not measure prediction accuracy.

| Region | Squares | Forest | Below threshold | Unavailable | Weather cells |
| --- | ---: | ---: | ---: | ---: | ---: |
| Piemonte | 102,247 | 62,099 | 40,148 | 0 | 340 |
| Valle d'Aosta | 13,283 | 6,054 | 7,229 | 0 | 45 |
| Lombardia | 96,040 | 42,998 | 53,042 | 0 | 329 |
| Trentino-Alto Adige | 54,831 | 39,880 | 14,951 | 0 | 191 |
| Veneto | 73,646 | 29,468 | 44,110 | 68 | 262 |
| Friuli-Venezia Giulia | 32,206 | 19,646 | 12,551 | 9 | 125 |
| Liguria | 22,224 | 20,441 | 1,715 | 68 | 105 |
| Emilia-Romagna | 90,241 | 47,633 | 42,588 | 20 | 313 |
| Toscana | 92,707 | 71,031 | 21,530 | 146 | 333 |
| Umbria | 33,814 | 25,336 | 8,478 | 0 | 123 |
| Marche | 37,549 | 23,343 | 14,155 | 51 | 135 |
| Lazio | 69,309 | 45,812 | 23,376 | 121 | 240 |
| Abruzzo | 43,372 | 30,588 | 12,742 | 42 | 149 |
| Molise | 17,804 | 12,001 | 5,795 | 8 | 73 |
| Campania | 55,039 | 37,828 | 17,074 | 137 | 191 |
| Puglia | 78,478 | 27,371 | 50,918 | 189 | 260 |
| Basilicata | 40,043 | 26,496 | 13,531 | 16 | 132 |
| Calabria | 61,250 | 41,028 | 20,075 | 147 | 200 |
| Sicilia | 104,785 | 40,591 | 63,808 | 386 | 328 |
| Sardegna | 98,605 | 67,460 | 30,801 | 344 | 321 |

Squares have one owning region, so their regional totals add to the national
total. Weather cells can cross region borders and their counts do not add.

## Representative checks and repeat identity

These checks locate actual stored squares. Their leaf classes describe the
classified source pixels, not a field survey or a tree-species observation.

| Place | Square ID | Forest fraction | Broadleaf fraction | Class |
| --- | --- | ---: | ---: | --- |
| Alps near Cortina | `500m_E4485000_N2605000` | 0.1376 | 0.7064 | Mixed |
| Apennines near Abetone | `500m_E4374000_N2337500` | 0.8284 | 0.8875 | Broadleaf |
| Sicily near Etna | `500m_E4763500_N1644500` | 0 | Missing | No forest |
| Sardinia near Fonni | `500m_E4256500_N1892000` | 0.4080 | 1 | Broadleaf |
| Lampedusa | `500m_E4556500_N1388000` | 0 | Missing | No forest |
| Elba | `500m_E4346500_N2189500` | 0.0864 | 1 | Below threshold |

The database audit hashes every square ID, row ID, chunk ID, fraction, class,
weather coordinate and missing reason in square order. The resulting SHA-256
is `e0be9b3583c963d13798a38fb4cd5122beb19e7ab45c337187ccd27e5015b11b`.

The layer is
`data/processed/mvp_forest/italy-forest-copernicus-2018-v1/forest_layer_2000m.geojson.gz`.
Its SHA-256 is
`159172e3fb7e2529fd5d06ca5b9800d3ce4819c27735848c2d08a41a35444d98`.
The audit checks unique polygon geometries, fractions above zero and at most
one, and the absence of any property other than `forest_share`.
Repeating the completed command took 2.818 seconds, reused all 676 chunks and
processed none. The repeat audit matched all stored row identities, values,
source references, regional counts, example squares and the layer checksum.

The local PostGIS checks run with:

```sh
uv run pytest tests/app/test_national_forest.py tests/test_habitat.py
```

They cover missing source pixels, mixed classes, exact threshold decisions,
repeat identity, interrupted downloads, source metadata, unchanged chunk
layouts and atomic publication of the simplified layer.

## Redistribution and credit

The source is available under the Copernicus free and open access terms in
EU Regulation 1159/2013. Redistribution must name the source, describe changes
and avoid implying European Union endorsement. The build retains this credit:

> © European Union, Copernicus Land Monitoring Service 2018, European Environment Agency

Micometeo groups the classified 10 m pixels into 500 m fractions and produces
a separate 2 km forest-share layer for broad map views. The latter contains
forest coverage only. Neither transformation adds a mushroom estimate or
makes a claim about tree species. The 500 m display squares and the 2 km layer
do not imply that a mushroom percentage has that level of accuracy.
