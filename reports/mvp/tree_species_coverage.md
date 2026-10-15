# Tree species source assessment

Checked on 12 October 2026 using source metadata and a small Tuscany sample.
This assessment does not import a national database.

## Decision

The project owner selected JRC for the first version on 12 October 2026.
SporaMeteo needs a broad indication of suitable host woodland for the four
porcini species considered together. JRC names more relevant Italian species
than the Bonannella release, including downy oak, sessile oak and maritime
pine. This coverage is the main reason for the choice. Its downloads work
and its records permit reuse with credit. The same twelve species
require about 220 MB of JRC archives versus 10.02 GB of complete Bonannella
files. Three JRC sample reads succeeded on their first attempt.

Accept JRC's age and coarse detail. The checked release represents 2006 and
has 1 km pixels. It cannot establish differences between adjacent 500 m
squares and does not measure tree shares.

Keep Bonannella as a candidate for newer, finer information. It provides
2018 to 2020 maps on a 30 m grid, but omits several relevant species and its
fir sample needed a retry. This test does not establish that its finer grid
gives more accurate answers in Italy. Regional sources remain optional local
evidence. This ticket concludes the source assessment. It does not integrate
tree values into the application or change the forecast calculation.

Use JRC as supporting habitat evidence alongside the existing forest map.
Its occurrence scores are not tree cover fractions or proof of a dominant
tree. A low score must not become a hard exclusion for porcini. The current
[forecast method](../../docs/forecast_method.md) does not use tree species.
Any future effect on that calculation needs separate validation.

## Follow-up work

The owner narrowed issue #75 to checking sources and comparing availability,
costs, access time and suitability. The national build requirements in the
original issue are outside this assessment. No national download or database
build is needed to finish it.

Before using JRC in the application, separate implementation work must:

- Pin the selected species files and record their dates, checksums, licence
  notices and required credit.
- Define how the 1 km occurrence values attach to 500 m squares and host
  groups. Preserve missing values and the original source detail.
- Add cached downloads, resumable loading, source metadata and database
  lookups. Verify repeat runs and measure completeness across Italy.
- Compare forecasts with and without tree information using independent
  observations before assigning it a numerical effect.

This assessment establishes access and selects a source. It does not establish
national completeness, national loading time or improved forecast accuracy.

## Availability, costs and limitations

| Question | JRC atlas | Bonannella through Zenodo | Regional sources |
|---|---|---|---|
| Access checked | All 21 relevant family archive URLs answered HTTP 200. Three archives downloaded and opened. | Twelve host-species records and headers checked. Two pilot reads succeeded immediately; fir succeeded on one retry. | Tuscany archive answered HTTP 200 and existing local data were readable. Piemonte metadata checked; no vector download tested. |
| Data fee | No fee or login for tested downloads. | No fee or login for tested reads. | No fee for the checked Tuscany source. Piemonte lists an open licence. |
| Terms | European Commission reuse notice, with source acknowledgement and applicable dataset notices. | CC BY 4.0, with attribution, licence link and notice of changes. | Tuscany CC BY-SA 4.0. Piemonte CC BY 4.0. Check other regions separately. |
| Coverage | Europe including Italy; actual pilot pixels checked. | Europe including Italy; actual pilot pixels checked. | Each source covers its region. |
| Date represented | Checked beech, chestnut and fir records specify 2006. Atlas published in 2016. | Six periods across 2000 to 2020. Tested files cover 2018 to 2020, version v0.3, published 25 July 2022. | Tuscany surveys from 1985 to 1993. Piemonte 2025 edition combines its 2016 map with the 2020 national forest boundary. |
| Native detail | Measured 1,000 m pixels. Statistical interpolation may be smoother than this spacing. | Measured 30 m pixels. Uses satellite and environmental inputs of different resolutions. Pixel spacing is not verified local accuracy. | Tuscany samples one point per 400 m cell. Piemonte publishes at scale 1:10,000. |
| Meaning | Relative probability of presence. | Modelled probability of at least one individual in a pixel. | Survey category or forest type, depending on source. |
| Missing values | A distinct negative floating-point marker, not zero. | Zero is declared missing in the sampled rasters. Do not turn it into confirmed absence. | Unclassified categories and places outside the source remain unavailable. |
| Main drawback | Old and coarse. | Missing species, ambiguous zero encoding and intermittent access in this test. | Uneven coverage, dates and category definitions. |

The JRC records for
[beech](https://data.jrc.ec.europa.eu/dataset/21012c45-0433-41d6-910e-24a2e72cf35a),
[chestnut](https://data.jrc.ec.europa.eu/dataset/4fb09324-9a61-4a90-bdce-48cb0e32b8cf)
and [silver fir](https://data.jrc.ec.europa.eu/dataset/af5644c2-d3dd-46e3-9490-44b143fb3163)
confirm their dates, anonymous access and reuse terms. Raster links are present
in the actual [atlas table](https://forest.jrc.ec.europa.eu/en/european-atlas/atlas-data-and-metadata/).
An earlier text extraction missed them. The claim that JRC rasters were
unavailable was incorrect.

The checked [EcoDataCube catalogue route](https://s3.ecodatacube.eu/arco/stac/catalog.json)
did not list these tree collections. This does not mean the underlying data
are unavailable. Archived Zenodo records provide working URLs. The
[Bonannella paper](https://doi.org/10.7717/peerj.13728) explains the maps and
their evaluation, but supplies no current field check for this pilot.

The [Tuscany download page](https://www502.regione.toscana.it/geoscopio/download/tematici/ift/index.html)
states CC BY-SA 4.0. Use that file-specific notice rather than the generic
catalogue's shorter attribution label. The
[Piemonte record](https://www.dati.gov.it/node/view-dataset/dataset?id=f633d439-5419-404c-9d83-8f37097911dd)
confirms its date, scale and licence, but does not enumerate species classes.
Piemonte has no coverage of the Tuscany pilot.

## Measured time and data size

These times describe this laptop and connection. First reads used a new
process, but upstream caches and network conditions were uncontrolled.
MB and GB use decimal bytes. These are source-access measurements, not
national database build times.

| Operation | Data size | Measured result |
|---|---|---|
| JRC beech archive download, open and pilot read | 21.96 MB downloaded | 4.561 seconds, succeeded |
| JRC chestnut archive download, open and pilot read | 19.50 MB downloaded | 4.199 seconds, succeeded |
| JRC fir archive download, open and pilot read | 20.26 MB downloaded | 4.266 seconds, succeeded |
| Bonannella beech pilot read | 140,751 pixels read; network bytes not measured | 13.928 seconds, succeeded |
| Bonannella chestnut pilot read | 140,751 pixels read; network bytes not measured | 15.450 seconds, succeeded |
| Bonannella fir pilot read | Same bounded window | First attempt failed to open. One retry succeeded in 31.331 seconds. |
| Existing Tuscany inventory read and selection | Local attribute file is 173.77 MB | 0.480 seconds, selecting 759 pilot points |
| Repeat window read on the same open raster | In-process cache check | All six successful reads returned identical values and masks in under 0.001 seconds. |

The three JRC archives total 61,711,995 bytes and took 13.026 seconds including
opening and sampling. Tuscany's archive advertises 9,854,201 bytes. A fresh
Tuscany download was not timed because the P2 files already exist.

For the same twelve host species, JRC advertises 219,814,397 archive bytes.
The pinned Bonannella records list 10,018,124,107 bytes for complete files,
about 46 times as much. All 21 JRC entries in the relevant families total
368,533,395 bytes. These totals come from headers and metadata, not complete
collection downloads.

An estimate for downloading the common twelve JRC species is about 46 seconds
if the measured throughput holds. This excludes national grid processing.
There is no reliable complete-file download estimate for Bonannella from
these partial reads. Its successful partial reads total 60.709 seconds,
excluding the failed attempt. They do not measure full-download throughput.

The test incurred no source fees and provisioned no services. A later
deployment would have storage, processing and possibly metered-network costs.
Those depend on its configuration and are not priced here. Downloaded data
can be retained for local reuse. No national import runtime was measured.

## Species coverage

| Host | JRC atlas entries | Bonannella entries |
|---|---|---|
| Beech | Fagus sylvatica | Fagus sylvatica |
| Chestnut | Castanea sativa | Castanea sativa |
| Oaks | Quercus cerris, frainetto, ilex, petraea, pubescens, pyrenaica, robur, suber | Quercus cerris, ilex, robur, suber |
| Pines | Pinus cembra, halepensis, mugo, nigra, pinaster, pinea, sylvestris | Pinus halepensis, nigra, pinea, sylvestris |
| Spruce and fir | Picea abies, Picea sitchensis, Abies alba, Abies spp. | Picea abies, Abies alba |

The JRC table lists 39 downloadable relative-presence layers in total.
The 21 entries above include a genus-level fir group and species that are not
usual native Italian hosts. Listing them does not recommend importing every
entry or treating a genus as an identified species.

Bonannella covers sixteen species. Its other four are Corylus avellana,
Olea europaea, Prunus avium and Salix caprea. It omits downy oak, sessile oak
and maritime pine. Broadleaf and conifer labels cannot supply those names.

The Tuscany inventory distinguishes beech, chestnut, silver fir, Turkey oak,
holm oak, downy oak, cork oak and several named pine categories, alongside
other forest and non-forest categories. It checks local names, but its age
prevents treating it as current ground truth.

## Tuscany comparison

The test uses the P2 sample box near Cutigliano and San Marcello Pistoiese.
Its EPSG:3035 extent is 4,373,500 to 4,385,500 metres east and 2,326,500 to
2,337,000 metres north, covering 126 square kilometres. It contains 759
inventory points. Beech, chestnut and silver fir account for 471 of them.

Each source was sampled at the original survey coordinate. Each JRC window
contains 143 native pixels; each Bonannella window contains 140,751 pixels.
Many survey points therefore share a JRC value. The test accesses no database.

| Inventory category | Points | JRC points with values | JRC mean score | Bonannella points with values | Bonannella mean score |
|---|---:|---:|---:|---:|---:|
| Beech | 214 | 214 | 0.469 | 214 | 0.985 |
| Chestnut | 224 | 224 | 0.322 | 223 | 0.770 |
| Silver fir | 33 | 33 | 0.209 | 33 | 0.917 |

Means exclude missing values. Bonannella percentages are divided by 100.
Higher scores do not establish higher accuracy. The models estimate different
forms of occurrence, and this sample lacks reliable absences and a current
field survey. Possible overlap with their training observations was not
checked. This is a consistency comparison, not independent validation.

JRC has values throughout all three pilot windows. Bonannella has values in
135,512 of 140,751 beech pixels, 116,267 chestnut pixels and 111,264 fir pixels.
Its zero pixels remain missing according to its masks. The paper describes
probabilities from zero to 100, while the files mark zero as missing. This
test cannot distinguish a rounded zero from absent source data.

As a separate diagnostic, choosing the highest of the three JRC scores
matches 271 inventory labels, differs from 196, and ties on four. It picks
beech at all 33 silver-fir points. This is not a validated classifier and does
not prove fir is absent. The maps estimate occurrence while the inventory
names a forest category.

A matched three-species ranking for Bonannella was not completed in one run
because fir failed initially. Its successful single-species retry supplied
the fir row above. There is no demonstrated accuracy winner from this test.

## Reproduce the bounded check

```sh
uv run python experiments/tree_sources/check_sources.py
```

The script reads the existing P2 inventory and three species from each
national source. It keeps rasters in memory, caps each JRC archive at 30 MB
and each sample window at 250,000 pixels, and prints JSON measurements.
Remote requests have timeouts. It has no automatic retries or database access.
The one retry used in this assessment was:

```sh
uv run python experiments/tree_sources/check_sources.py --provider Bonannella --species fir
```

The tested Zenodo records are
[beech 6956944](https://zenodo.org/records/6956944),
[chestnut 6951628](https://zenodo.org/records/6951628) and
[fir 6953790](https://zenodo.org/records/6953790).
Their filenames select `anv.eml_p`, `2018..2020` and `v0.3`.
The tested JRC archives are `Fagus-sylvatica_rpp.zip`,
`Castanea-sativa_rpp.zip` and `Abies-alba_rpp.zip` from the atlas table.

Credit JRC and the named dataset authors, relevant atlas chapters and
de Rigo and colleagues' 2016 modelling chapter. Credit Bonannella and
colleagues' 2022 paper and individual Zenodo records under CC BY 4.0.
Credit Regione Toscana for the inventory. The inventory-derived comparison
tables here are shared under CC BY-SA 4.0.

National per-region completeness, current field accuracy and full ingestion
runtime remain unmeasured. These small checks establish source access and
practical differences without requiring a national database build.
