# Decisions

## Assumptions

Each assumption comes from section 2 of the PRD. A final status is one of
VALIDATED, REJECTED or INCONCLUSIVE. The evidence link must point to a report
or run record in this repository. Until an experiment finishes, the status is
NOT TESTED.

| ID | Assumption | Experiment and issue | Status | Reason | Evidence link |
|---|---|---|---|---|---|
| A1 | Enough trustworthy, dated, located porcini finds exist. | P1, #3 | INCONCLUSIVE | Switzerland and Austria have 4,747 reliable finds, enough to test weather. Tuscany and the Apennines have 85, too few on their own. | [P1 report](../reports/p1_observations.md), [run record](../reports/runs/p1_observations/20261010T181005Z-696b43.json) |
| A2 | Tree and habitat data help at regional level. | P2, #4 and #5 | NOT TESTED | | |
| A3 | Past weather is enough to judge conditions today. | P3a, #6 | NOT TESTED | | |
| A4 | A forecast 7 days ahead can be tested without knowing the outcome. | P3b, #7 | NOT TESTED | | |
| A5 | Weather and habitat signals beat a simple guess. | P4, #8 and #9 | NOT TESTED | | |
| A6 | Precomputed results can be served efficiently on a phone. | P5, #10 | NOT TESTED | | |
| A7 | Licences and running costs allow a free small service. | P6, #11 and #12 | NOT TESTED | | |

## Decision log

| ID | Date | Decision | Reason |
|---|---|---|---|
| D1 | 2026-10-10 | Use 500 m squares in EPSG:3035 with IDs like `500m_E4321500_N2345000`. | One fixed grid in metres keeps squares equal in area and lets every dataset join on the same ID. |
| D2 | 2026-10-10 | A day runs from midnight to midnight Italian time, Europe/Rome. | Finds, weather and users all follow Italian local days, so one rule avoids shifted dates. |
| D3 | 2026-10-10 | Study the four porcini species as one group: *Boletus edulis* GBIF 5954958, *B. aereus* GBIF 8733688, *B. reticulatus* GBIF 5954691 and *B. pinophilus* GBIF 5954949. *B. aestivalis* is a GBIF synonym of *B. reticulatus* and is included through that ID. iNaturalist taxon IDs are 48701, 333772, 350216 and 335942. | GBIF count queries on this date found 15 *B. edulis* records in all of Tuscany and about 100 for the four species together. One species alone is too few to test anything. |
| D4 | 2026-10-10 | Use two areas. The home area is Tuscany, GADM ITA.16_1, plus Emilia-Romagna, GADM ITA.6_1, south of latitude 44.30 N to cover the Apennine side. Pistoia province, GADM ITA.16.8_1, is reported on its own. The comparison area is Switzerland plus Austria. | The home area has about 130 to 160 separate finds, which may be too few. Switzerland and Austria have about 8,900 records since 2000 in mountain forests closer to the Apennines than northern Europe. A result there shows whether weather predicts finds at all. Tuscany shows whether it holds where the app will be used. |
