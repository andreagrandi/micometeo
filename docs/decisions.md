# Decisions

## Assumptions

Each assumption comes from section 2 of the PRD. A final status is one of
VALIDATED, REJECTED or INCONCLUSIVE. The evidence link must point to a report
or run record in this repository. Until an experiment finishes, the status is
NOT TESTED.

| ID | Assumption | Experiment and issue | Status | Reason | Evidence link |
|---|---|---|---|---|---|
| A1 | Enough trustworthy, dated, located porcini finds exist. | P1, #3 | NOT TESTED | | |
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
