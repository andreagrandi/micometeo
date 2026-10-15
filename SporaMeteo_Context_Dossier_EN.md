# SporaMeteo — Research, Context and Decision Dossier

**Version:** 0.1 — October 10, 2026  
**Status:** Research/background document; **not** binding product scope  
**Working name:** **SporaMeteo** (preferred, but **trademark and domain availability have NOT been confirmed**)  
**Operational companion:** [`SporaMeteo_PRD_Epic_1_Validation_EN.md`](./SporaMeteo_PRD_Epic_1_Validation_EN.md)

> **Purpose:** Preserve the research, competing products, data sources, architectural options, price observations, tradeoffs, assumptions, decisions and open questions discussed during discovery. When creating implementation tickets, use **only the Epic 1 PRD as the scope authority**. This dossier is background and does not authorize implementing every feature mentioned.

## 1. Vision, audience and governing principles

SporaMeteo is a potential **free, mobile-first mushroom-foraging web app** showing where and when environmental conditions favor fruiting of particular mushroom species. The highest-value question is **“Where should I go looking for mushrooms today?”** Seven-day forecasts are useful but secondary to a defensible assessment based on **7–30 days of observed/reconstructed preceding weather**.

The app must not claim to know actual secret mushroom spots or guarantee a find. Distinguish **habitat suitability** (mostly static), **current fruiting conditions** (dynamic), **future forecasts** (more uncertain) and **recorded occurrences** (subject to human sampling bias). A 0–100 suitability index is **not** automatically a calibrated percentage chance of finding mushrooms.

Agreed constraints and decisions:

- **Validation first:** Epic 1 consists of bounded PoCs intended to falsify or corroborate key assumptions. **No large-scale implementation** or multi-Epic backlog until a GO/PIVOT/NO-GO decision.
- **Lightweight models:** benchmark simple baselines, documented ecological rules, logistic regression and perhaps LightGBM; each training run capped at **30 minutes**, ideally seconds/minutes on commodity CPUs. No mandatory GPU.
- **Honest retrospective testing:** join dated/geolocated occurrence records with habitat and **weather actually available at the relevant point in time**; hold out future years/locations and avoid leakage.
- **Web-first, mobile-first:** genuinely usable on a phone; independent, reusable backend API for a possible later native iOS client; PWA optional.
- **Predictable small costs:** ultimately deploy alongside other low-traffic projects on a cheap shared VPS, separate from the existing BookCorners VPS. **Do not buy hosting or a domain in Epic 1.**
- **Portability matters more than 100% uptime:** reproducible hosting, tested backup/restore, preprovisioning a destination server, fast DB cutover/DNS or Cloudflare origin change, rollback, agent-run scripts and human approval for production operations.
- **Initial geography:** Tuscany, particularly the Pistoia Apennines (beech, chestnut and oak forests); expand only if observation coverage demands it.
- **Initial target:** porcini; clarify whether one species or a carefully defined group (*Boletus edulis*, *B. aereus*, *B. reticulatus*, *B. pinophilus*). Future possibilities: chanterelles, Caesar's mushrooms, St. George's mushrooms and parasol mushrooms, with taxon-specific ecological rules.

## 2. Competitive landscape — Italy

**Evidence standard:** The following capabilities were taken from public product listings and descriptions, not complete hands-on feature audits. Vendor accuracy claims are not independent validation. All prices are dated observations subject to store, tax, tier, promotional and regional changes; **re-check before business decisions**.

| Product | Links | Advertised features | Free tier and reported paid prices | Caveats |
|---|---|---|---|---|
| **Mappa dei Funghi / The Mycologist** | https://mappadeifunghi.it/ ; https://mappadeifunghi.it/mappe-complete/ | Habitat and daily fruiting-index maps by species/area; weather, soil, woods and multi-day trends; vendor cites many environmental variables | Free demo; **from €14.90/year per map** | Per-map price, not necessarily nationwide all-species access; validate accuracy claims independently |
| **FungRadar** | https://it.fungradar.com/previsioni | Regional/municipal forecasts, favored species, index and seven-day trend; publicly identifies environmental open-data inputs | Public forecast pages accessible for free; additional premium price **unverified** | Verify actual map granularity and whether high-resolution details are paywalled |
| **Geoticket** | https://geoticket.it/download-app ; https://apps.apple.com/it/app/geoticket/id1475238989 | Smart maps, saved places and territorial collection permits | Free download; earlier research indicated **Plus €24.99/year or €19.99/month**; **store recheck required** | Validate exactly which mapping features remain free |
| **Semaforo dei Funghi / Funghi Magazine** | https://play.google.com/store/apps/details?id=com.funghimagazine.semaforodeifunghi | Weekly national growth-conditions map, observations and mushroom-related information | Android download listed as free; any paywall **not confirmed** | Broad map rather than necessarily daily, per-forest/species ranking |
| **ShroomCast** | https://apps.apple.com/it/app/shroomcast-previsioni-funghi/id6748039058 | Per-forest cards with tree type, soil, previous 14 days' rain, species forecast, maps, alerts and claimed 14-day horizon | Free download; Premium **€5.99/month**, **€12.99/quarter**, **€24.99/year** | Close functional competitor; quality and data coverage need independent testing |
| **MycoMap Italia** | https://mycomap.it/ ; https://apps.apple.com/it/app/mycomap/id6814987192 | Daily growth index, maps, history, track logging and ecological explanations | **Guest:** coarse-area map with limited zoom; **free login:** notebook; **Pro:** point detail, history, likely species, alerts. **€1.49/7 days; €4.49/month listed as IAP (description also says €4.99); €23.99/year; €50 supporter** | Crucial correction: limited free map exists; that does **not** mean fully free granular forecasts |
| **Mycel** | https://apps.apple.com/it/app/mycel-mappa-dei-funghi/id6771742569 | Mushroom maps and Pro features | Earlier price observations **€1.99/month, €17.99/year, €44.99 lifetime**; **needs rechecking** | Not reconfirmed during final documentation |
| **Catacapea** | https://apps.apple.com/it/app/catacapea/id6817034469 | Mushroom forecasting application | Earlier observations: **7-day trial, €59.99/year Basic, €119.99/year Pro**; **needs rechecking** | Verify current listing and entitlements |
| **Mondo Funghi** | https://mondofunghi.it/faq/ ; https://apps.apple.com/it/app/mondo-funghi/id6764337695 | Species guide, saved places, diary, historical/predictive Premium functionality, photo-based identification | Free limited tier; **complete study €4.99 one-time; Premium €2.99/month or €12.99/year; €29.99 lifetime**, upgrade €24.99 | Wider mushroom assistant, not exclusively a forecasting service |

**Market implication:** Free alternatives already exist, including regional forecast pages and restricted-access heatmaps. The opportunity is **not simply “nobody offers this for free.”** The hypothesis is that **free, precise, taxon-specific, explainable, present-day local forecasting, with transparent evaluation** could stand apart. Inspect free offerings of FungRadar, MycoMap, Semaforo and ShroomCast before claiming differentiation.

### Naming collisions: MycoMap / MicoMap

Different projects use near-identical names, and they should **not** be assumed to share ownership:

- **MycoMap.org** — https://mycomap.org/ — collaborative fungal biodiversity initiative associated with Stephen D. Russell; a project listing reports founding in **2015**. The displayed founding year is distinct from product launch dates.
- **Mycomap Android (Swiss)** — https://play.google.com/store/apps/details?id=com.kohrtetelle.mycomap — associated with Thierry Beuret; a **July 2025 update** was observed, but its initial launch year was not independently established.
- **MicoMap Android (Spain)** — https://play.google.com/store/apps/details?id=com.micomap.app — associated with Nexther Apps/Jose Maria Garcia Soler; an **February 2026 update** was observed, not necessarily the original launch.
- **MycoMap Italia** — https://mycomap.it/ — associated with Simone Lorenzoni; a **September 2026 privacy policy** was observed, not a confirmed founding date.

For brand confusion and search discoverability, avoid **MicoMap/MycoMap** regardless of any unsettled trademark legal status. Treat company/developer and chronological details as historical listing observations requiring independent reconfirmation before publication.

## 3. Data-source inventory

### 3.1 Real mushroom occurrences

- **GBIF** — https://www.gbif.org/ ; occurrence API https://techdocs.gbif.org/en/openapi/v1/occurrence — observations with taxonomy, date, location, georeferencing metadata and per-record licensing. Enables documented download subsets. Records may overlap with original providers.
- **iNaturalist** — https://www.inaturalist.org/ ; API https://www.inaturalist.org/api ; license explanation https://help.inaturalist.org/en/support/solutions/articles/151000173511 — identification, date, images and coordinates. Some research-grade records also appear through GBIF; deduplicate.
- **Licensing:** many iNaturalist observations/photos default to **CC BY-NC**; do not assume commercial redistribution. The observation's license may differ from the **photo's license**. Obscured coordinates cannot validate a 250 m spatial score. Retain record-level source and license metadata; claimed GPS precision does not guarantee accuracy.
- **Private/community records:** local mushroom associations and opt-in users may someday provide additional observations. No automatic entitlement to proprietary datasets or private foraging locations.
- **Scientific issues:** presence-only reporting; strong visitor/road/trail/season/weekend biases; mistaken taxonomic identification; recorded observation date is not necessarily the onset of fruiting.

### 3.2 Forests, trees, habitats and land cover

- **Copernicus Land Monitoring Service** — https://land.copernicus.eu/en/products/high-resolution-layer-forests-and-tree-cover — canopy/forest/broadleaf-conifer layers, some at **10 m**. Broadleaf versus conifer is **not** reliable 10 m species-level mapping of beech versus chestnut.
- **ESA WorldCover** — https://esa-worldcover.org/ — global land-cover classes useful for initial habitat masks, not exact tree species.
- **JRC European Atlas of Forest Tree Species** — https://forest.jrc.ec.europa.eu/en/european-atlas/ — modeled tree ranges/presence; check spatial scale, publication period and meaning of probabilities.
- **2026 European forest-type research dataset** — mentioned in prior exploration as 14 forest categories with species probabilities; **verify the precise paper, dataset link, availability and licensing before relying on it**.
- **Tuscany Region GEOscopio** — https://www.regione.toscana.it/geoscopio — regional thematic maps, WMS/WFS, geology, woodland, land use, elevation and possible detailed forest classes. Validate endpoints and license **per layer**.
- Other potential sources: regional woodland inventories, national forest inventory and OpenStreetMap land-use/road/trail attributes (not necessarily reliable tree-species classification).

### 3.3 Soil, geology and topography

- **ISRIC SoilGrids** — https://isric.org/explore/soilgrids ; https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_02.html — global ~**250 m** modeled soils with pH, sand/silt/clay, organic carbon and multiple depths/uncertainties; **CC BY 4.0**. Prefer download/WCS/raster extracts when the REST API is unavailable.
- **Tuscany GEOscopio soils/geology** — https://www.regione.toscana.it/geoscopio — including detailed geological mapping around 1:10,000 where offered; verify each layer's reuse permissions and required attribution.
- **Elevation/DEM** — https://dataspace.copernicus.eu/ and regional terrain models. Derive elevation, slope, aspect, drainage/topographic indicators.
- **Crucial distinction:** geology, modeled pH and *today's* soil moisture are separate variables. A visually fine grid does not improve precision beyond the coarsest meaningful input.

### 3.4 Observed weather, reanalysis, current forecasts and archived forecast runs

- **Open-Meteo Forecast API** — https://open-meteo.com/en/docs — rainfall, temperature, humidity, modeled soil conditions and forward forecasts.
- **Historical Weather API** — https://open-meteo.com/en/docs/historical-weather-api — historic/reanalysis data to pair observations with antecedent conditions.
- **Historical Forecast API** — https://open-meteo.com/en/docs/historical-forecast-api — historical data produced from forecasts, but **do not assume this returns the exact complete seven-day forecast issued seven days earlier**.
- **Previous Runs API** — https://open-meteo.com/en/docs/previous-runs-api — forecasts at specified lead times useful for 1–7 day skill evaluation.
- **Single Runs API** — https://open-meteo.com/en/docs/single-runs-api — select a real historic model run; particularly relevant to strict point-in-time backtesting when coverage and license allow it.
- **ECMWF, ERA5, ERA5-Land** — https://www.ecmwf.int/ ; https://cds.climate.copernicus.eu/ — reanalysis for weather/soil features; **not an archive of forecasts that would have been known at the earlier date**.
- **Local weather networks:** Tuscany rain gauges and regional meteorological/hydrological services, possibly ARPAT-related resources. Determine real APIs, coverage and licenses; alpine/apennine topography may make local observations valuable.
- **Licensing and cost warning:** Open-Meteo's free API is described as **non-commercial** (https://open-meteo.com/en/pricing). An app that is free to its users is not automatically classified as non-commercial. Commercial historical access may require more expensive plans than basic real-time forecasts. Check alternatives such as openly downloadable data or permitted self-hosting.

### 3.5 Access, permits and restrictions

- **Tuscany Region** — https://www.regione.toscana.it/ — collection permissions, regional regulations, parks, local restrictions and African swine fever measures; combine authoritative boundaries and dates.
- **OpenStreetMap** — https://www.openstreetmap.org/ — roads, trails, land use; other topographic basemaps such as OpenTopoMap. Check individual tile-server usage conditions. Mapping a forest does **not** certify that collection/access is legal.
- Do not label a place *permitted* merely because a restriction is missing from a dataset. Present ecological forecasts and legal restrictions as separate layers with sources and update dates.

## 4. Scientific hypothesis and modeling

### 4.1 Two separate prediction problems

1. **Today / nowcast:** combine static habitats with preceding **7, 14, 21 and 30 days** of rainfall, temperature and modeled soil moisture. Update daily. Explore rainfall lags, antecedent drought, evapotranspiration and ground temperature by species.
2. **Tomorrow through +7 days:** combine the same features with forecasts **actually available when the prediction is issued**. Uncertainty generally grows with the forecast horizon.

“40 mm of rain fell” alone is not enough: timing, soil baseline, species, substrate, elevation and season may change what it means. Biological thresholds must come from defensible literature or data, not arbitrary numbers presented as scientific certainty.

### 4.2 Deterministic scores versus calibrated probability

An expert rule system can produce a **0–100 favorability index**, combining habitat, moisture, temperature and season with non-linear interactions. **85/100 does not mean an 85% chance of finding a mushroom.** A calibrated chance requires an explicitly defined outcome (e.g., one find in a specified survey effort), representative labeled sampling and actual absences or a valid survey design. Deterministic formulas can also be calibrated statistically; ML is not required merely to produce numbers.

### 4.3 Candidate models

- Spatially neutral/random and seasonal baselines; simple **recent rainfall** baseline.
- Documented, interpretable expert ecological rules combining static and time-varying features.
- Logistic regression on tabular temporal/geographic features.
- LightGBM/gradient-boosted trees **if** sample size and independent evaluation support it.
- CPU execution, reproducible training with a hard **30-minute-per-run** limit; no mandatory GPU. Reject ML if it does not materially outperform simpler models.

### 4.4 Honest evaluation and known limits

- Evaluate **ranking of areas associated with reported finds** against carefully sampled background or pseudo-absences, controlling where possible for access, season, habitat and observer effort. Do **not** present ordinary classification accuracy as true presence/absence accuracy when only presence data exist.
- Candidate metrics: share of observed finds captured in the top 10% or 20% of *comparable* land by model rank; lift against random and weather-only baselines; ranking metrics and bootstrap confidence intervals.
- Hold out **years and geographic blocks**, avoiding nearby and duplicate points spread between train and test. Investigate trail proximity, population density, accessible places and known popular sites.
- Backtest date X only with weather/history/forecast information **available by date X**. For a +7-day test, use a real archived run from X−7 days; ex-post ERA5 is not a valid stand-in.
- Report uncertainty in coordinates, dates, taxonomy, licensing, deduplication, historical coverage and sample size.
- **No recorded observation ≠ no mushroom.** Initial evaluation estimates observation-conditioned ranking value, not a forager's calibrated success probability.
- An illustrative benchmark—**not an established result**—could be “68% of recorded finds captured in the top 20% of ranked area.” Define success criteria **before** seeing the results.

## 5. Hypothetical user experience — after PoC, NOT authorized backlog

- Phone-friendly interactive heatmap with species and date filters (**−30 through +7 days**), user geolocation and a bottom sheet showing score and explanation.
- Separate maps for **habitat**, **conditions today** and **future forecast**, with observation dates, source quality and uncertainty visible.
- Optional private saved locations and alerts when conditions improve; coordinates never shared without consent.
- Permit/restriction overlays separate from ecological suitability.
- A native iOS application might later reuse the same API. Offline maps and photo recognition are **not** part of Epic 1.
- **Safety:** never guarantee edibility or identification from a photo; direct users to qualified mycological inspection services for consumption decisions.

## 6. Potential architecture — hypothesis, not commitment

- **Frontend:** responsive mobile-first web/PWA using MapLibre GL JS; React or Astro possible, not mandated.
- **API:** independent versioned REST API (`/api/v1/...`), potentially FastAPI/Python or another lightweight stack.
- **Operational data:** PostgreSQL + PostGIS for spatial queries; Python/GDAL/Rasterio/GeoPandas for geoprocessing. Avoid loading every massive source raster or all weather history into the live relational database.
- **Static geography batch:** infrequent preparation of an initial **250–500 m grid** with habitat, forest, soils, geology and topographic features. Model input resolution and forecast confidence matter more than rendered pixel size.
- **Daily batch:** weather import and calculated features/scores by cell/species/date; precomputed overlays/tiles behind a cache/CDN.
- **Serve precomputed results, not training per request.** ML training can take place on a laptop/CI/occasional batch; do not require a GPU/large production server.
- **Scope/data placement:** start around Pistoia, then Tuscany; keep bulky downloadable science artifacts out of the production operational database.

## 7. Hosting, prices and operations

### 7.1 Decisions

- **Do not buy a VPS or domain during Epic 1.** Prototype locally and measure actual usage.
- After validation, use a **multi-project small VPS** with application isolation; separate databases inside one PostgreSQL instance may conserve RAM. Keep the existing BookCorners host independent.
- **100% availability is not required:** a short downtime is acceptable. Restoreability, automation, backup and migration matter more than elaborate high availability.
- Prefer Docker Compose plus Caddy/Traefik; optionally Ansible for provisioning; persistence outside app containers; off-site backups.
- Migration: provision/test destination first, freeze writes, final DB dump/restore, smoke-test, switch DNS/Cloudflare origin, monitor and prepare rollback. **DNS/origin cutover is not strictly instant or atomic** because caches and connections can still reach the old host. Keep old origin read-only as appropriate and avoid divergent writes.
- Agents should execute **version-controlled runbooks/scripts** (`prepare`, `check`, `cutover`, `rollback`) with least-privilege credentials, approvals for production changes and logs—not invent an ad hoc destructive migration procedure.

### 7.2 Hosting-provider price notes

**Price snapshot from October 10, 2026. Not binding quotes.** Check customer-country VAT, activation fees, contract length, promotion expiry, IPv4 charges, inventory and renewals before purchasing.

| Provider / plan | Resources | Observed rate / qualification |
|---|---|---|
| **netcup VPS piko G11s** | 1 vCore, 1 GB RAM, 30 GB SSD | **€1.84/month including 19% German VAT**; purely mathematical equivalent ~**€1.89 at 22% Italian VAT** assuming same net price |
| **netcup VPS nano G11s** | 2 vCore, 2 GB RAM, 60 GB SSD | **€3.08/month including German VAT**; analogous Italian VAT estimate ~**€3.16** |
| **netcup VPS Lite 1 G12s** | 2 vCore, 4 GB RAM, 80 GB SSD | **€4.88/month including German VAT**; analogous Italian VAT estimate ~**€5.00** |
| **netcup VPS Lite 2 G12s** | 4 vCore, 8 GB RAM, 160 GB SSD | **€7.92/month including German VAT**; analogous Italian VAT estimate ~**€8.12** |
| **netcup standard VPS** | e.g. 4 GB RAM, 64 GB disk | A separate generally more expensive line. **Do not confuse standard with VPS Lite.** |
| **Hetzner CX23 / CAX11 / CX33** | 4–8 GB depending on plan | Previously discussed indicative **€5.49 / €5.99 / €8.49 plus VAT and sometimes IPv4**; verify latest list and availability |
| **Aruba Cloud entry VPS** | 1–2 GB plans | Earlier snapshot around **€3.04 / €5.48 including Italian VAT**; recheck |
| **OVHcloud VPS-1** | ~2 cores, 4 GB, 40 GB | Earlier snapshot **€3.81 ex VAT / ~€4.65 with Italian VAT**; user previously experienced repeated account verification-email failures, so **not favored** |
| **IONOS entry VPS** | Small plans | Frequently promotional €2–4 introductory figures, sometimes higher recurring rate and setup; assess **recurring** costs only |

**Correct netcup catalog:** https://www.netcup.com/en/server/vps-lite . Its observed catalog figures **already included 19% German VAT**. Earlier informal nano/Lite estimates of €3.78/€6.01 were misleading if framed as a simple Italian-VAT adjustment; do not reuse without explaining taxation and dates.

Target is roughly **€3–6/month shared VPS** if feasible, or **€5–8/month including shared hosting/backup** as a provisional objective, **excluding domain and commercial weather/data licenses**. 2 GB might be constrained with PostGIS and multiple services; 4 GB may suffice but **must be measured**. Keep heavyweight raster processing off-host if it threatens stability.

For a later comparison with BookCorners, inspect `free -h`, `docker stats --no-stream`, `df -h`, `docker system df`. Its observed average CPU at 1–2% does **not** prove the RAM is underused.

### 7.3 Costs/risks not captured by the VPS sticker price

- **Open-Meteo licensing:** its free plan is for noncommercial use; production/commercial historic or ensemble access may require higher paid tiers than the basic plan. This could cost more than the VPS even with zero visitors. Assess open download/self-host alternatives where licensing allows.
- **Base map tiles:** commercial use, attribution, third-party tile server policies and request charges.
- **Data footprint:** raster source files, cached overlays, archived historic model outputs, off-site backups, domain renewal, outbound traffic.
- **API metering:** long time windows and large variable/location sets may count as more than one basic API request; model actual workload rather than HTTP count alone.
- Do not require the live VPS to host every source scientific dataset and intermediate training artifact.

## 8. Product name and positioning

**Product name: SporaMeteo.** It combines *spora*, the Italian word for spore, and *meteo*, weather. The domain `sporameteo.com` is registered.

Other discussed candidates: **Sporabosco**, **Sporasentiero**, **MycoBussola**, **Fungometria**. Names with potential collisions needing avoidance/checks: **Micovia**, **Sporavia**, **FungiTrail**. **MycoMap/MicoMap is already used by several independent mushroom-related products** and should be avoided.

**Trademark clearance has not been verified.** Before launch, check Registro .it (https://www.nic.it/it), ICANN (https://lookup.icann.org/), EUIPO (https://www.euipo.europa.eu/), UIBM (https://uibm.mimit.gov.it/), phonetic similarities and app stores. **No domain purchase in Epic 1.** Technical repository placeholder could be `mushroom-forecast`.

## 9. Business constraints and differentiation

- Expect only **dozens of initial users**, not thousands or immediate revenue.
- Free-to-user does not mean cost-free. Evaluate the fixed cost at **zero users** plus marginal costs for expanded geography/species/audience.
- Possible differentiation: **daily local nowcast per forest/species**, reasons for the score, uncertainty/transparent methodology, independent backtesting and genuinely private places.
- Do not copy proprietary map layers, private spotting locations, competitors' visual assets or unlicensed observation photographs.

## 10. Top open questions and risks

1. How many genuinely useful *Boletus* observations are available in Tuscany with credible dates, sufficiently precise coordinates, reliable identification, compatible licensing and deduplication?
2. How much do trails, visitor activity and well-known spots distort the target distribution?
3. Do regional forest layers actually discriminate beech/chestnut/oak forests around Pistoia well enough?
4. What is the real spatial value of weather data in mountain terrain? Are 250 m cells falsely precise?
5. Which historical weather values and **forecast vintages** were knowable on date X? What do those data cost to use commercially?
6. Does any ranking outperform chance, seasonality and rainfall-only heuristics on a blinded temporal/geographic holdout?
7. Can a free public product lawfully use its observations, meteorological data, forest layers and basemaps without unaffordable subscriptions?
8. How much CPU, RAM, disk and network are needed for updates and **hosting beside other projects**?
9. Is the SporaMeteo name legally/technically usable? How should local permits and temporary restrictions be represented?

## 11. When planning the next roadmap is allowed

**Epic 1** must produce executable artifacts, empirical results, measurements and decisions; hypotheses are allowed to fail. Review the final **GO / PIVOT / NO-GO** report first. **Only then** scope and ticket later product Epics. The companion PRD defines acceptance criteria and dependencies.

## 12. Reference links

**Competitor products**
- https://mappadeifunghi.it/ ; https://mappadeifunghi.it/mappe-complete/
- https://it.fungradar.com/previsioni
- https://geoticket.it/download-app ; https://apps.apple.com/it/app/geoticket/id1475238989
- https://play.google.com/store/apps/details?id=com.funghimagazine.semaforodeifunghi
- https://apps.apple.com/it/app/shroomcast-previsioni-funghi/id6748039058
- https://mycomap.it/ ; https://apps.apple.com/it/app/mycomap/id6814987192
- https://apps.apple.com/it/app/mycel-mappa-dei-funghi/id6771742569
- https://apps.apple.com/it/app/catacapea/id6817034469
- https://mondofunghi.it/faq/ ; https://apps.apple.com/it/app/mondo-funghi/id6764337695

**Weather, habitat, observations**
- https://open-meteo.com/en/docs ; https://open-meteo.com/en/pricing
- https://open-meteo.com/en/docs/historical-weather-api
- https://open-meteo.com/en/docs/historical-forecast-api
- https://open-meteo.com/en/docs/previous-runs-api
- https://open-meteo.com/en/docs/single-runs-api
- https://cds.climate.copernicus.eu/
- https://land.copernicus.eu/en/products/high-resolution-layer-forests-and-tree-cover
- https://esa-worldcover.org/
- https://forest.jrc.ec.europa.eu/en/european-atlas/
- https://isric.org/explore/soilgrids ; https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_02.html
- https://www.regione.toscana.it/geoscopio
- https://www.gbif.org/ ; https://techdocs.gbif.org/en/openapi/v1/occurrence
- https://www.inaturalist.org/ ; https://www.inaturalist.org/api
- https://help.inaturalist.org/en/support/solutions/articles/151000173511
- https://www.openstreetmap.org/

**Hosting and naming**
- https://www.netcup.com/en/server/vps-lite
- https://www.netcup.com/en/server/vps
- https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/
- https://www.arubacloud.com/vps/
- https://www.ovhcloud.com/it/vps/
- https://www.nic.it/it ; https://lookup.icann.org/ ; https://www.euipo.europa.eu/ ; https://uibm.mimit.gov.it/

---
**Agent rule:** Do not turn post-PoC ideas, providers, proposed models or historical prices in this dossier into binding implementation decisions. Use the separate PRD to create **only Epic 1** tickets and explicitly document unvalidated assumptions.
