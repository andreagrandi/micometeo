# Published MVP issues

Published and verified on 11 October 2026 using the gh-issue skill.

[Micometeo project](https://github.com/users/andreagrandi/projects/9).

The [product PRD](product_prd.md) defines the scope. The [issue plan](mvp_issue_plan.md) retains the drafted bodies and classifications. GitHub now contains seven MVP epics, 26 native sub-issues and one later epic named "Features Roadmap". All new project items are in Todo.

## Local acceptance before hosting

All MVP work runs locally. The owner must choose between the Google Stitch and agent mockups before production UI work. The owner must then accept the complete local product before any later public deployment or domain and VPS investment. No issue authorizes a purchase, DNS change or public deployment.

The UI foundation [#55](https://github.com/andreagrandi/micometeo/issues/55) is blocked by the design decision [#54](https://github.com/andreagrandi/micometeo/issues/54). Later UI work depends on that foundation. The final owner decision [#63](https://github.com/andreagrandi/micometeo/issues/63) follows the complete local checks. Automated checks cannot complete that decision on the owner's behalf.

## Epics

Every row has the `epic` label and `size: XL`.

| Issue | Title | Priority | Area | Size | Risk | Native children |
|---|---|---|---|---|---|---|
| [#30](https://github.com/andreagrandi/micometeo/issues/30) | Epic 2: Build the local application foundation | High | Operations | XL | High | 3 |
| [#31](https://github.com/andreagrandi/micometeo/issues/31) | Epic 3: Build the terrain and habitat data for Italy | High | Habitat | XL | High | 3 |
| [#32](https://github.com/andreagrandi/micometeo/issues/32) | Epic 4: Keep recent weather and seven-day forecasts current | High | Weather | XL | High | 3 |
| [#33](https://github.com/andreagrandi/micometeo/issues/33) | Epic 5: Calculate and serve experimental porcini estimates | High | Modeling | XL | High | 4 |
| [#34](https://github.com/andreagrandi/micometeo/issues/34) | Epic 6: Compare two mockups and choose the MVP design | High | Web | XL | High | 4 |
| [#35](https://github.com/andreagrandi/micometeo/issues/35) | Epic 7: Build the curated bilingual map website | High | Web | XL | High | 6 |
| [#36](https://github.com/andreagrandi/micometeo/issues/36) | Epic 8: Accept the complete MVP locally before public launch | High | Operations | XL | High | 3 |
| [#37](https://github.com/andreagrandi/micometeo/issues/37) | Features Roadmap | Low | Research | XL | High | 0 |

## Sub-issues

Each issue has exactly its type label and its size label. Parent and blocker links below are verified native GitHub relationships, not only references in the body.

| Issue | Title | Type | Priority | Area | Size | Risk | Parent | Direct blockers |
|---|---|---|---|---|---|---|---|---|
| [#38](https://github.com/andreagrandi/micometeo/issues/38) | Start the Django application and PostGIS database locally | enhancement | High | Operations | M | High | [#30](https://github.com/andreagrandi/micometeo/issues/30) | None |
| [#39](https://github.com/andreagrandi/micometeo/issues/39) | Run background jobs and scheduled commands on the local machine | enhancement | High | Operations | M | Normal | [#30](https://github.com/andreagrandi/micometeo/issues/30) | [#38](https://github.com/andreagrandi/micometeo/issues/38) |
| [#40](https://github.com/andreagrandi/micometeo/issues/40) | Add application checks without deployment automation | enhancement | Medium | Operations | M | Normal | [#30](https://github.com/andreagrandi/micometeo/issues/30) | [#39](https://github.com/andreagrandi/micometeo/issues/39) |
| [#41](https://github.com/andreagrandi/micometeo/issues/41) | Build a repeatable 500 m grid for all Italy | enhancement | High | Habitat | M | High | [#31](https://github.com/andreagrandi/micometeo/issues/31) | [#38](https://github.com/andreagrandi/micometeo/issues/38) |
| [#42](https://github.com/andreagrandi/micometeo/issues/42) | Attach national terrain information to the grid | enhancement | High | Habitat | M | High | [#31](https://github.com/andreagrandi/micometeo/issues/31) | [#41](https://github.com/andreagrandi/micometeo/issues/41) |
| [#43](https://github.com/andreagrandi/micometeo/issues/43) | Attach forest information and report habitat coverage | enhancement | High | Habitat | M | High | [#31](https://github.com/andreagrandi/micometeo/issues/31) | [#41](https://github.com/andreagrandi/micometeo/issues/41) |
| [#44](https://github.com/andreagrandi/micometeo/issues/44) | Fetch weather by shared cells and account for the free allowance | enhancement | High | Weather | M | High | [#32](https://github.com/andreagrandi/micometeo/issues/32) | [#41](https://github.com/andreagrandi/micometeo/issues/41) |
| [#45](https://github.com/andreagrandi/micometeo/issues/45) | Build dated weather summaries for today and seven days ahead | enhancement | High | Weather | M | High | [#32](https://github.com/andreagrandi/micometeo/issues/32) | [#44](https://github.com/andreagrandi/micometeo/issues/44) |
| [#46](https://github.com/andreagrandi/micometeo/issues/46) | Schedule a daily weather update and retain complete batches | enhancement | High | Weather | M | High | [#32](https://github.com/andreagrandi/micometeo/issues/32) | [#45](https://github.com/andreagrandi/micometeo/issues/45), [#39](https://github.com/andreagrandi/micometeo/issues/39) |
| [#47](https://github.com/andreagrandi/micometeo/issues/47) | Define and implement the experimental growing-probability method | enhancement | High | Modeling | M | High | [#33](https://github.com/andreagrandi/micometeo/issues/33) | [#42](https://github.com/andreagrandi/micometeo/issues/42), [#43](https://github.com/andreagrandi/micometeo/issues/43), [#45](https://github.com/andreagrandi/micometeo/issues/45) |
| [#48](https://github.com/andreagrandi/micometeo/issues/48) | Calculate and publish one complete eight-date estimate update | enhancement | High | Modeling | M | High | [#33](https://github.com/andreagrandi/micometeo/issues/33) | [#47](https://github.com/andreagrandi/micometeo/issues/47), [#46](https://github.com/andreagrandi/micometeo/issues/46) |
| [#49](https://github.com/andreagrandi/micometeo/issues/49) | Serve map estimates by date and visible area | enhancement | High | Web | M | High | [#33](https://github.com/andreagrandi/micometeo/issues/33) | [#48](https://github.com/andreagrandi/micometeo/issues/48) |
| [#50](https://github.com/andreagrandi/micometeo/issues/50) | Serve area explanations, weather and source details | enhancement | High | Web | M | High | [#33](https://github.com/andreagrandi/micometeo/issues/33) | [#48](https://github.com/andreagrandi/micometeo/issues/48) |
| [#51](https://github.com/andreagrandi/micometeo/issues/51) | Write the shared mockup brief and Google Stitch prompt | documentation | High | Web | S | Normal | [#34](https://github.com/andreagrandi/micometeo/issues/34) | None |
| [#52](https://github.com/andreagrandi/micometeo/issues/52) | Produce the Google Stitch mockup for phone and desktop | enhancement | High | Web | M | Normal | [#34](https://github.com/andreagrandi/micometeo/issues/34) | [#51](https://github.com/andreagrandi/micometeo/issues/51) |
| [#53](https://github.com/andreagrandi/micometeo/issues/53) | Create an independent agent mockup for phone and desktop | enhancement | High | Web | M | Normal | [#34](https://github.com/andreagrandi/micometeo/issues/34) | [#51](https://github.com/andreagrandi/micometeo/issues/51) |
| [#54](https://github.com/andreagrandi/micometeo/issues/54) | Compare both mockups and record the owner's design choice | documentation | High | Web | S | Normal | [#34](https://github.com/andreagrandi/micometeo/issues/34) | [#52](https://github.com/andreagrandi/micometeo/issues/52), [#53](https://github.com/andreagrandi/micometeo/issues/53) |
| [#55](https://github.com/andreagrandi/micometeo/issues/55) | Implement the selected responsive layout and language controls | enhancement | High | Web | M | High | [#35](https://github.com/andreagrandi/micometeo/issues/35) | [#54](https://github.com/andreagrandi/micometeo/issues/54), [#38](https://github.com/andreagrandi/micometeo/issues/38) |
| [#56](https://github.com/andreagrandi/micometeo/issues/56) | Add the probability map, date control and background styles | enhancement | High | Web | M | High | [#35](https://github.com/andreagrandi/micometeo/issues/35) | [#55](https://github.com/andreagrandi/micometeo/issues/55), [#49](https://github.com/andreagrandi/micometeo/issues/49) |
| [#57](https://github.com/andreagrandi/micometeo/issues/57) | Add place search and optional current location | enhancement | High | Web | M | Normal | [#35](https://github.com/andreagrandi/micometeo/issues/35) | [#56](https://github.com/andreagrandi/micometeo/issues/56) |
| [#58](https://github.com/andreagrandi/micometeo/issues/58) | Show the selected area's estimate, weather and explanation | enhancement | High | Web | M | High | [#35](https://github.com/andreagrandi/micometeo/issues/35) | [#56](https://github.com/andreagrandi/micometeo/issues/56), [#50](https://github.com/andreagrandi/micometeo/issues/50) |
| [#59](https://github.com/andreagrandi/micometeo/issues/59) | Save and manage private favorites in the current browser | enhancement | Medium | Web | M | Normal | [#35](https://github.com/andreagrandi/micometeo/issues/35) | [#58](https://github.com/andreagrandi/micometeo/issues/58) |
| [#60](https://github.com/andreagrandi/micometeo/issues/60) | Open the selected destination in an external navigation app | enhancement | Medium | Web | S | Normal | [#35](https://github.com/andreagrandi/micometeo/issues/35) | [#58](https://github.com/andreagrandi/micometeo/issues/58) |
| [#61](https://github.com/andreagrandi/micometeo/issues/61) | Verify the national data and update flow on the local machine | enhancement | High | Operations | M | High | [#36](https://github.com/andreagrandi/micometeo/issues/36) | [#40](https://github.com/andreagrandi/micometeo/issues/40), [#49](https://github.com/andreagrandi/micometeo/issues/49), [#50](https://github.com/andreagrandi/micometeo/issues/50) |
| [#62](https://github.com/andreagrandi/micometeo/issues/62) | Verify the complete bilingual journey and sustained phone-map use | enhancement | High | Web | M | High | [#36](https://github.com/andreagrandi/micometeo/issues/36) | [#61](https://github.com/andreagrandi/micometeo/issues/61), [#57](https://github.com/andreagrandi/micometeo/issues/57), [#59](https://github.com/andreagrandi/micometeo/issues/59), [#60](https://github.com/andreagrandi/micometeo/issues/60) |
| [#63](https://github.com/andreagrandi/micometeo/issues/63) | Record the owner's acceptance of the complete local MVP | documentation | High | Operations | S | Normal | [#36](https://github.com/andreagrandi/micometeo/issues/36) | [#62](https://github.com/andreagrandi/micometeo/issues/62) |

## Labels and colors

Copied the shared repository labels `dependencies`, `github_actions`, `python`, `docker` and `javascript` from Book Corners, plus `PRD` and `python:uv` from Draft Omen. Existing unrelated and project-specific labels were retained.

| Repository size label | Color copied from Draft Omen |
|---|---|
| size: S | B7E4C7 |
| size: M | A9D6FF |
| size: L | FFD6A5 |
| size: XL | FFADAD |

Their descriptions also match Draft Omen. Priority uses red for High, yellow for Medium and blue for Low, matching Book Corners and Draft Omen. Project Size uses green for S, blue for M, orange for L and red for XL, matching Draft Omen and Score Sift. Status already matched and was retained.

Area retains Micometeo's names and uses the shared palette. Observations is blue, Habitat green, Weather yellow, Modeling purple, Web pink, Operations orange and Research grey. Updating options changed their IDs. Existing assignments were restored by name, and the new IDs are recorded in the [issue reference](../.agents/skills/gh-issue/REFERENCE.md).

## Verification

One final GraphQL query checked the published bodies, titles, state, exact labels, four project fields, native parents, native children, native blockers, repository label colors and project option colors. It found no mismatches against the drafted plan.

- All 34 new issues are open and have the expected project values.
- All 26 child issues have the correct native parent.
- All 37 direct dependency links match the plan. The plan has no dependency cycles or redundant transitive links.
- Features Roadmap contains the grouped tables for 66 deferred features and has no children or blockers.
- All 15 existing project items retained their Priority, Area, Status and Size values.

There were 117 explicit `gh api` calls. Four failed to connect before the user requested another attempt. Two reference lookups returned HTTP 404. One large project-field assignment returned HTTP 504 after partially completing. A targeted read identified the three remaining assignments, which were restored. Subsequent project-field assignments used smaller batches to avoid another timeout. The final verification confirmed the complete result. The final GraphQL response reported 4972 points remaining in its rate allowance.
