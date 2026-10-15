# MVP issue plan

The original publication drafts below have been superseded by the detailed
[issue specifications](issues/mvp/README.md). Use those specifications for
implementation. The originals remain here as a record of the first plan.

This plan follows `docs/product_prd.md` and the owner's instruction to create the issues. All MVP acceptance is local. The owner must accept the complete product before public deployment or hosting investment.

The issues have been published. Their URLs and verified native relationships
are recorded in the [published issue index](mvp_github_issues.md).

## GitHub call graph

Read repository labels, reference-project fields and existing SporaMeteo issues once. Preserve existing project assignments before editing field colors. Draft every issue below before publication. Create 34 issues in dependency order through `gh api`, retaining their returned node and database IDs. Add them to Project 9 in one GraphQL request and assign Priority, Area, Status and Size in one request. Attach 26 native children and 37 direct dependencies with the documented REST endpoints. Verify the final issue bodies, labels, project fields and native relationships together where the API supports it. No GitHub mutations run in parallel.

## Classifications

| Key | Title | Type | Priority | Area | Size | Risk | Parent | Direct dependencies |
|---|---|---|---|---|---|---|---|---|
| E2 | Epic 2: Build the local application foundation | epic | High | Operations | XL | High | None | None |
| E3 | Epic 3: Build the terrain and habitat data for Italy | epic | High | Habitat | XL | High | None | None |
| E4 | Epic 4: Keep recent weather and seven-day forecasts current | epic | High | Weather | XL | High | None | None |
| E5 | Epic 5: Calculate and serve experimental porcini estimates | epic | High | Modeling | XL | High | None | None |
| E6 | Epic 6: Compare two mockups and choose the MVP design | epic | High | Web | XL | High | None | None |
| E7 | Epic 7: Build the curated bilingual map website | epic | High | Web | XL | High | None | None |
| E8 | Epic 8: Accept the complete MVP locally before public launch | epic | High | Operations | XL | High | None | None |
| FND1 | Start the Django application and PostGIS database locally | enhancement | High | Operations | M | High | E2 | None |
| FND2 | Run background jobs and scheduled commands on the local machine | enhancement | High | Operations | M | Normal | E2 | FND1 |
| FND3 | Add application checks without deployment automation | enhancement | Medium | Operations | M | Normal | E2 | FND2 |
| HAB1 | Build a repeatable 500 m grid for all Italy | enhancement | High | Habitat | M | High | E3 | FND1 |
| HAB2 | Attach national terrain information to the grid | enhancement | High | Habitat | M | High | E3 | HAB1 |
| HAB3 | Attach forest information and report habitat coverage | enhancement | High | Habitat | M | High | E3 | HAB1 |
| WEA1 | Fetch weather by shared cells and account for the free allowance | enhancement | High | Weather | M | High | E4 | HAB1 |
| WEA2 | Build dated weather summaries for today and seven days ahead | enhancement | High | Weather | M | High | E4 | WEA1 |
| WEA3 | Schedule a daily weather update and retain complete batches | enhancement | High | Weather | M | High | E4 | WEA2, FND2 |
| MOD1 | Define and implement the experimental growing-probability method | enhancement | High | Modeling | M | High | E5 | HAB2, HAB3, WEA2 |
| MOD2 | Calculate and publish one complete eight-date estimate update | enhancement | High | Modeling | M | High | E5 | MOD1, WEA3 |
| MOD3 | Serve map estimates by date and visible area | enhancement | High | Web | M | High | E5 | MOD2 |
| MOD4 | Serve area explanations, weather and source details | enhancement | High | Web | M | High | E5 | MOD2 |
| DES1 | Write the shared mockup brief and Google Stitch prompt | documentation | High | Web | S | Normal | E6 | None |
| DES2 | Produce the Google Stitch mockup for phone and desktop | enhancement | High | Web | M | Normal | E6 | DES1 |
| DES3 | Create an independent agent mockup for phone and desktop | enhancement | High | Web | M | Normal | E6 | DES1 |
| DES4 | Compare both mockups and record the owner's design choice | documentation | High | Web | S | Normal | E6 | DES2, DES3 |
| WEB1 | Implement the selected responsive layout and language controls | enhancement | High | Web | M | High | E7 | DES4, FND1 |
| WEB2 | Add the probability map, date control and background styles | enhancement | High | Web | M | High | E7 | WEB1, MOD3 |
| WEB3 | Add place search and optional current location | enhancement | High | Web | M | Normal | E7 | WEB2 |
| WEB4 | Show the selected area's estimate, weather and explanation | enhancement | High | Web | M | High | E7 | WEB2, MOD4 |
| WEB5 | Save and manage private favorites in the current browser | enhancement | Medium | Web | M | Normal | E7 | WEB4 |
| WEB6 | Open the selected destination in an external navigation app | enhancement | Medium | Web | S | Normal | E7 | WEB4 |
| ACC1 | Verify the national data and update flow on the local machine | enhancement | High | Operations | M | High | E8 | FND3, MOD3, MOD4 |
| ACC2 | Verify the complete bilingual journey and sustained phone-map use | enhancement | High | Web | M | High | E8 | ACC1, WEB3, WEB5, WEB6 |
| ACC3 | Record the owner's acceptance of the complete local MVP | documentation | High | Operations | S | Normal | E8 | ACC2 |
| ROADMAP | Features Roadmap | epic | Low | Research | XL | High | None | None |

## Label and project corrections

Copy shared repository labels from Book Corners and Draft Omen. Preserve repository-specific labels and do not copy the names of unrelated projects. Copy Draft Omen's size-label colors and descriptions. Use the shared Priority colors, red for High, yellow for Medium and blue for Low. Use the shared Size colors, green for S, blue for M, orange for L and red for XL. Keep Status unchanged because it already matches. Retain SporaMeteo's Area names and use the same project color palette, with blue for Observations, green for Habitat, yellow for Weather, purple for Modeling, pink for Web, orange for Operations and grey for Research. Preserve existing issue assignments if updating options changes their identifiers.

## Draft issue bodies

The following bodies are the publication drafts. Dependency keys are replaced with the actual created issue numbers. Each issue receives its type label and matching size label. Every new project item starts in Todo.

### E2. Epic 2: Build the local application foundation

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The repository contains investigation tools and a demonstration map, but no application foundation for the agreed MVP.

#### Goal

Run the application, geographic database, background worker and checks locally using the established Book Corners patterns.

#### Scope

- Django, Django Ninja and PostgreSQL with PostGIS.
- Local application and worker processes, configuration and documented commands.
- Automated checks that do not deploy anything.

#### Out of scope

Public hosting and deployment, purchases, deferred roadmap features and manual mushroom field validation.

#### Child issues

- [ ] Start the Django application and PostGIS database locally
- [ ] Run background jobs and scheduled commands on the local machine
- [ ] Add application checks without deployment automation

#### Acceptance Criteria

- [ ] AC1: The local setup and worker checks recorded by the child issues pass from a clean checkout.
- [ ] AC2: CI runs checks without deployment jobs, hosting secrets or a public server.
- [ ] AC3: The investigation commands remain usable alongside the application.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Epic classification

- Overall size: XL
- Overall risk: High
- Reason: Application setup, geographic migrations and worker configuration affect later work.

### E3. Epic 3: Build the terrain and habitat data for Italy

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The habitat investigation covered 504 squares. The MVP must support all Italy at a few hundred metres of map detail.

#### Goal

Build a repeatable national 500 m grid with terrain, forest information, source dates and explicit data gaps.

#### Scope

- Redistributable Italian boundaries and the existing 500 m grid convention.
- National terrain and forest inputs, including Sicily and Sardinia.
- Coverage reports, source credits and optional regional details already available.

#### Out of scope

Public hosting and deployment, purchases, deferred roadmap features and manual mushroom field validation.

#### Child issues

- [ ] Build a repeatable 500 m grid for all Italy
- [ ] Attach national terrain information to the grid
- [ ] Attach forest information and report habitat coverage

#### Acceptance Criteria

- [ ] AC1: The child reports account for grid coverage and missing inputs across all Italian regions.
- [ ] AC2: A repeated build produces the same identifiers and retains source and licence information.
- [ ] AC3: Unavailable habitat values remain missing rather than becoming unsuitable habitat.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Epic classification

- Overall size: XL
- Overall risk: High
- Reason: National data joins and distribution licences can produce silent errors.

### E4. Epic 4: Keep recent weather and seven-day forecasts current

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The investigation proved weather access, but the app needs a shared daily update for all Italy.

#### Goal

Keep the recent weather and today plus seven forecast dates available through a local scheduled job within the already assessed free allowance.

#### Scope

- Shared weather cells and incremental caching using the existing Open-Meteo client.
- Italian local dates, recent rain periods and available forecast weather.
- Daily updates with complete batches, failure handling and counted API usage.

#### Out of scope

Public hosting and deployment, purchases, deferred roadmap features and manual mushroom field validation.

#### Child issues

- [ ] Fetch weather by shared cells and account for the free allowance
- [ ] Build dated weather summaries for today and seven days ahead
- [ ] Schedule a daily weather update and retain complete batches

#### Acceptance Criteria

- [ ] AC1: The national request plan and actual usage follow the allowance recorded in P6.
- [ ] AC2: Weather and forecast records refer to the correct Italian local dates.
- [ ] AC3: A failed update preserves the last complete weather batch and records its age.
- [ ] AC4: The job runs locally and does not require a server or a paid API.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Epic classification

- Overall size: XL
- Overall risk: High
- Reason: Date handling, incomplete downloads and provider accounting can silently change estimates.

### E5. Epic 5: Calculate and serve experimental porcini estimates

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The demonstration uses made-up scores. The MVP needs real inputs, a documented experimental calculation and consistent map results.

#### Goal

Produce and serve experimental growing-probability estimates for Italy for today and the next seven days, with explanations and data limitations.

#### Scope

- One documented method for the existing porcini group, using weather and habitat.
- Consistent publication of eight dated result sets.
- Map results and selected-area details with sources, freshness and missing-data states.

#### Out of scope

Public hosting and deployment, purchases, deferred roadmap features and manual mushroom field validation.

#### Child issues

- [ ] Define and implement the experimental growing-probability method
- [ ] Calculate and publish one complete eight-date estimate update
- [ ] Serve map estimates by date and visible area
- [ ] Serve area explanations, weather and source details

#### Acceptance Criteria

- [ ] AC1: All served estimates come from real input batches and identify the calculation version.
- [ ] AC2: The map and details agree on the selected area, date and published update.
- [ ] AC3: The service exposes experimental status and does not claim validated accuracy.
- [ ] AC4: No child requires manual field validation or automatic learning from new observations.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Epic classification

- Overall size: XL
- Overall risk: High
- Reason: Probability wording, geographic joins and dated result publication can mislead users if wrong.

### E6. Epic 6: Compare two mockups and choose the MVP design

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

A polished interface is mandatory, and the owner wants to compare a Google Stitch design with an independent agent design before UI implementation.

#### Goal

Evaluate two complete design alternatives for the agreed MVP and record the owner's chosen direction.

#### Scope

- A shared design brief and a ready-to-use Google Stitch prompt.
- One actual Google Stitch mockup and one independent agent mockup.
- Phone and desktop states, Italian and English examples, and the owner's comparison.

#### Out of scope

Public hosting and deployment, purchases, deferred roadmap features and manual mushroom field validation.

#### Child issues

- [ ] Write the shared mockup brief and Google Stitch prompt
- [ ] Produce the Google Stitch mockup for phone and desktop
- [ ] Create an independent agent mockup for phone and desktop
- [ ] Compare both mockups and record the owner's design choice

#### Acceptance Criteria

- [ ] AC1: Both alternatives cover the same selected MVP journey and required states.
- [ ] AC2: The owner has seen both alternatives and chosen a direction, with requested adjustments recorded.
- [ ] AC3: Production UI work depends on the design decision child issue.
- [ ] AC4: Mockups do not introduce deferred features into the MVP.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Epic classification

- Overall size: XL
- Overall risk: High
- Reason: Two device layouts and all MVP interactions must support a consistent design choice.

### E7. Epic 7: Build the curated bilingual map website

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

Visitors need the complete map journey in a polished interface, without accounts or paid access.

#### Goal

Implement the chosen design for phones and desktops, with Italian and English, area exploration, weather, favorites and external navigation.

#### Scope

- The selected design, responsive layouts and translated user-facing states.
- Date, map-background and layer controls, search and optional location.
- Area explanations, weather, browser-local favorites and navigation links.

#### Out of scope

Public hosting and deployment, purchases, deferred roadmap features and manual mushroom field validation.

#### Child issues

- [ ] Implement the selected responsive layout and language controls
- [ ] Add the probability map, date control and background styles
- [ ] Add place search and optional current location
- [ ] Show the selected area's estimate, weather and explanation
- [ ] Save and manage private favorites in the current browser
- [ ] Open the selected destination in an external navigation app

#### Acceptance Criteria

- [ ] AC1: All 16 MVP features are represented by the completed website and its supporting data work.
- [ ] AC2: The complete journey works without an account, advertising or subscriptions.
- [ ] AC3: The UI follows the owner-selected mockup on phone and desktop.
- [ ] AC4: Every child is developed and checked locally.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Epic classification

- Overall size: XL
- Overall risk: High
- Reason: Map state, data requests and responsive layouts interact across the complete user journey.

### E8. Epic 8: Accept the complete MVP locally before public launch

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

Passing individual tickets does not prove the complete product works or that the owner is satisfied enough to invest in hosting.

#### Goal

Verify the complete locally running MVP and obtain the owner's explicit product acceptance before any public deployment or hosting investment.

#### Scope

- A national data and update run on the local machine.
- The complete bilingual browser journey and sustained phone-map checks.
- An owner walkthrough with a recorded acceptance decision.

#### Out of scope

Public hosting and deployment, purchases, deferred roadmap features and manual mushroom field validation.

#### Child issues

- [ ] Verify the national data and update flow on the local machine
- [ ] Verify the complete bilingual journey and sustained phone-map use
- [ ] Record the owner's acceptance of the complete local MVP

#### Acceptance Criteria

- [ ] AC1: The local acceptance report records the national data checks and the complete browser journey.
- [ ] AC2: Actual phone checks do not reproduce the progressive slowdown and freeze seen in P5.
- [ ] AC3: The owner explicitly accepts the complete locally running product.
- [ ] AC4: No VPS deployment, domain purchase, DNS change or paid service is needed to complete this epic.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Epic classification

- Overall size: XL
- Overall risk: High
- Reason: Integrated data, map behavior and owner acceptance determine whether the MVP is actually complete.

### FND1. Start the Django application and PostGIS database locally

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The product needs an application structure separate from the experiment runner.

#### Proposed change

Use Book Corners as the reference for Django, Django Ninja, PostgreSQL with PostGIS and Docker Compose. Provide local settings, environment examples and a basic health endpoint. Keep the existing investigation package and commands usable. This ticket does not implement the product UI.

#### Acceptance Criteria

- [ ] AC1: `docker compose up` starts the application and geographic database using documented local defaults.
- [ ] AC2: The migration and health checks in `docs/local_development.md` succeed from an empty local database.
- [ ] AC3: An automated check confirms the database supports geographic values used by the application.
- [ ] AC4: The existing experiment CLI help and focused tests still run using the commands recorded in the local development guide.
- [ ] AC5: The setup needs no domain, VPS, deployment secret or paid service.

#### Dependencies

None.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: Application structure and geographic database initialization affect every later subsystem.

### FND2. Run background jobs and scheduled commands on the local machine

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

Weather and estimate updates need a worker that can be exercised before any server exists.

#### Proposed change

Reuse Book Corners' database-backed Django task and worker patterns. Provide a local worker process and a documented way to trigger a scheduled command. Separate the trigger from the weather and prediction logic, which later tickets supply.

#### Acceptance Criteria

- [ ] AC1: The local worker check in `docs/local_development.md` submits and completes a test job.
- [ ] AC2: A restart check confirms a queued job is retained and a completed job is not run twice accidentally.
- [ ] AC3: A failed-job check records the failure and leaves the worker usable for a subsequent job.
- [ ] AC4: The documented scheduler entry point can run locally without provisioning a VPS.

#### Dependencies

- Blocked by {{FND1}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: Normal
- Reason: This adds one local job execution subsystem.

### FND3. Add application checks without deployment automation

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The new application needs repeatable checks, but copying Book Corners wholesale could deploy before the owner accepts the MVP.

#### Proposed change

Adapt Book Corners' Python, PostGIS and frontend-build check patterns for SporaMeteo. Document the equivalent local commands. Include no deploy workflow, deployment environment, VPS access or domain setup.

#### Acceptance Criteria

- [ ] AC1: The documented local check command runs the application tests against a local PostGIS database.
- [ ] AC2: The GitHub Actions check workflow runs the same relevant checks and frontend build when frontend files exist.
- [ ] AC3: A workflow review recorded in `docs/local_development.md` confirms that no job publishes to a VPS or requires hosting credentials.
- [ ] AC4: The check setup does not require the owner to buy any service.

#### Dependencies

- Blocked by {{FND2}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: Normal
- Reason: This configures development checks without changing runtime product behavior.

### HAB1. Build a repeatable 500 m grid for all Italy

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The investigation grid covers a small area and uses boundaries that cannot be distributed in the app.

#### Proposed change

Extend the existing grid code for Italy using redistributable boundaries already considered in P6. Preserve the established 500 m identifier and coordinate conventions. Build in manageable parts and record the boundary source, version, licence and coverage.

#### Acceptance Criteria

- [ ] AC1: The documented grid-build command creates stable identifiers for mainland Italy, Sicily and Sardinia.
- [ ] AC2: `reports/mvp/italy_grid.md` lists the boundary source, licence, build command and counts by region.
- [ ] AC3: A repeat-build test confirms no duplicate identifiers and identical cells for unchanged inputs.
- [ ] AC4: A region-boundary test confirms that neighboring partitions do not omit or duplicate their shared edge cells.
- [ ] AC5: The generated distribution contains no GADM outline files.

#### Dependencies

- Blocked by {{FND1}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: Boundary licences and national grid joins affect coverage and redistribution.

### HAB2. Attach national terrain information to the grid

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The estimate method needs terrain values outside the habitat pilot.

#### Proposed change

Reuse the existing Copernicus terrain processing code to attach elevation and the supported terrain facts to Italy's grid. Cache downloads, process bounded regions and retain source information. Keep unavailable values explicit.

#### Acceptance Criteria

- [ ] AC1: The terrain-build command in `reports/mvp/italy_terrain.md` processes the national grid without loading the whole source dataset into memory.
- [ ] AC2: Fixture tests check coordinate alignment, elevation units and missing values.
- [ ] AC3: The report records coverage and gaps by region, including the Alps, Apennines and islands.
- [ ] AC4: A resumed build reuses completed source downloads and produces the same finished values.
- [ ] AC5: The dataset retains the Copernicus source version and required attribution.

#### Dependencies

- Blocked by {{HAB1}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: Coordinate or unit errors can produce plausible but incorrect habitat inputs.

### HAB3. Attach forest information and report habitat coverage

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The Tuscany inventory alone cannot support an Italy-wide product, and its records are old.

#### Proposed change

Reuse the investigated national Copernicus forest data as the common input. Join existing optional regional forest information where available, keeping its source and date separate. Report forest coverage and gaps. Do not add a public forest-exploration feature or revive the rejected soil input.

#### Acceptance Criteria

- [ ] AC1: The forest-build command in `reports/mvp/italy_habitat.md` produces forest values for the national grid and a coverage summary for every region.
- [ ] AC2: Join tests distinguish missing forest information from a known lack of forest cover.
- [ ] AC3: The report separates national source coverage from optional regional records and states their dates.
- [ ] AC4: An outside-Tuscany fixture confirms that absent regional inventory records do not suppress otherwise usable national inputs.
- [ ] AC5: Published derived regional values retain the applicable sharing terms and credits.

#### Dependencies

- Blocked by {{HAB1}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: Regional data age, missing values and licence conditions can silently affect national results.

### WEA1. Fetch weather by shared cells and account for the free allowance

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

Italy-wide weather must be fetched once for shared weather areas, not once per map square or visitor.

#### Proposed change

Extend the existing Open-Meteo client and cache for a national shared-cell request plan. Reuse the Forecast API and the P6 allowance assessment. Count requests using the provider's variable and date rules, including retries. Reuse stored recent weather where possible.

#### Acceptance Criteria

- [ ] AC1: `reports/mvp/weather_requests.md` records the national cell count and the planned daily and monthly counted usage against the allowance already documented in P6.
- [ ] AC2: Cache tests show that squares sharing a weather cell reuse its response.
- [ ] AC3: Request-accounting tests count long date ranges, variable counts and retries rather than only HTTP requests.
- [ ] AC4: A quota-limit test delays work instead of crossing the recorded minute, hour, day or month limits.
- [ ] AC5: The documented request-plan command runs without fetching national data or reopening the provider-pricing research.

#### Dependencies

- Blocked by {{HAB1}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: Provider accounting and cache keys determine whether nationwide updates fit the free service.

### WEA2. Build dated weather summaries for today and seven days ahead

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The app needs consistent daily inputs and recent rain totals, not raw weather responses.

#### Proposed change

Build the weather summaries required by the calculation and area details. Use Europe/Rome days, rain over 7, 14 and 30 completed days, and today plus seven future dates. Keep recent modelled weather distinct from forecasts. Carry available temperature, drying, frost or hail information without inventing missing fields.

#### Acceptance Criteria

- [ ] AC1: Weather date tests cover Italian midnight, daylight-saving changes and all eight target dates.
- [ ] AC2: Rain-window tests confirm exact 7, 14 and 30 completed-day totals and distinguish them from forecast rain.
- [ ] AC3: Missing-input tests preserve unknown values instead of inserting zero rain or invented optional weather.
- [ ] AC4: Forecast-window tests use the weather available for each target date without substituting later observed outcomes.
- [ ] AC5: `reports/mvp/weather_dates.md` records the source fields, units, date rules and a representative saved example.

#### Dependencies

- Blocked by {{WEA1}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: Date boundaries and weather windows can create convincing but incorrect estimates.

### WEA3. Schedule a daily weather update and retain complete batches

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

A failed download or overlapping job must not leave the application with a partially updated weather dataset.

#### Proposed change

Add a local daily weather command using the shared client and dated summaries. Record complete batches, source timestamps, counted usage and failures. Publish only complete batches required by the selected input rules. Preserve the previous usable batch on failure.

#### Acceptance Criteria

- [ ] AC1: The documented local update command in `reports/mvp/weather_updates.md` completes a batch and records its dates, source and usage.
- [ ] AC2: An interrupted-download test leaves the previous completed batch available and marks the new batch incomplete.
- [ ] AC3: A repeated-trigger test prevents overlapping runs from duplicating work or mixing batches.
- [ ] AC4: A retry test resumes supported work through the cache while respecting the allowance.
- [ ] AC5: The same entry point runs manually and through the local worker, with no hosted scheduler.

#### Dependencies

- Blocked by {{WEA2}}.
- Blocked by {{FND2}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: Batch consistency and failure recovery affect every displayed date.

### MOD1. Define and implement the experimental growing-probability method

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

Epic 1 did not establish calibrated probabilities, and the demonstration score is not a product calculation.

#### Proposed change

Implement one documented, versioned method for the existing porcini group using the actual terrain, forest and weather inputs. Start from the published knowledge and reusable code in Epic 1. Explain how the method produces its experimental percentage and contributing factors. Check whether regional season and altitude assumptions suit national use.

#### Acceptance Criteria

- [ ] AC1: `docs/forecast_method.md` defines the event, 500 m area, target day, input requirements, calculation and experimental limitations.
- [ ] AC2: Calculation tests produce repeatable percentages and matching contributing factors from fixed weather and habitat examples.
- [ ] AC3: Missing-input tests produce an unavailable result where required inputs are absent, rather than a false zero or an invented percentage.
- [ ] AC4: The method records its version and does not reuse P5's made-up scores or reliability labels.
- [ ] AC5: The report states that field validation, a measured accuracy target and automatic learning are not acceptance requirements.

#### Dependencies

- Blocked by {{HAB2}}.
- Blocked by {{HAB3}}.
- Blocked by {{WEA2}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: The calculation and its wording determine the meaning of the product's main result.

### MOD2. Calculate and publish one complete eight-date estimate update

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

Visitors must not see map cells and details assembled from different prediction runs.

#### Proposed change

Run the experimental method for the national grid and the eight requested dates after a complete weather update. Retain source references, method version, target dates and calculation time. Publish the finished update consistently and retain the previous one on failure.

#### Acceptance Criteria

- [ ] AC1: The local calculation command in `reports/mvp/estimate_updates.md` produces all eight target dates from a completed weather batch.
- [ ] AC2: Publication tests confirm that readers see either the previous complete update or the new complete update, never a mixture.
- [ ] AC3: Failure tests preserve previous results with their original dates and update time.
- [ ] AC4: Date-rollover tests never relabel an old target date as a new forecast day.
- [ ] AC5: A repeat-run test confirms that the same inputs and method version produce the same results.

#### Dependencies

- Blocked by {{MOD1}}.
- Blocked by {{WEA3}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: Publishing partial or incorrectly dated estimates can mislead every map user.

### MOD3. Serve map estimates by date and visible area

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The map needs bounded responses for local detail and nationwide browsing.

#### Proposed change

Use Django Ninja to expose the stored map results for a requested date and visible area. Include update identity and missing-data states. Limit or summarize large views while retaining selectable 500 m areas at closer zoom. Serve stored results without making weather requests.

#### Acceptance Criteria

- [ ] AC1: API tests confirm that requested dates and map bounds select the correct results from one published update.
- [ ] AC2: Invalid-date and oversized-view tests return a defined error or documented summarized response.
- [ ] AC3: A national-view response-size check is recorded in `reports/mvp/map_api.md`.
- [ ] AC4: A no-weather-fetch test confirms that repeated browsing requests only read stored results.
- [ ] AC5: Unavailable estimates remain distinguishable from zero percent in API response tests.

#### Dependencies

- Blocked by {{MOD2}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: API contracts and national map response sizes affect correctness and phone usability.

### MOD4. Serve area explanations, weather and source details

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

An area percentage needs its supporting facts, weather and limitations from the same calculation.

#### Proposed change

Expose selected-area details through Django Ninja. Include the selected date, experimental percentage, contributing weather and habitat facts, recent rain periods, supported weather fields, source dates, update identity, real input detail and required credits.

#### Acceptance Criteria

- [ ] AC1: API tests confirm that details match the selected grid area, date and published update.
- [ ] AC2: Explanation tests confirm that changing a contributing input changes the relevant explanation.
- [ ] AC3: Weather tests expose 7, 14 and 30 completed-day rain totals separately from forecast weather.
- [ ] AC4: Missing-data tests return explicit reasons without invented confidence labels or optional values.
- [ ] AC5: `reports/mvp/area_api.md` records the response contract, experimental wording and source-credit fields.

#### Dependencies

- Blocked by {{MOD2}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: The API joins the percentage, explanations and weather into a single claim.

### DES1. Write the shared mockup brief and Google Stitch prompt

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The two design alternatives need the same agreed scope so the owner can compare them.

#### Proposed change

Write `docs/design/mvp_mockup_brief.md` and a ready-to-paste prompt in `docs/design/google_stitch_prompt.md`. Use the PRD's selected features and companion positioning. Include phone and desktop layouts, bilingual examples and the requirement for a polished interface.

#### Acceptance Criteria

- [ ] AC1: The brief maps every selected MVP feature to a screen or interaction to show.
- [ ] AC2: The Stitch prompt includes the eight-date map, search, layer controls, area details, weather, favorites, navigation and language switch.
- [ ] AC3: The brief lists loading, empty, missing-data, location-denied and error states for both alternatives.
- [ ] AC4: A checklist in the brief excludes accounts, diaries, alerts and other deferred features.
- [ ] AC5: Both documents state that the owner will choose a design before production UI implementation.

#### Dependencies

None.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: S
- Risk: Normal
- Reason: This prepares two short design documents from settled product requirements.

### DES2. Produce the Google Stitch mockup for phone and desktop

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The owner needs to see an actual Google Stitch alternative before choosing the UI.

#### Proposed change

Use the prepared prompt with Google Stitch. Save the resulting design artefacts or reviewable links with the prompt version. Cover the shared brief with representative sample data clearly treated as mockup content.

#### Acceptance Criteria

- [ ] AC1: `docs/design/stitch_mockup.md` links or embeds the actual Stitch output and records the prompt used.
- [ ] AC2: The output shows phone and desktop versions of the main map and selected-area journey.
- [ ] AC3: The brief's state checklist records how loading, missing data and errors appear.
- [ ] AC4: Italian and English examples demonstrate that the layouts accommodate both languages.
- [ ] AC5: The design remains within the selected MVP features and uses no production deployment.

#### Dependencies

- Blocked by {{DES1}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: Normal
- Reason: This produces one bounded design alternative for review.

### DES3. Create an independent agent mockup for phone and desktop

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The owner wants an alternative made directly by the agent to compare with Stitch.

#### Proposed change

Create a distinct visual proposal using the same brief and representative sample content. Supply reviewable phone and desktop artefacts or a local prototype. Treat this as design work, not the production UI implementation.

#### Acceptance Criteria

- [ ] AC1: `docs/design/agent_mockup.md` records and links the agent-produced proposal.
- [ ] AC2: The output covers the same main journey and state checklist as the Stitch alternative.
- [ ] AC3: Phone and desktop layouts show the curated typography, spacing, map controls and area details.
- [ ] AC4: Italian and English examples fit without obscuring the map or controls.
- [ ] AC5: The prototype or artefacts can be reviewed without deploying to a VPS or buying services.

#### Dependencies

- Blocked by {{DES1}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: Normal
- Reason: This produces one bounded design alternative for review.

### DES4. Compare both mockups and record the owner's design choice

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

Production UI work must follow the owner's choice after seeing both alternatives.

#### Proposed change

Present both alternatives against the shared brief. Record the owner's selected direction, requested adjustments and the visual and interaction rules to implement in `docs/design/selected_design.md`.

#### Acceptance Criteria

- [ ] AC1: The decision document links both phone and desktop alternatives and compares them against the agreed journey.
- [ ] AC2: The owner explicitly selects the direction and any requested adjustments are recorded.
- [ ] AC3: The chosen design defines the layout, type, colors, controls and required user-facing states.
- [ ] AC4: The issue remains open while the owner's design choice is pending; producing mockups alone does not complete it.

#### Dependencies

- Blocked by {{DES2}}.
- Blocked by {{DES3}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: S
- Risk: Normal
- Reason: This records a concrete owner decision that blocks production UI work.

### WEB1. Implement the selected responsive layout and language controls

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The product needs the selected visual design implemented consistently across screen sizes.

#### Proposed change

Use Book Corners' Django templates, HTMX, Tailwind and daisyUI patterns to implement the approved layout and shared components. Add Italian and English language handling and shared loading, empty and error states. Keep this ticket to the page structure and reusable controls.

#### Acceptance Criteria

- [ ] AC1: The visual checks in `reports/mvp/ui_layout.md` compare phone and desktop layouts with the selected design.
- [ ] AC2: Language tests confirm Italian and English navigation, shared notices and error text.
- [ ] AC3: A language-switch test preserves the selected area and date when those values exist.
- [ ] AC4: Keyboard and readable-text checks cover the shared controls without relying on color alone.
- [ ] AC5: The page opens locally without registration, ads, subscriptions or hosting credentials.

#### Dependencies

- Blocked by {{DES4}}.
- Blocked by {{FND1}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: Shared layout and translation behavior affect every later interaction.

### WEB2. Add the probability map, date control and background styles

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

Visitors need to explore experimental estimates across areas and dates in the chosen design.

#### Proposed change

Implement the map using the stored-result API, the Book Corners map approach where suitable and the providers already assessed in P6. Add today plus seven dates, at least two OpenStreetMap background styles, overlay visibility, opacity and the experimental legend.

#### Acceptance Criteria

- [ ] AC1: Browser checks in `reports/mvp/map_controls.md` cover all eight dates, background switching, overlay visibility and opacity.
- [ ] AC2: The map identifies the selected date and the current published update, with explicit unavailable and stale states.
- [ ] AC3: An out-of-order-response test prevents an older request from replacing the visitor's latest area or date selection.
- [ ] AC4: Map credits and the experimental explanation remain readable on phone and desktop.
- [ ] AC5: A bounded-rendering check confirms that a national view does not draw every 500 m cell at once.

#### Dependencies

- Blocked by {{WEB1}}.
- Blocked by {{MOD3}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: Map rendering, asynchronous requests and multiple controls can desynchronize displayed results.

### WEB3. Add place search and optional current location

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

Visitors need to reach an Italian place without knowing coordinates or granting location access.

#### Proposed change

Add place search with selectable results and an explicit current-location action. Reuse suitable Book Corners patterns and respect the selected search provider's usage rules. Provide clear empty, failed and permission-denied states in both languages.

#### Acceptance Criteria

- [ ] AC1: Browser checks in `reports/mvp/place_search.md` cover a successful search, multiple results, no results and a failed lookup.
- [ ] AC2: A selected result moves the map to the intended location and permits area inspection.
- [ ] AC3: Permission tests confirm that geolocation is requested only after the visitor's action.
- [ ] AC4: A denied-location check leaves place search and manual browsing usable.
- [ ] AC5: The report records the search source, its required credits and request-limit handling.

#### Dependencies

- Blocked by {{WEB2}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: Normal
- Reason: This adds one location-discovery flow with defined failure states.

### WEB4. Show the selected area's estimate, weather and explanation

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

A colored map alone does not explain what its percentage means or why it was produced.

#### Proposed change

Implement the selected-area panel from the chosen design. Show the percentage, target day, experimental status, contributing facts, weather, recent rain periods, update time, sources and actual weather detail. Provide complete Italian and English wording.

#### Acceptance Criteria

- [ ] AC1: Browser checks in `reports/mvp/area_details.md` show that map selection and date changes update the correct area details.
- [ ] AC2: The panel distinguishes 7, 14 and 30 completed-day rain totals from predicted weather.
- [ ] AC3: Missing and stale data checks show the reason and actual update time without a false zero or invented confidence.
- [ ] AC4: Both languages explain that percentages are experimental and have not been validated.
- [ ] AC5: Phone and desktop checks confirm that the panel does not prevent use of map and date controls.

#### Dependencies

- Blocked by {{WEB2}}.
- Blocked by {{MOD4}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: The panel presents the meaning and evidence behind the experimental percentage.

### WEB5. Save and manage private favorites in the current browser

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

Visitors need to return to useful areas without creating an account.

#### Proposed change

Add a browser-local favorites list for selected points or grid areas. Support names, optional colors, reopening, renaming and removal. Explain that favorites stay in this browser, do not synchronize and can be lost when browser data is cleared.

#### Acceptance Criteria

- [ ] AC1: Browser checks in `reports/mvp/favorites.md` cover add, reload, reopen, rename, color selection and removal.
- [ ] AC2: Reopening a favorite selects the intended area and current forecast rather than storing an old percentage.
- [ ] AC3: A local-storage failure check gives a clear message without falsely claiming that the place was saved.
- [ ] AC4: The privacy check confirms that saving a favorite creates no public record or model-training submission.
- [ ] AC5: The full flow and storage explanation work in Italian and English.

#### Dependencies

- Blocked by {{WEB4}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: Normal
- Reason: This adds local personal state without accounts or server synchronization.

### WEB6. Open the selected destination in an external navigation app

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

Visitors need to hand the selected destination to their navigation app.

#### Proposed change

Add the external-navigation action from the selected design. Use the actual selected coordinates and provide an appropriate browser fallback. Keep route calculation and GPS tracking outside SporaMeteo.

#### Acceptance Criteria

- [ ] AC1: A destination-link test confirms the generated link uses the selected point or documented grid-area destination.
- [ ] AC2: Phone and desktop checks in `reports/mvp/navigation.md` confirm that the action opens a navigation destination or usable browser fallback.
- [ ] AC3: Italian and English labels explain the action and an unavailable-destination state.
- [ ] AC4: The action does not add route planning, parking discovery or location tracking.

#### Dependencies

- Blocked by {{WEB4}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: S
- Risk: Normal
- Reason: This adds a focused link-out action to the existing area panel.

### ACC1. Verify the national data and update flow on the local machine

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

Separate subsystem checks do not establish that the national data and eight-day estimates work together within the existing service allowance.

#### Proposed change

Run the complete local build and update flow with real national inputs. Record coverage, counted weather usage, elapsed time, memory and disk use. Exercise failed refresh and date rollover using controlled checks. Reuse P6 instead of conducting another pricing investigation.

#### Acceptance Criteria

- [ ] AC1: The data section of `reports/mvp/local_acceptance.md` records commands, source versions, regional coverage and genuine data gaps.
- [ ] AC2: The report records a complete eight-date estimate update and matching map and detail responses.
- [ ] AC3: Recorded daily and monthly counted usage fits the established Open-Meteo limits, including the proposed cache and refresh behavior.
- [ ] AC4: Failure and rollover checks retain correctly dated previous results and expose unavailable future dates honestly.
- [ ] AC5: All work runs locally without buying services, uploading the app to a VPS or collecting field observations.

#### Dependencies

- Blocked by {{FND3}}.
- Blocked by {{MOD3}}.
- Blocked by {{MOD4}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: This checks the national integration, usage accounting and failure behavior.

### ACC2. Verify the complete bilingual journey and sustained phone-map use

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

P5 froze during sustained use on an iPhone, and a working desktop page does not establish that the complete MVP is usable.

#### Proposed change

Check the finished local product on desktop, an actual iPhone with Safari and an Android phone browser. Phones may use the local network. Follow the approved visual design and exercise the complete Italian and English journey. Record any unmet requirement rather than treating automated checks as owner acceptance.

#### Acceptance Criteria

- [ ] AC1: The browser section of `reports/mvp/local_acceptance.md` records devices, browsers, viewport sizes and evidence for the full journey in both languages.
- [ ] AC2: The phone checks include at least 25 map moves plus date, background and opacity changes, without the progressive slowdown or freeze seen in P5.
- [ ] AC3: The report verifies search, denied location permission, explanations, recent weather, favorites and navigation.
- [ ] AC4: The report verifies loading, empty, missing-data, stale-data and error states against the selected design.
- [ ] AC5: Every required check has an explicit result; unresolved failures remain open before the owner acceptance ticket can complete.

#### Dependencies

- Blocked by {{ACC1}}.
- Blocked by {{WEB3}}.
- Blocked by {{WEB5}}.
- Blocked by {{WEB6}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: M
- Risk: High
- Reason: Real-device rendering and combined interactions can fail despite isolated tests.

### ACC3. Record the owner's acceptance of the complete local MVP

Source: `docs/product_prd.md`, following the completed product interview. Epic 1 reports provide evidence, not MVP scope.

#### Problem

The owner must be satisfied with the complete product before investing in a domain or VPS.

#### Proposed change

Provide the documented local startup and walkthrough, present the complete product and record the owner's decision in `reports/mvp/local_acceptance.md`. Address or track requested corrections before seeking a new decision. This ticket does not authorize hosting or publication.

#### Acceptance Criteria

- [ ] AC1: The owner-decision section identifies the tested revision and links the completed local data and browser evidence.
- [ ] AC2: The owner has tried the complete locally running MVP and explicitly confirmed satisfaction.
- [ ] AC3: Any required corrections are resolved before the acceptance decision is recorded as complete.
- [ ] AC4: The issue remains open if the owner requests changes or has not decided; technical checks alone cannot close it.
- [ ] AC5: The report records public deployment and hosting investment as separate later work requiring explicit authorization.

#### Dependencies

- Blocked by {{ACC2}}.

#### Delivery constraint

Build and verify this work locally. The complete MVP must receive the owner's explicit acceptance before any VPS deployment or domain or hosting investment. This issue authorizes no purchase, DNS change or public deployment.

#### Implementation classification

- Estimated size: S
- Risk: Normal
- Reason: This records the owner's product acceptance rather than implementing another subsystem.

### ROADMAP. Features Roadmap

### Growth estimates and dates

| ID | Feature |
|---|---|
| F03 | A separate habitat map showing where porcini can live, apart from daily growth estimates. |
| F06 | Replay past dates and distinguish saved predictions from later reconstructions. |
| F07 | Compare areas, rank nearby options and suggest the best day for an area. |
| F08 | Distinguish individual porcini types or species. |
| F09 | Add other mushrooms or edible plants. |
| F10 | Show seasonal calendars and stages of mushroom growth. |
| F82 | Automatically improve the prediction method using new public mushroom observations. |

### Map controls and environmental information

| ID | Feature |
|---|---|
| F15 | Explore elevation, slope, direction, shade and drainage. |
| F16 | Explore forest type, host trees, tree age, density and cover. |
| F17 | Explore soil acidity, moisture and temperature. |
| F19 | Show weather stations, historical charts and downloadable reports. |
| F20 | Map protected areas, gathering restrictions and closed days. |
| F21 | Show published sightings with species, date and identification filters. |
| F22 | Draw or select forest boundaries for analysis. |

### Personal places and outing records

| ID | Feature |
|---|---|
| F24 | Keep a find journal with dates, locations, species, quantities and condition details. |
| F25 | Record unsuccessful searches, time spent and possible reasons for finding nothing. |
| F26 | Fill records with weather and photo dates or locations, with corrections. |
| F27 | Attach photos, text and voice notes, with bulk import. |
| F28 | Compare outings with weather and predictions, and summarize seasons and previous years. |
| F29 | Reconstruct past outings from records or photos entered later. |
| F30 | Offer account synchronization and storage choices for personal records. |
| F31 | Back up, restore, import, export and delete broader personal records. |
| F32 | Monitor places or species and send weather, growth or reminder alerts. |

### Offline use

| ID | Feature |
|---|---|
| F33 | Download map backgrounds and terrain or forest layers. |
| F34 | Keep forecasts and area information available offline with their date and expiry. |
| F35 | Read and create personal records offline, with later synchronization. |
| F36 | Use identification and reference tools offline. |
| F37 | Use downloaded routes and return guidance without a connection. |
| F38 | Manage download sizes, interrupted downloads, repairs and removal. |

### Reaching an area and recording the walk

| ID | Feature |
|---|---|
| F40 | Show trails, contours, 3D terrain and printable maps. |
| F41 | Create walking routes, estimate travel time and plan multi-day trips. |
| F42 | Record GPS routes, duration and distance. |
| F43 | Save parking and provide compass, altitude and return-to-car guidance. |
| F44 | Share a live outing, last position and expected return deliberately. |
| F45 | Provide wrong-turn and group-separation alerts, return checks and emergency messages. |
| F46 | Import and export route files and exchange routes with watches. |
| F47 | Record finds through lock-screen or watch controls. |

### Privacy, sharing and community

| ID | Feature |
|---|---|
| F48 | Control exact, approximate, trusted-person and private visibility for records. |
| F49 | Share selected places or records by link, QR code or file, with optional expiry. |
| F50 | Let users decide whether their personal records may improve predictions. |
| F51 | Publish and search community observations or approximate totals. |
| F52 | Offer invitations, groups, companions, chat, posts and followed activity. |
| F53 | Provide reporting, blocking, moderation and appeals. |
| F54 | Ask the community to suggest or review mushroom identifications. |
| F55 | Show verified experts or trusted contributors. |
| F56 | Add achievements, friend challenges, rankings and rubbish-collection records. |
| F57 | Export account data and delete accounts. |

### Identification and learning

| ID | Feature |
|---|---|
| F58 | Provide species reference cards with names, photos, habitat and season. |
| F59 | Compare similar species and explain dangerous lookalikes. |
| F60 | Suggest species from photos, with clear limits on identification. |
| F61 | Guide identification through visible traits and illustrated questions. |
| F62 | Offer consultation with a human expert. |
| F63 | Provide quizzes, practice exams and review of mistakes. |
| F64 | Provide field exercises and learning progress. |
| F65 | Publish guides, growth bulletins, newsletters and website badges. |

### Permits and commercial services

| ID | Feature |
|---|---|
| F66 | Sell permits and retain purchase history or wallet passes. |
| F67 | Store an existing permit's authority, number, receipt, cost and expiry. |
| F68 | Notify users about restrictions and changes to gathering rules. |
| F69 | Offer outdoor bookings, authority or retailer tools and member benefits. |
| F71 | Suggest recipes and routes between ingredient locations. |

### Website access and supporting choices

| ID | Feature |
|---|---|
| F73 | Provide native phone or tablet apps. |
| F74 | Make the website installable as an app. |
| F77 | Provide accounts and sign-in methods. |
| F78 | Show other outdoor conditions, such as snow, air quality or insect activity. |
| F79 | Accept local weather corrections and structured field measurements. |
| F80 | Publish prediction evaluation methods, errors and failed targets. |
