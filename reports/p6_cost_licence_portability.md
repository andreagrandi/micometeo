# P6 licences, running costs and moving servers

Issue #11 covers the licence and cost sections. Issue #12 adds the backup,
restore and server move test.

## Question

Do the data licences allow a service that is free for users, and what would it
cost each month to run?

## Answer

Yes, with five conditions. No source used in Epic 1 stops a free app. The cost
does not change between 10 and 100 users.

A rented server with backups costs 7.20 to 9.74 euro a month with Italian VAT
among the servers that could be ordered on 11 October 2026, all at Netcup.
Only the 24-month contract, at 7.20 euro, is inside the provisional target of
5 to 8 euro. A 1-month contract costs 9.74 euro. The cheaper OVH and Hetzner
servers, 4.65 to 8.65 euro, were sold out in Europe on that day.

The conditions:

- The app must stay non-commercial to use the free Open-Meteo plan: no ads and
  no subscriptions. Otherwise the cheapest paid plan is 29 euro a month.
- GADM area outlines cannot ship in the app. Replace them with ISTAT outlines
  or OpenStreetMap borders.
- Finds and their photos stay out of the app. Finds only test the rules.
- Anything the app publishes from the Tuscany forest inventory must be shared
  under CC BY-SA 4.0.
- Every map and data page carries the credit lines listed below.

All prices were checked on 11 October 2026. They are dated observations, not
quotes. Nothing was bought and no account was opened.

## How this was done

- Every source in the run records of P1 to P5 was listed, and its licence and
  terms were read again on the provider's site. Where the site blocked
  automated reads, the table says so and names the other source used.
- Open-Meteo prices come from the Stripe price table that its pricing page
  loads. The page itself shows no amounts.
- `uv run sporameteo run p6_costs` measures the home area, the daily scoring
  and the size of the stored scores, and writes `reports/p6_sizes.csv` and
  `reports/p6_users.csv`. Run record:
  [20261011T142322Z-4fe9ea](runs/p6_costs/20261011T142322Z-4fe9ea.json). It
  took 2.2 seconds.
- Server prices come from the OVHcloud configurator and the Netcup order
  pages, read in a browser with Italy set as the country. The Hetzner site
  loads its prices with JavaScript and showed no amounts, even in a browser,
  so Hetzner prices come from costgoat.com, last updated on 5 September 2026.

## Licences

The full table, with URL, usage limits, cost, risks and the date checked for
all 23 sources, is [p6_licences.csv](p6_licences.csv).

### Find records and find photos

Rights to a find record and rights to its photo are separate. Each record and
each photo carries its own licence, chosen by the person who posted it.

| Source | Kind | Licence | Commercial use | Republish | App needs it |
|---|---|---|---|---|---|
| GBIF download 0019331-260928105237408 | records | 10,224 CC BY, 1,499 CC BY-NC, 88 CC0 | Not for CC BY-NC records | With credit and the download DOI | No |
| iNaturalist, home area | records | 97 CC BY-NC, 8 CC BY-NC-ND, 7 CC BY, 3 CC0, 1 CC BY-SA, 46 with no licence | Only CC0 and CC BY | Records with no licence may not be republished | No |
| iNaturalist | photos | Set per photo, all rights reserved is allowed | Depends on each photo | Only open licences, with credit | No |
| GBIF | photos | Set per image by the publisher | Depends on each image | Only open licences, with credit | No |
| Bielefeld daily counts on Zenodo | records | CC BY 4.0 | Yes | With credit | No |
| Google Trends | timing sign | Google Terms of Service | Not stated | With the credit Data source: Google Trends | No |

Epic 1 downloaded no photos. The finds test the rules and never appear in the
app, so their licences do not limit it. If the app ever shows a find, it
should link to the record page and not copy the record or its photo. 46 of the
162 home area records from iNaturalist have no licence.

### Habitat, weather and map data

| Source | Licence | Commercial use | Credit or condition |
|---|---|---|---|
| Copernicus DEM GLO-30 and GLO-90 | Copernicus WorldDEM licence | Yes | Changed data must say "produced using Copernicus WorldDEM-30" with the DLR and Airbus copyright line and a no-liability sentence |
| Copernicus forest type 2018 | EU Regulation 1159/2013, free and open | Yes | Name the Copernicus Land Monitoring Service, state changes, imply no EU endorsement |
| SoilGrids 2.0 | CC BY 4.0 | Yes | Credit ISRIC. Not needed, too uncertain in P2 |
| Regione Toscana geology 1:10,000 | CC BY, version not stated | Yes | Credit Regione Toscana |
| Inventario forestale della Toscana | CC BY-SA 4.0 | Yes | Anything published from it uses CC BY-SA 4.0 too |
| OpenStreetMap through Geofabrik | ODbL 1.0 | Yes | Credit OpenStreetMap. A changed database stays ODbL |
| GADM 4.1 outlines | GADM licence | No, needs permission | Cannot be redistributed. Replace in the app |
| ERA5 through the Climate Data Store | CC BY 4.0 since 2 July 2025 | Yes | "Generated using Copernicus Climate Change Service information" and the year |
| Open-Meteo, all five APIs | CC BY 4.0 data, free plan non-commercial | Paid plan only | "Weather data by Open-Meteo.com" with a link where data is shown |
| MapLibre GL JS | BSD 3-Clause | Yes | Keep the licence notice |
| OpenFreeMap | Free service, ODbL map data | Yes | OpenFreeMap, OpenMapTiles and OpenStreetMap credit |

The Esri satellite photos and the Tuscany land cover map of 2019 were only
viewed for 6 squares in the P2 hand check. The app does not need them.

### Open-Meteo for a free app

The Open-Meteo terms define non-commercial use as Creative Commons does. They
give "private or non-profit websites or apps that do not have subscriptions or
advertising" as an example of non-commercial use. Websites with ads or
subscriptions, and use inside commercial products, are commercial.

A SporaMeteo app that is free, has no ads and has no subscriptions fits the
non-commercial example. Three cases are not covered by the terms: donations,
a company or VAT number running the app, and links that earn money. Ask
Open-Meteo in writing before launch and keep the answer.

The free plan allows 600 calls a minute, 5,000 an hour, 10,000 a day and
300,000 a month. The app would need about 1,036 calls a day, see below.

Paid plans, from the Stripe price table on 11 October 2026:

| Plan | Per month | Per year | Calls a month | APIs |
|---|---|---|---|---|
| API Standard | 29 euro | 319 euro | 1 million | Forecast, without past weather and stored forecasts |
| API Professional | 99 euro | 1,099 euro | 5 million | Adds past weather, forecasts published in the past and single runs |

Stripe adds tax at checkout. The page does not say whether the listed prices
include VAT. Plans renew each month or year and can be cancelled at any time,
effective at the end of the period. A request with more than 10 variables or
more than 14 days counts as several calls.

The app needs only the Forecast API: the last 30 days come from `past_days`
and the next 7 days from the forecast, in one request. Past weather and
forecasts published in the past were needed only to test the rules, which is
non-commercial research.

Free ways to get the same weather if the free plan stops fitting:

- Run the Open-Meteo server on our own machine. Its code is open source under
  AGPLv3 and it reads the free open data of ECMWF and the German weather
  service. Disk and processor needs were not measured.
- Download ECMWF forecasts directly. The Open-Meteo licence page lists them as
  CC BY open data.
- Use ERA5 from the Climate Data Store for past weather, free under CC BY 4.0.
  It runs 5 to 6 days behind, see A3, so it cannot cover the last days.

### Background map options

| Option | Cost | Limits | Commercial use | Notes |
|---|---|---|---|---|
| OpenFreeMap, used in P5 | Free | None on views or requests, no key | Yes | Donations only, no uptime promise. Main suspect for the iPhone freeze in P5 |
| Protomaps files on our own server | Server disk only | None, the file is ours | Yes, ODbL map data | The whole world is about 120 GB. `pmtiles extract` cuts out a region and fewer zoom levels |
| OpenStreetMap standard map images | Free | Heavy use, bulk download and offline use are banned. No uptime promise | Warned against | Not suited to a public app |
| MapTiler free plan | Free | 5,000 map sessions a month, then the map stops until next month | Not on the free plan | Flex plan 30 dollars a month without VAT for 25,000 sessions |
| Stadia Maps free plan | Free | 200,000 credits a month | No | Starter plan 20 dollars a month with commercial use |
| Esri World Imagery | Needs an Esri plan | Offline copies not allowed | Only under an Esri plan | Satellite photos. Terms outside Esri software not settled |
| Regione Toscana aerial photos | Free, CC BY | Not checked | Yes | Returned blank images for the P2 area |

At 100 users with 2 sessions a day the app makes about 6,000 map sessions a
month, more than the MapTiler free plan allows. OpenFreeMap and our own
Protomaps file are the two options with no limit. A small Protomaps file of
the home area would also test whether a lighter map stops the iPhone freeze.

## Size of the work for 10, 50 and 100 users

The app area is the home area of decision D4: Tuscany and the Apennine strip
of Emilia-Romagna, 28,205 km2. Each number is marked measured, with its run,
or estimated, with how it was worked out.

### Daily work

| Item | Value | Kind | Source |
|---|---|---|---|
| 500 m squares in the home area | 112,814 | measured | P6a run, square centres inside the outline |
| Weather cells of 9 km that touch the area | 392 | measured | P6a run |
| Weather cells of 25 km that touch the area | 83 | measured | P6a run |
| Open-Meteo calls a day, 9 km cells | 1,036 | estimated | 392 requests of 37 days and 8 variables, counted as 37/14 calls each |
| Time to download the weather, 9 km cells | about 7 minutes | estimated | P3b made 737 requests in 12.4 minutes, about 1 second each |
| Scores a day for 1 species and 8 days | 902,512 | measured | P6a run |
| Time to score one day with the D8 rules | 0.03 seconds | measured | P6a run on made-up weather |
| Time to write one day of scores | 0.08 seconds | measured | P6a run |
| Peak memory of the scoring run | 146 MB | measured | P6a run record |

The daily work is the weather download. Scoring takes less than a second. The
weather calls do not depend on the number of users.

The one-time build of the habitat grid for the whole area was not measured.
P2 built 504 squares in 399 seconds, most of it downloads. That build can run
on a laptop, and only the finished grid goes to the server.

### Disk and memory

| Item | Value | Kind | Source |
|---|---|---|---|
| Habitat grid of the home area | about 9 MB | estimated | P2 grid is 40 KB for 504 squares, about 80 bytes a square |
| One day of scores | 0.3 MB | measured | P6a run, Parquet file of made-up scores. Real scores repeat more and compress better |
| Scores kept online, 14 days | 4.2 MB | estimated | one day times 14 |
| Scores archive, one year | 0.11 GB | estimated | one day times 365 |
| Weather answers, one year | about 2.1 GB | estimated | P3b stored 11 MB for 737 requests, about 15 KB each, times 392 cells a day |
| Habitat source files for the whole area | under 1 GB | estimated | P2 sample: 744 KB of elevation and 1.4 MB of forest map for 126 km2, plus 186 MB for the regional inventory. Not needed on the server |
| Operating system and container images | about 3 GB | estimated | Typical size, not measured |
| Memory of the API | 35 to 42 MB | measured | P5 |
| Memory of the database, the operating system and the web server | about 0.6 GB | estimated | Typical idle use, not measured |

A server with 2 GB of memory and 20 GB of disk is enough. 4 GB and 40 GB
leave room for other projects on the same server.

### Map images

The P5 API sends squares as small compressed lists, so the app needs no map
images of its own. If the squares were served as ready-made map images
instead, the home area would need these images for each day and each day
ahead, measured in the P6a run:

| Zoom | Images of 512 pixels |
|---|---|
| 11 | 198 |
| 12 | 676 |
| 13 | 2,457 |
| 14 | 9,430 |

That is 12,761 images for one day and one day ahead, or about 102,000 a day
for 8 days ahead. The background map comes from OpenFreeMap and is not counted.

### Requests

All numbers are estimated from `reports/p6_users.csv`. Each active user opens
the app twice a day. A session sends 10 square requests, as the iPhone session
in P5 sent 9 in 25 seconds, and 2 other requests. A square request is 7.4 KB
compressed, measured in P5. One session in four loads the page and map
library, about 230 KB, with an empty cache.

| Active users | Sessions a day | API requests a day | API requests a month | Data sent a month |
|---|---|---|---|---|
| 10 | 20 | 240 | 7,200 | 0.08 GB |
| 50 | 100 | 1,200 | 36,000 | 0.38 GB |
| 100 | 200 | 2,400 | 72,000 | 0.75 GB |

At 100 users the server answers about one request every 36 seconds, each in
at most 11 ms, measured in P5. Data sent is under 1 GB a month. The cheapest
servers include 20 TB or more. Users do not change the server size or cost
at these numbers.

## Monthly costs

Prices checked on 11 October 2026. Italian VAT is 22 percent and is added
because a private person or a non-profit without a VAT number cannot recover
it. The domain and paid data licences are left out, as the issue asks.

### Servers with 2 processors, 4 GB of memory and 40 GB or more of disk

| Provider and plan | Contract | Without VAT | With VAT | Could be ordered | Backups | Source |
|---|---|---|---|---|---|---|
| Netcup VPS 500 G12.5, 64 GB | 1 month | 7.98 euro | 9.74 euro | Yes | Snapshots included | netcup.com order page |
| Netcup VPS 500 G12.5, 64 GB | 12 months | 6.94 euro | 8.47 euro | Yes | Snapshots included | netcup.com order page |
| Netcup VPS 500 G12.5, 64 GB | 24 months | 5.90 euro | 7.20 euro | Yes | Snapshots included | netcup.com order page |
| OVHcloud VPS-1, 40 GB | none, monthly | 4.49 euro | 5.48 euro | No, sold out in all 14 European locations for every contract length | Daily copy of the last 24 hours included | ovhcloud.com/it/vps configurator |
| OVHcloud VPS-1, 40 GB | 12 months, 45.72 euro paid in advance | 3.81 euro | 4.65 euro | No, sold out in all 14 European locations for every contract length | Daily copy of the last 24 hours included | ovhcloud.com/it/vps configurator |
| Hetzner CX23, 40 GB, with IPv4 | none, billed by the hour | 5.99 euro | 7.31 euro | No, marked unavailable | 20 percent extra, 1.10 euro, for 7 daily copies | costgoat.com, 5 September 2026 |

Netcup charges no setup fee. Its servers are placed in Austria, Germany or the
Netherlands. Choosing one city costs 1.07 euro a month more. The contract runs
for the chosen term. The notice period to cancel was not checked.

OVH also offers a 6-month contract at 5 percent off. Its 12-month contract
renews for another 12 months unless the renewal is turned off before the end.

Hetzner raised cloud prices on 1 April and 15 June 2026, from 3.99 to 5.49
euro for CX23, according to northflank.com.

### Off-site backup

| Option | Price | Fits | Source |
|---|---|---|---|
| Backblaze B2 | First 10 GB free, then 6.95 dollars per TB a month | Yes. Scores, grid and database add about 0.12 GB a year | backblaze.com |
| Hetzner Storage Box BX11, 1 TB | 3.20 euro without VAT, 3.90 euro with VAT, no minimum term | Yes, far more space than needed | whtop.com, February 2026. Hetzner's page showed no amount |

### Scenarios

| Scenario | Monthly with VAT | Notes |
|---|---|---|
| Netcup VPS 500 for 24 months and Backblaze B2 free | 7.20 euro | Cheapest that could be ordered. Inside the target |
| Netcup VPS 500 for 12 months and Backblaze B2 free | 8.47 euro | 0.47 euro above the target |
| Netcup VPS 500 month by month and Backblaze B2 free | 9.74 euro | 1.74 euro above the target. No long contract |
| OVH VPS-1 for 12 months and Backblaze B2 free | 4.65 euro | Sold out in Europe |
| OVH VPS-1 month by month and Backblaze B2 free | 5.48 euro | Sold out in Europe |
| Hetzner CX23 and Backblaze B2 free | 7.31 euro | Marked unavailable |
| Hetzner CX23 with Hetzner backups | 8.65 euro | Marked unavailable. 7.09 euro without VAT |

### More memory or disk

| Plan | Processors, memory, disk | With VAT | Change from the 4 GB plan |
|---|---|---|---|
| Netcup VPS 1000 G12.5, 1 month | 4, 8 GB, 128 GB | 17.09 euro | plus 7.35 euro |
| Netcup VPS 1000 G12.5, 12 months | 4, 8 GB, 128 GB | 14.86 euro | plus 6.39 euro |
| Netcup VPS 1000 G12.5, 24 months | 4, 8 GB, 128 GB | 12.63 euro | plus 5.43 euro |
| OVH VPS-2, 12 months | 4, 8 GB, 75 GB | 8.80 euro | plus 4.15 euro. Sold out in Europe |
| Hetzner CX33 | 4, 8 GB, 80 GB | 10.97 euro | plus 3.66 euro |
| Hetzner CPX22 | 2, 4 GB, 80 GB | 24.39 euro | The closest plan to CX23 that cloudhim.com lists as orderable |

The app needs less than 1 GB of memory and about 5 GB of disk, so the 4 GB
plans are enough. Doubling memory costs 3.66 to 7.35 euro more a month.

## Blockers

None stops a free service. These limits apply:

- GADM outlines cannot be shipped. ISTAT publishes Italian outlines under
  CC BY 3.0 IT according to an ISTAT volume of 2018. The licence of the
  outline files themselves was not confirmed. OpenStreetMap borders under
  ODbL are the other choice.
- The free Open-Meteo plan holds only while the app stays non-commercial.
  If it changes, the Standard plan costs 29 euro a month and breaks the 5 to
  8 euro target, or the Open-Meteo server must run on our own machine.
- On 11 October 2026 OVH VPS-1 and VPS-2 were sold out in every European
  location, and Hetzner marked CX23 unavailable. Netcup was the only one of
  the three that could be ordered. Its month-by-month price, 9.74 euro, is
  above the target, so staying inside 8 euro means a 24-month contract or
  waiting for OVH or Hetzner stock.
- OpenFreeMap has no uptime promise. Our own Protomaps file is the fallback.

## Costs not covered

- The domain.
- An Open-Meteo paid plan, 29 or 99 euro a month, if the app becomes
  commercial or needs past weather in production.
- Running our own Open-Meteo server. Its disk and processor needs were not
  measured.
- Disk and transfer for our own Protomaps map, if OpenFreeMap stops.
- Cloudflare or another service in front of the server. Its free plan was not
  checked.
- Email, legal advice on licences, and the time to run the service.
- The one-time habitat build for the whole area, which was not measured.
- Future price rises. Hetzner raised prices twice in 2026.

## Sources checked

- Open-Meteo terms, licence and pricing pages, open-meteo.com/en/terms,
  /en/licence and /en/pricing, and the Stripe price table they load.
- GBIF data user agreement and licensing guides, through search results,
  because gbif.org blocked automated reads.
- iNaturalist API limits, through the iNaturalist forum and the pyinaturalist
  guide, because inaturalist.org blocked automated reads.
- GADM licence, gadm.org/license.html.
- Copernicus Land Monitoring Service data policy, land.copernicus.eu.
- Copernicus DEM licence, the WorldDEM-30 licence PDF on the Copernicus data
  space.
- ERA5 licence, the ECMWF forum notice of the CC BY change on 2 July 2025.
- Regione Toscana catalogue records for the geology database.
- Zenodo record 20591123.
- Geofabrik download page.
- OpenStreetMap tile usage policy, operations.osmfoundation.org.
- OpenFreeMap, MapTiler, Stadia Maps and Protomaps sites.
- OVHcloud and Netcup server pages, costgoat.com and northflank.com for
  Hetzner, Backblaze B2 pricing, whtop.com for the Hetzner Storage Box.

## Backup, restore and moving servers

Issue #12 adds this section.
