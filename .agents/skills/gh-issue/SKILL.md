---
name: gh-issue
description: >-
  Create, classify, split, and organize GitHub issues for andreagrandi/sporameteo.
  Use when filing issues, drafting experiment tickets, creating epics or native
  sub-issues, linking dependencies, or updating the SporaMeteo project.
---

# Manage SporaMeteo issues

Repository: `andreagrandi/sporameteo` · Project: `https://github.com/users/andreagrandi/projects/9`

See [REFERENCE.md](REFERENCE.md) for classifications, templates, IDs, and API patterns.

## Scope authority

- Epic 1 tickets come only from `SporaMeteo_PRD_Epic_1_Validation_EN.md`.
  `SporaMeteo_Context_Dossier_EN.md` is background: sources, prices and design
  rationale. Never turn a dossier idea into a ticket unless the PRD asks for it.
- Do not create issues for Epics 2 and later until
  `reports/EPIC1_VALIDATION_REPORT.md` records a GO or PIVOT decision.
- Never write a ticket that purchases a domain, VPS, paid API or subscription.

## Non-negotiable rules

- Draft outward-facing issue content first. Show title, body, labels, Priority,
  Area, Size, and risk; mutate GitHub only after explicit approval.
- One agent owns all authenticated GitHub I/O. Subagents receive already
  fetched issue data and MUST NOT call GitHub.
- Never parallelize GitHub mutations. Batch independent ProjectV2 mutations
  into one GraphQL request.
- Never run GraphQL schema introspection during routine work. Use the stable
  IDs and patterns in [REFERENCE.md](REFERENCE.md).
- Never repeat a project or issue query merely to apply a different `jq`
  projection. Keep the first response and parse it locally.
- Never loop over `gh project item-edit --url ... --field ... --value ...`.
  Friendly-name resolution can issue extra lookups; use node and field IDs.

## Call budget

- Single issue: at most 6 calls after approval: create, add to the project, and
  set four fields by ID.
- Multi-issue or epic: write the API call graph before execution. Target no
  more than `2N + D + 8` calls for `N` issues and `D` dependency links.
- Above 10 calls, include `rateLimit { cost remaining resetAt }` in an existing
  query. If quota is low, stop nonessential reads and do not retry before
  `resetAt`.

## Draft and classify

- Every issue gets exactly two labels: one type label and `size: <S|M|L|XL>`.
  Type is `epic`, `experiment`, `enhancement`, `bug`, or `documentation`.
- Project fields are required: Priority, Area, Status `Todo`, and Size matching
  the size label.
- Use `experiment` for a PoC that tests an assumption and produces a report.
  Its body uses the experiment template, which names the assumption, inputs,
  outputs, limits and when to stop or change course.
- For an epic or split, prefer one independently reviewable outcome per child,
  make dependencies explicit, classify every child independently, and keep the
  native parent-child relationship.
- Never recommend a model in issue content.

## Plain language

Write titles, bodies and acceptance criteria so someone outside data science
or meteorology can follow them. Follow the "Plain language" section of the
repository `AGENTS.md`, including its table of terms to avoid, and check every
draft against it before showing it.

## Size and implementation readiness

Size reflects expected scope, including scripts, tests, data manifests and the
report:

- `S`: one focused change; roughly 3 files and 100 meaningful lines or less.
- `M`: one subsystem outcome; roughly 10 files and 500 meaningful lines or less.
- `L`: more than one subsystem, or up to roughly 20 files and 1,000 meaningful
  lines.
- `XL`: epic-scale; several independently reviewable outcomes.

Only `S` and `M` issues are implementation-ready. Split `L` and `XL` work into
native `S` or `M` sub-issues before it is scheduled. Split along the
assumption being tested or the data source being integrated, so each child ends
with its own evidence.

Every implementation-ready issue has numbered acceptance criteria, each stating
one observable outcome checked by a named test, command, or report section.
Prefer 8 criteria or fewer; more suggests the issue should be split.

## Execute after approval

### One issue

1. Create it with `gh issue create`, passing label names.
2. Add it with `gh project item-add` and capture the returned project item ID.
3. Set all four project fields with ID-based `gh project item-edit` commands.
4. Add explicitly requested native parent or dependency links.

### Two or more issues

1. Create each approved issue; keep every URL and number.
2. Resolve all issue node and database IDs in one targeted GraphQL query.
3. Add every issue to the project in one aliased `addProjectV2ItemById`
   mutation; keep the returned item IDs.
4. Set Priority, Area, Status, and Size for every item in one aliased
   `updateProjectV2ItemFieldValue` mutation.
5. Attach native sub-issues and dependency links with the REST patterns in
   [REFERENCE.md](REFERENCE.md). Do not add redundant transitive dependencies.

## Verify once

- One targeted GraphQL query returns all affected project items with their
  labels, Priority, Area, Status, and Size; compare locally with the approved
  values.
- One parent sub-issues query verifies all native children.
- Query blocked-by endpoints only for children that should have direct
  dependencies.
- Do not re-run successful mutations as verification.
- Report URLs, type, Priority, Area, Size, risk, parent links, dependencies,
  verification result, and the actual authenticated-call count.
