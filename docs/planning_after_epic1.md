# Planning after Epic 1

Start here to write the epics and tickets that follow Epic 1. Read the files
in this order.

1. [Epic 1 validation report](../reports/EPIC1_VALIDATION_REPORT.md). The
   PIVOT decision, the open risks, and section 7 with what was tested and the
   checks to run before users see anything.
2. [Decisions](decisions.md). The status of A1 to A7 and the decision log.
   D11 to D14 set the product direction: a web map with a phone and a desktop
   layout, a percentage for each square, and an OpenStreetMap background.
3. [Epic 1 PRD](../Micometeo_PRD_Epic_1_Validation_EN.md). The rules that
   still hold: no purchases, runs on a laptop CPU, a score is not a chance
   until it is checked against real outcomes, and no weather from after the
   assessment date.
4. [Data formats](data_formats.md) and [test rules](test_rules.md). The 500 m
   grid, column names, the Italian day, and how predictions are scored.
5. [P6 licences and costs](../reports/p6_cost_licence_portability.md) and the
   [licence table](../reports/p6_licences.csv). Licence conditions, credit
   lines, API limits and monthly costs.
6. [P5 phone map](../reports/p5_phone_map.md) and the
   [API README](../apps/api/README.md). The API shape and the iPhone freeze.
7. [P4b benchmark](../reports/p4_benchmark.md) and
   [its settings](../experiments/p4b_benchmark/config.toml). The rules from
   published studies and their sources, which the percentage of D13 builds on.
8. [Context dossier](../Micometeo_Context_Dossier_EN.md). Background only.

File issues with the `gh-issue` skill in `.agents/skills/gh-issue/`.
