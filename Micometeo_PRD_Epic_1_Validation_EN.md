# Micometeo — Product Requirements Document: Epic 1, Feasibility & Validation

**Version:** 1.0 — October 10, 2026  
**Status:** Ready to break down into issues and execute PoCs  
**Working name:** Micometeo (provisional; trademark and domain availability unverified)  
**Background:** [`Micometeo_Context_Dossier_EN.md`](./Micometeo_Context_Dossier_EN.md)  
**Scope authority:** This PRD, not the background dossier.

## 1. Objective

**Before building the product**, establish through small, reproducible, measurable experiments whether a free, mobile-first web application can credibly identify areas whose environmental conditions favor fruiting of particular mushroom species. Prioritize **“Where should I look today?”**, followed by forecasts up to seven days ahead.

**Do not** create a large backlog of Epics before completing Epic 1. Deliver one evidence-based **GO / PIVOT / NO-GO** report at the end; only then scope subsequent Epics.

### Non-negotiable principles

- **Validation first:** turn critical assumptions into falsifiable tests, not accepted requirements.
- **Bounded cost and effort:** small experiments; each ML training run must complete within **30 minutes** on ordinary CPU hardware, with no mandatory GPU.
- **Legitimate, reproducible data:** record URLs, licenses, versions, retrieval dates, query parameters and filters; do not scrape in violation of service terms.
- **Scores are not probabilities:** a 0–100 suitability score is not the probability of finding a mushroom without calibration against defined, observable outcomes.
- **Prevent data leakage:** distinguish observed/reanalyzed weather from forecasts actually issued before the target date. Never incorporate future conditions or test observations in training.
- **Web-first and mobile-first:** build toward an API reusable by a future iOS client, but Epic 1 requires only a minimal technical spike, not a complete application.
- **No purchases:** no domain, VPS, paid API or subscription in Epic 1 without a separate explicit decision.
- **Portability:** target a cheap shared Linux VPS, migratable database and repeatable deployment; 100% uptime is not a requirement.

## 2. Assumptions to test

| ID | Hypothesis | Minimum evidence | PoC |
|---|---|---|---|
| A1 | Enough trustworthy, dated, geolocated porcini observations exist | Counts by source, taxon, year, spatial precision, duplicates, geography and documented limitations | P1 |
| A2 | Tree and habitat data are useful at regional scale | Reproducible GIS sample, attributes, coverage and **effective** resolution | P2 |
| A3 | Historic weather supports a “today” assessment | Up to 30 days of preceding features by date/location, with lineage and cost | P3 |
| A4 | A +7-day forecast can be evaluated without hindsight | Availability, archive coverage and limits of **actual past forecast runs** | P3 |
| A5 | Environmental signals outperform basic heuristics | Time- and geography-held-out benchmark with uncertainty and baselines | P4 |
| A6 | Precomputed results can be served on mobile efficiently | Minimal local API/map, mobile usability, payload and memory measurements | P5 |
| A7 | Licensing and operating costs allow a free small-scale service | Source/license matrix, cost scenarios and local backup/restore/portability test | P6 |

Do **not** invent performance targets after seeing results. A negative or inconclusive experiment is still useful evidence.

## 3. Experiment boundaries

- **Initial geography:** Pistoia and the Tuscan Apennines. Expand to Tuscany or adjacent regions **only if** the valid observation sample is inadequate; document the scope change.
- **Initial taxon:** porcini. Explicitly decide whether data represent individual species (*Boletus edulis*, *B. aereus*, *B. reticulatus*, *B. pinophilus*) or a properly defined aggregate; avoid unintended taxonomic mixing.
- **Time period:** multiple years/seasons where available; reserve later periods for testing.
- **Initial spatial cells:** approximately 250–500 m, subject to actual input resolution; do not imply false spatial accuracy.
- **Candidate sources:** GBIF/iNaturalist; Tuscany GEOscopio; Copernicus Land Monitoring; SoilGrids; Open-Meteo Historical Weather, Historical Forecast, Previous Runs and Single Runs; regional weather stations. See dossier for details, licenses and links.

## 4. Epic 1 — Proposed PoC tickets

### P0 — Experiment scaffold and decision ledger

**Question:** Can experiments be reproducible, auditable and resource-bounded?

**Minimum work**
- Repository README, run instructions, locked Python environment (`uv` or equivalent), CLI scripts and configurations.
- Conventional folders: `experiments/`, `data/README.md`, `reports/`, `docs/decisions.md`. Keep secrets and large files out of Git.
- Record inputs, sources, versions, random seeds, hardware, duration, limits and generated artifacts for every experiment.
- Maintain an assumptions ledger with `VALIDATED`, `REJECTED` or `INCONCLUSIVE`, rationale and evidence links.

**Acceptance:** Another developer can reproduce at least one example from the instructions; no credentials committed; duration and budget caps are explicit.

### P1 — Mushroom occurrence availability and quality

**Question:** Are there enough trustworthy occurrences to compare with historical weather and habitat?

**Minimum work**
- Obtain a limited sample from GBIF and/or iNaturalist for the agreed taxon and geographic scope. Save queries, download IDs, retrieval dates, licenses and source provenance.
- Deduplicate, including identifiable GBIF/iNaturalist overlap.
- Profile raw and filtered counts by year, season, location, coordinate uncertainty/obfuscation, identification quality, temporal/spatial anomalies and license.
- Make a minimal diagnostic plot of **eligible** records. Never expose sensitive or obscured locations.
- Inspect sampling bias around roads, footpaths and heavily visited sites.

**Deliverables:** `reports/p1_observations.md`, quality table, and reproducible sample or download script.

**Acceptance:** Report independent eligible event count, geographic/time coverage, location precision, license constraints and a reasoned conclusion about dataset adequacy—not merely “the API works.”

**Stop/pivot:** If evidence is sparse, widen the region/taxon or use expert rules only. Never interpret absence of a report as verified mushroom absence.

### P2 — GIS and habitat feasibility

**Question:** Can we distinguish potentially suitable habitats with reproducible data?

**Minimum work**
- Collect forest cover, tree classes/species where available, elevation/slope/aspect and soil pH/geology for a small sample area.
- Check licenses, formats, CRS, coverage, nominal versus effective resolution and gaps.
- Combine into a reproducible grid and derive a handful of interpretable features with provenance/quality flags.
- Manually check a few contrasting cells; do not infer exact tree species from broadleaf/conifer classes alone.

**Deliverables:** `reports/p2_habitat.md`, processed small-area extract, layer manifest and ETL scripts.

**Acceptance:** Reproducible sample grid, auditable features, coverage statistics and limitations. No need for a national production map.

### P3 — Historical weather and archived forecasts

**Question:** Can we reconstruct the information actually available when a prediction would have been made?

**Minimum work**
- For a limited P1 sample, extract 7/14/30 preceding days of precipitation and temperatures, and where available soil moisture, evapotranspiration and soil temperature.
- Keep **historic observations/reanalysis** strictly separate from **forecasts issued in the past**. Document model-specific run availability and date coverage.
- Compute features with explicit point-in-time cutoffs: `as_of_date`, `target_date`, `lead_days`; document day boundary and timezone handling.
- Measure API latency, quotas, caching, licensing and batch retrieval feasibility.

**Deliverables:** `reports/p3_weather.md`, sample extracts and `build_weather_features` script.

**Acceptance:** Demonstrate a defensible historical “where to look today” reconstruction; **independently** demonstrate or rule out a true +7-day forecast backtest. Never substitute weather that later occurred for a forecast actually issued at that time.

### P4 — Baselines and model benchmark

**Question:** Do environmental features rank promising areas better than naive strategies?

**Prerequisites:** P1–P3 or a documented narrower benchmark decision.

**Minimum work**
- Define evaluation unit (occurrence/cell/day), metrics, inclusion rules and splits **before** running comparisons.
- Baselines: random/area-neutral, recent-rainfall heuristic and optionally static habitat suitability.
- Compare explainable expert rules, logistic regression and **only when justified** LightGBM/gradient-boosted trees.
- Address time and spatial leakage, duplicates, autocorrelation and observer effort. Hold out years and geographic regions; row-level random splitting alone is insufficient.
- With presence-only observations, use carefully matched background/pseudo-absence samples and **ranking/enrichment metrics**, e.g. share of observations falling in the top 20% of ranked accessible land. Do not report ordinary binary accuracy as true presence/absence performance.
- Quantify uncertainty where feasible; reserve genuinely out-of-sample data after tuning.
- Enforce a hard **30-minute training/run timeout**, CPU only, no dedicated ML infrastructure.

**Deliverables:** `reports/p4_benchmark.md`, metrics, splits, baselines, CPU/RAM/runtime, configs, reproducible commands and models only when useful.

**Acceptance:** Honest replicable comparison, including ML failures; identify added signal from weather versus habitat; recommend **rules / ML / insufficient data**.

**Stop/pivot:** An invalid dataset or evaluation design yields `INCONCLUSIVE`, not permission to escalate model complexity.

### P5 — Mobile web map + API technical spike

**Question:** Can precomputed data be explored comfortably on a smartphone?

**Minimum work**
- Local versioned `/api/v1/...` endpoint serving sample/precomputed cells with `species`, `as_of`, `target_date`, `score_type`, uncertainty/quality and data provenance.
- One responsive page with MapLibre (or equivalent), geographic map, species/date selection and cell details.
- Check touch usability, readability, scroll/pan, first-load performance, payload size and service RAM in a mobile viewport and preferably a physical phone.
- Clearly label synthetic/demo data; never treat a simulated heatmap as prediction evidence.

**Deliverables:** Local minimal demo, documented endpoint and `reports/p5_web_spike.md`.

**Acceptance:** Works locally on a phone/tested mobile environment; frontend and API remain separate; no VPS/domain/full authentication needed.

**Out of scope:** polished visual design, accounts, notifications, offline PWA, native iOS, national maps and large-scale load testing.

### P6 — Licenses, operating costs, shared hosting and migration

**Question:** Can the service remain free to users and portable across inexpensive hosts?

**Minimum work**
- Source/API matrix covering provider, URL, license, commercial use, redistribution, attribution, quotas, cost and risks; distinguish observation data and photograph rights.
- Estimate daily batch compute, raster/cache footprint, operational database size, tile count and requests at **hypothetical** levels of 10/50/100 active users.
- Target roughly **€5–8/month** for shared VPS plus backup, **excluding domains and commercial data licenses**; show plausible actual costs, contract terms and RAM/storage sensitivity instead of promising the target.
- Use local Docker Compose to initialize app/database from scratch and prove **dump → restore → smoke test** with an existing application image.
- Outline repeatable future provisioning and cutover (Ansible, reverse proxy, Cloudflare API), without purchasing or changing any infrastructure now.
- Account for multi-project container isolation, off-site backup, DNS/Cloudflare caching, rollback and explicit approval before production changes. A few minutes of outage are acceptable.

**Deliverables:** `reports/p6_cost_licence_portability.md`, source-license matrix, budget scenario and local restore evidence.

**Acceptance:** Document blockers, uncovered costs, estimated/measured RAM and disk needs, and locally demonstrated portability. Zero actual purchases.

## 5. Order and dependencies

1. **P0** creates experiment/reproducibility conventions.
2. **P1, P2, P3** can run in parallel with agreed data contracts. Reassess P4 if P1 shows inadequate observations.
3. **P4** depends on features and a rigorous evaluation plan.
4. **P5** may use visibly labeled synthetic data; its technical feasibility does not depend on model accuracy.
5. **P6** can run in parallel and update cost estimates with P2–P5 measurements.
6. **Final gate:** one concise evidence-based decision and recommended next scope.

P0–P6 are **proposed validation units**, not a requirement to create seven standalone tickets if merging work reduces overhead without sacrificing evidence or ownership.

## 6. Mandatory GO / PIVOT / NO-GO gate

A decision requires:

- All A1–A7 marked **VALIDATED / REJECTED / INCONCLUSIVE**, with links to evidence.
- Real datasets retrieved and processed—not only source websites bookmarked.
- Quantitative comparison against at least random and rainfall baselines, **or** a documented quantitative blocker preventing credible validation.
- Strict separation of present-day nowcast, retrospective realized-weather assessment and genuine archived +7-day forecast evaluation.
- Working local mobile web map and API spike.
- License matrix and cost budget with terms and uncertainties.
- Local restore test and plausible vendor-neutral shared-VPS deployment plan.
- No unsubstantiated success probabilities or accuracy claims.

**GO:** sufficient evidence and validation, useful improvement over baseline, sustainable rights/costs and feasible web stack; only then write an evidence-informed roadmap.

**PIVOT:** critical constraint requires changing species/geography/ambition or launching only an explicitly labeled habitat/conditions map.

**NO-GO:** insufficient data or predictive value, or unacceptable legal/economic limitations.

ML does **not** need to win. A strong transparent rule model can support GO. An honest environmental *conditions indicator* is a legitimate smaller outcome, without claiming calibrated find probabilities.

## 7. Explicit exclusions from Epic 1

- No domain, VPS, commercial weather subscriptions or private dataset purchases.
- No account system, social network, notifications, complete species guides, photographic recognition, native iOS client or complete national coverage.
- No publication of obscured/private observation coordinates.
- No conflation of ecological suitability with actual collection probability or mushroom edibility.
- No hindsight weather treated as a forecast issued earlier.
- No detailed planning of Epics 2–12 before the final validation report.

## 8. Required final report

Write `reports/EPIC1_VALIDATION_REPORT.md` with:

1. **Executive decision:** GO / PIVOT / NO-GO, justified within one page.
2. **Assumption ledger:** A1–A7, status, evidence, limitations, next action.
3. **Evidence index:** sources, dataset/version/license, repository commit and exact commands.
4. **Benchmark:** evaluation setup, data splits, metrics, baselines, models, runtime, uncertainty, errors and sampling biases.
5. **Deployment and costs:** RAM/disk, monthly cost scenarios and exclusions, API limits, local restoration result.
6. **Outstanding risks:** unresolved items described without downplaying them.
7. **Scope recommendation:** only after a gate decision, identify tested capabilities worth implementing next.

## 9. Agent handoff instruction (copy/paste)

> Use `Micometeo_PRD_Epic_1_Validation_EN.md` as the **sole operational scope authority** and `Micometeo_Context_Dossier_EN.md` only as background, source/price inventory and design rationale. Create Epic 1 with the smallest sensible number of independent issues implementing these PoCs. For each issue specify assumption, experiment, inputs, outputs, acceptance criteria, time/cost limits and dependencies. Do not generate later Epics, purchase services or implement the full application. Require the GO/PIVOT/NO-GO validation report before any subsequent roadmap.
