# Planning after Epic 1

Start with the [product PRD](product_prd.md) to write the epics and tickets
that follow Epic 1. It records the completed product interview, the MVP and
the grouped description for the single "Features Roadmap" epic. The
[competitor comparison](../reports/Porcini%20app%20feature%20comparison.md)
records the feature research and selections.

The [published MVP issue index](mvp_github_issues.md) links the epics,
sub-tickets and native dependencies. The MVP must run locally and receive
the owner's acceptance before public deployment or domain and VPS investment.

The investigation establishes what was tested. It does not select the MVP.
The product PRD supersedes the earlier suggestions about regional scope and
requiring field validation before showing percentages. The MVP covers Italy
and can launch with clearly labelled experimental estimates.

Read the investigation evidence in this order.

1. [Epic 1 validation report](../reports/EPIC1_VALIDATION_REPORT.md). The
   PIVOT decision, the open risks, and section 7 with what was tested and the
   checks to run before users see anything.
2. [Decisions](decisions.md). The status of A1 to A7 and the historical
   decision log. Read product decisions alongside the later product PRD.
3. [Epic 1 PRD](../SporaMeteo_PRD_Epic_1_Validation_EN.md). The scope and
   rules of the completed investigation. Its validation requirements do not
   override the owner's acceptance of experimental estimates for the MVP.
   The no-purchase rule and honest handling of dates and evidence still hold.
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
8. [Context dossier](../SporaMeteo_Context_Dossier_EN.md). Background only.

File issues with the `gh-issue` skill in `.agents/skills/gh-issue/`.
