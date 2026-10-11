# Micometeo issue reference

## Stable GitHub metadata

Repository: `andreagrandi/micometeo`

Project: number `9`, ID `PVT_kwHOAAm1584BmebS`

| Field | Field ID | Options |
|---|---|---|
| Priority | `PVTSSF_lAHOAAm1584BmebSzhlHUdU` | High `11ab1cfc`; Medium `f708776c`; Low `c98a518a` |
| Area | `PVTSSF_lAHOAAm1584BmebSzhlHUeQ` | Observations `2ec95c32`; Habitat `dcfa8f97`; Weather `cd8fa0a6`; Modeling `7788089d`; Web `628ab47e`; Operations `9b044dc6`; Research `76f21ed5` |
| Status | `PVTSSF_lAHOAAm1584BmebSzhlHUaw` | Todo `f75ad846`; In Progress `47fc9ee4`; Done `98236657` |
| Size | `PVTSSF_lAHOAAm1584BmebSzhlHUhs` | S `19398795`; M `99413039`; L `6b4c4eaa`; XL `6df14021` |

These option IDs were refreshed after matching the project colors to the
other projects on 11 October 2026.

Pass label names to `gh issue create`:

- Type: `epic`, `experiment`, `enhancement`, `bug`, or `documentation`
- Size: `size: S`, `size: M`, `size: L`, or `size: XL`

## Classification

Priority has no default. Ask when it is not stated or inferable.

For product work after Epic 1, use High for MVP prerequisites and work that
blocks other MVP tickets. Use Medium for required work that can follow the
main implementation. The curated UI is a launch requirement, so it is not
Low merely because the work concerns appearance. Deferred roadmap choices
use Low. The investigation rules below remain relevant to Epic 1.

- High: needed before the GO / PIVOT / NO-GO decision and blocking other
  issues, or a defect that makes evidence untrustworthy, such as using data
  that did not exist yet on a date, a wrong source record, or a committed
  secret.
- Medium: needed before the decision but not blocking other work, or a defect
  with a workaround.
- Low: polish, docs, refactors, minor developer experience.

Area:

- Observations: GBIF and iNaturalist finds, species, duplicates, location
  accuracy.
- Habitat: forest, tree, land cover, terrain, soil and rock type layers, the
  map grid.
- Weather: past weather, forecasts published in the past, and the weather
  totals built from them.
- Modeling: test rules, data splits, simple guesses, rules and models.
- Web: API and phone map.
- Operations: repository setup, environment, Docker, backup, restore,
  server plans.
- Research: licenses, costs, decision records and validation reports.

Size is approximate; never estimate exact LOC in issue content.

Use High risk for logic that could use data not yet available on a given date,
evaluation design, licensing that could block reuse, migrations, public API
compatibility, multiple runtime or UI surfaces, or failures likely to survive
ordinary tests. Otherwise use Normal. Size and risk are independent.

## Experiment issue body

Use for `experiment` issues. Every Epic 1 PoC answers one question and tests
named assumptions from the PRD.

```markdown
## Question

<The PRD question this experiment answers>

## Assumptions tested

<A1-A7 IDs and hypotheses from the PRD, or None>

## Experiment

<Minimum work, as concrete steps>

## Inputs

<Data sources, prior issue outputs, configs>

## Outputs

<Report path, scripts, data extracts, manifests>

## Acceptance Criteria

- [ ] AC1: <Observable done condition>
- [ ] AC2: <Observable done condition>

## Limits

<Runtime caps, data volume caps, no purchases, API terms to respect>

## Stop or change course

<Evidence that ends the experiment early, and what to record>

## Dependencies

<Direct prerequisite issues, or None>

## Implementation classification

- **Estimated size:** <S|M|L|XL>
- **Risk:** <Normal|High>
- **Reason:** <One concise sentence>
```

## Normal issue body

```markdown
## Problem

<What is wrong or missing and where>

## Proposed change

<What should happen instead>

## Acceptance Criteria

- [ ] AC1: <Observable done condition>
- [ ] AC2: <Observable done condition>

## Dependencies

<Direct prerequisite issues, or None>

## Implementation classification

- **Estimated size:** <S|M|L|XL>
- **Risk:** <Normal|High>
- **Reason:** <One concise sentence>
```

Title: short, imperative or problem-focused. Experiment titles may start with
the PoC ID, such as `P1: ...`.

## Epic body

```markdown
## Problem

<Overall problem>

## Goal

<Completed outcome>

## Scope

<Major covered areas>

## Out of scope

<Important exclusions>

## Child issues

- [ ] <Child outcome>
- [ ] <Child outcome>

## Acceptance Criteria

- [ ] <Epic-level completion condition>
- [ ] <Epic-level completion condition>

## Epic classification

- **Overall size:** <S|M|L|XL>
- **Overall risk:** <Normal|High>
- **Reason:** <One concise sentence>
```

## Efficient single-issue execution

```sh
URL=$(gh issue create --repo andreagrandi/micometeo \
  --title "<title>" --body-file <body.md> \
  --label "<type>" --label "size: <S|M|L|XL>")

ITEM_ID=$(gh project item-add 9 --owner andreagrandi \
  --url "$URL" --format json --jq .id)
```

Set each field with node IDs; never resolve by URL or name in the edit loop:

```sh
gh project item-edit --id "$ITEM_ID" \
  --project-id PVT_kwHOAAm1584BmebS \
  --field-id <field-id> --single-select-option-id <option-id>
```

## Efficient multi-issue execution

After creation, resolve every issue node ID and REST database ID in one query:

```graphql
query {
  repository(owner: "andreagrandi", name: "micometeo") {
    i1: issue(number: 1) { id databaseId url }
    i2: issue(number: 2) { id databaseId url }
  }
  rateLimit { cost remaining resetAt }
}
```

Add every issue to the project in one request:

```graphql
mutation {
  i1: addProjectV2ItemById(input: {
    projectId: "PVT_kwHOAAm1584BmebS"
    contentId: "<issue-node-id>"
  }) { item { id } }
  i2: addProjectV2ItemById(input: {
    projectId: "PVT_kwHOAAm1584BmebS"
    contentId: "<issue-node-id>"
  }) { item { id } }
}
```

Set every field in one request, with one alias per item and field:

```graphql
mutation {
  i1Priority: updateProjectV2ItemFieldValue(input: {
    projectId: "PVT_kwHOAAm1584BmebS"
    itemId: "<project-item-id>"
    fieldId: "PVTSSF_lAHOAAm1584BmebSzhlHUdU"
    value: { singleSelectOptionId: "<priority-option-id>" }
  }) { projectV2Item { id } }
  i1Area: updateProjectV2ItemFieldValue(input: {
    projectId: "PVT_kwHOAAm1584BmebS"
    itemId: "<project-item-id>"
    fieldId: "PVTSSF_lAHOAAm1584BmebSzhlHUeQ"
    value: { singleSelectOptionId: "<area-option-id>" }
  }) { projectV2Item { id } }
}
```

Include Status and Size aliases in the same mutation and run it through one
`gh api graphql -f query='<mutation>'` process.

## Native relationships

The relationship endpoints take REST database IDs, which the batched issue
query already returned.

Attach a native child:

```sh
gh api --method POST -H "X-GitHub-Api-Version: 2026-03-10" \
  repos/andreagrandi/micometeo/issues/<parent>/sub_issues \
  -F sub_issue_id=<child-database-id>
```

Add a direct blocked-by relationship:

```sh
gh api --method POST -H "X-GitHub-Api-Version: 2026-03-10" \
  repos/andreagrandi/micometeo/issues/<issue>/dependencies/blocked_by \
  -F issue_id=<blocker-database-id>
```

Do not query an issue again just to recover a database ID. Do not add
transitive blocked-by links.

## Verification query

Verify all project items in one query using the item IDs returned by the add
mutation:

```graphql
query {
  nodes(ids: ["<item-id>", "<item-id>"]) {
    ... on ProjectV2Item {
      content { ... on Issue { number title labels(first: 10) { nodes { name } } } }
      fieldValues(first: 20) {
        nodes {
          ... on ProjectV2ItemFieldSingleSelectValue {
            name
            field { ... on ProjectV2SingleSelectField { name } }
          }
        }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
```

Compare the response locally with the approved specification. One parent
`sub_issues` request and only the needed direct `blocked_by` requests finish
relationship verification.
