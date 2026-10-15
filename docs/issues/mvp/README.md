# MVP issue specifications

These files replace the abbreviated descriptions in the original
[issue plan](../../mvp_issue_plan.md). Each numbered file is the complete
body for that GitHub issue. The [published issue index](../../mvp_github_issues.md)
records titles, classifications, parents and direct blockers.

The [product PRD](../../product_prd.md) remains the scope authority.
The specifications repeat the decisions relevant to each ticket, cite the
investigation evidence, identify reusable code and define outputs, failure
behavior and observable acceptance criteria. Existing source paths refer to
the repository unless they explicitly name Book Corners. Deliverable paths
describe files to create during implementation, not files already present.

## Epics and children

| Epic | Child specifications |
|---|---|
| [#30 Local application foundation](30.md) | [#38 Application](38.md), [#39 Worker](39.md), [#40 Checks](40.md) |
| [#31 National terrain and habitat](31.md) | [#41 Grid](41.md), [#42 Terrain](42.md), [#43 Forest](43.md) |
| [#32 On-demand weather](32.md) | [#44 Requests and allowance](44.md), [#45 Dated summaries](45.md), [#46 Fetch on first request](46.md) |
| [#33 Experimental estimates](33.md) | [#47 Method](47.md), [#48 Stored estimates per area](48.md), [#49 Map API](49.md), [#50 Detail API](50.md) |
| [#34 Mockup comparison](34.md) | [#51 Brief](51.md), [#52 Stitch mockup](52.md), [#53 Agent mockup](53.md), [#54 Owner design choice](54.md) |
| [#35 Bilingual website](35.md) | [#55 Layout and language](55.md), [#56 Map](56.md), [#57 Search and location](57.md), [#58 Area details](58.md), [#59 Favorites](59.md), [#60 Navigation](60.md) |
| [#36 Local acceptance](36.md) | [#61 National data and on-demand checks](61.md), [#62 Browser and phone checks](62.md), [#63 Owner acceptance](63.md) |

[Features Roadmap #37](https://github.com/andreagrandi/sporameteo/issues/37)
retains its 66 grouped deferred features and has no sub-tickets. This revision
does not change its description, issue scope, labels, project fields, parents
or native dependencies.

## Decisions carried into every relevant ticket

- Cover all Italy, with today and the next seven days interpreted in Europe/Rome.
- Show whole experimental growth percentages with unvalidated status. Missing
  required data is unavailable, not zero. No owner mushroom fieldwork is required.
- Support Italian and English, free access, no ads and no registration.
- Use Book Corners' established implementation patterns and the useful
  SporaMeteo experiment code. Preserve the historical research results.
- Compare an actual Stitch mockup with an independent agent mockup before
  production UI work. The owner chooses the design in #54.
- Run and accept the complete MVP locally. The owner makes the final decision
  in #63. No ticket buys or deploys infrastructure.

## Engineering decisions owned by specific tickets

The interview settled product scope. Some implementation decisions require
the results of their owning ticket. They must be recorded before that ticket
is complete, rather than silently inherited from a prototype.

| Ticket | Required decision or measurement |
|---|---|
| #41 | Exact redistributable boundary file and national cell coverage. |
| #44 | Forest weather-cell mapping, temperature handling, request rules and the worst-case budget. P6 pricing is already assessed, and D15 to D18 settle on-demand fetching, cell size, forest squares and the weather window. |
| #45 | Explicit stored periods and distinction between live retrieval time and the historical experiment's midnight cutoff. |
| #47 | Exact experimental formula, parameters, national season/altitude treatment and worked examples. Research did not establish a calibrated formula. |
| #54 | Owner-selected design and required adjustments. |
| #56 | Compatible map provider/styles and measured renderer behavior using Book Corners as the starting point. |
| #57 | Free geocoder and its request policy. Physical-phone location checks use the Tailscale HTTPS address from #38. |

## GitHub update call graph

Read the existing issues and take one combined snapshot of bodies,
classifications, project fields, parents, children and blockers. Draft all 33
MVP bodies here before writing to GitHub. Update only those 33 issue bodies
with sequential `gh api` PATCH requests. Read them once in a combined final
query and compare each complete body with its file. Verify the same query
also preserves titles, labels, project fields and native relationships, and
that #37 remains unchanged. Include the API rate allowance in the queries.

The user's request to correct the inadequate tickets authorizes these body
updates. It does not authorize new product scope, commits, pushes or deployment.

## Verification

Published and checked on 11 October 2026. All 33 issue bodies exactly matched
these files after publication. The verification query also confirmed unchanged
titles, labels, project values, 26 native child links and 37 direct blockers.
Features Roadmap was unchanged. The full correction used 37 authenticated
GitHub CLI calls. See the [issue index](../../mvp_github_issues.md#description-revision)
for the audit record.
