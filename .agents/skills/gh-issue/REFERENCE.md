# Micometeo issue reference

## Stable GitHub metadata

Repository: `andreagrandi/micometeo`

Project: number `9`, ID `PVT_kwHOAAm1584BmebS`

| Field | Field ID | Options |
|---|---|---|
| Priority | `PVTSSF_lAHOAAm1584BmebSzhlHUdU` | High `8ae88294`; Medium `4150b902`; Low `195aaa9c` |
| Area | `PVTSSF_lAHOAAm1584BmebSzhlHUeQ` | Observations `b482b62f`; Habitat `8f0e36d3`; Weather `4a4d5da4`; Modeling `7c2ff745`; Web `81652542`; Operations `28c76f4c`; Research `91c18a95` |
| Status | `PVTSSF_lAHOAAm1584BmebSzhlHUaw` | Todo `f75ad846`; In Progress `47fc9ee4`; Done `98236657` |
| Size | `PVTSSF_lAHOAAm1584BmebSzhlHUhs` | S `855411c1`; M `78633b54`; L `f46c5cc6`; XL `611bd67c` |

Pass label names to `gh issue create`:

- Type: `epic`, `experiment`, `enhancement`, `bug`, or `documentation`
- Size: `size: S`, `size: M`, `size: L`, or `size: XL`

## Classification

Priority has no default. Ask when it is not stated or inferable.

- High: on the critical path to the GO / PIVOT / NO-GO gate, or a defect that
  invalidates evidence, such as data leakage, wrong provenance or a committed
  secret.
- Medium: required for the gate but not blocking other work, or a defect with
  a workaround.
- Low: polish, docs, refactors, minor developer experience.

Area:

- Observations: GBIF and iNaturalist occurrences, taxonomy, deduplication,
  location quality.
- Habitat: forest, tree, land cover, terrain, soil and geology layers, the
  spatial grid.
- Weather: historical weather, reanalysis, archived forecast runs, point-in-time
  features.
- Modeling: evaluation protocol, splits, baselines, rules and models.
- Web: API and mobile map.
- Operations: repository scaffold, environment, Docker, backup, restore,
  deployment plans.
- Research: licenses, costs, decision records and validation reports.

Size is approximate; never estimate exact LOC in issue content.

Use High orchestration risk for point-in-time or leakage-sensitive logic,
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

## Stop or pivot

<Evidence that ends the experiment early and what to record>

## Dependencies

<Direct prerequisite issues, or None>

## Implementation classification

- **Estimated size:** <S|M|L|XL>
- **Orchestration risk:** <Normal|High>
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
- **Orchestration risk:** <Normal|High>
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
- **Overall orchestration risk:** <Normal|High>
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

