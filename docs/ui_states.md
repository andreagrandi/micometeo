# Web UI states and shared state

Issue #55 owns the Django shell, language behavior, formatting helpers and
shared state contract. Later map, search, details, favorites and navigation
issues replace the marked boundaries without changing the page shell.

## State ownership

| State | Owner in the shell | Later replacement |
| --- | --- | --- |
| Selected square | `data-selected-square` and the `square` URL parameter | #56 map selection |
| Target date | `data-target-date` and the `date` URL parameter | #56 date results |
| Map centre and zoom | `data-map-center`, `data-map-zoom`, and URL parameters | #56 Leaflet map |
| Update and assessment date | `data-update-id`, `data-assessment-date`, and URL parameters | #58 stored update |
| Language | An explicit `micometeo_language` cookie, then browser `Accept-Language` | Shared by every page |
| Open panel and folded cards | `data-open-panel` actions, root `data-panel`, `data-fold` controls, and URL parameters | #56 map controls |
| Details panel and sheet height | root `data-details-open`, aside `data-details`, `data-close-details`, `data-sheet-height`, and URL parameters | #58 real area contents |
| Map layers | `data-overlay`, `data-opacity`, background radio inputs, and URL parameters | #56 map controls |
| Search and location | Accessible controls with shell feedback | #57 place service |
| Favorites | Translated message explaining that saving comes later | #59 private favorites |
| Navigation | A labelled shell action | #60 external map links |

Changing language reloads the page and keeps the current state URL parameters.
The square, date, update, assessment date, map centre, zoom, open panels,
folded cards, sheet height and layer settings survive the switch and a later
reload. An unsupported browser
language falls back to English. Browser language detection does not set the
language cookie. The visible language switch sets `micometeo_language`.
Forecast dates are ISO calendar days and are displayed in Europe/Rome.
`web_ui.formatting` and `window.MicometeoFormatting` keep this rule in one
place. The browser names are `formatDate`, `formatNumber` and
`formatMeasurement`. Italian displays `12,5 mm` and `11 ottobre 2026`; English displays
`12.5 mm` and `11 October 2026`.

## Selected-area details

The live details sheet opens after a map square is selected. Its identity is
the square ID, target date and update UUID from the map response. The sheet
requests `/api/v1/areas/{square_id}` with the target date and, when present,
the same update UUID. The request omits `update_id` only when the map has no
selected update. A request is current only while all three identity values
match the current selection. A later response cannot replace a newer square,
date or update.

The sheet shows the whole percentage from `estimate.whole_percentage`, so zero
is shown as `0%`. A missing estimate keeps the percentage unavailable and
shows its stored reason. HTTP 404 and 409 responses classify the square as
having no detail for that update. Other failed requests show a retry action.
Old results retain their facts and sources and show the assessment and
calculation dates.

Facts use the response values, units and inclusive periods. The selected-day
weather section is separate from recent rain. The rain controls show 7, 14 and
21 completed days ending on the day before the assessment date. They never
include rain from the selected target day or a later day. Optional weather
values and recorded gaps remain visible as unavailable. The sheet renders no
hail value, confidence percentage or accuracy label unless the API supplies a
supported value. Weather source records include model, retrieval time, source
points, detail limits and required credits. The selected square is 500 m wide,
while a weather value can cover several kilometres.

The API's `selection.representative_coordinates` is the selected destination
for a square. An exact search, geolocation or map-click point remains separate
from that representative. The current map centre is never used as a
destination. Closing the sheet keeps the selected map day, invalidates its
detail request and returns focus to the map. Escape follows the same path.

Fixture pages remain gated behind `MICOMETEO_UI_FIXTURE_PAGES=true`. The
normal `/map/` route renders only responses from the live API and does not use
illustrative details.

On 13 October 2026, a standalone headed Chromium session with a persistent
profile checked the live panel with intercepted area API responses. The
checks used English at 1440 by 900 and 320 by 568, and Italian at 390 by 844.
The first phone check found a hidden square heading and close button. Both
remain visible after the fix, including while scrolling through the sources.
The final checks found no horizontal overflow or JavaScript errors. Selecting
7, 14 and 21 days retained focus on the chosen rain button. Escape closed the
panel, returned focus to the map and preserved the target date. Source credits
and the weather detail explanation remained readable in the phone sheet.

The full local run used `uv run pytest --tb=short -q` and finished with 727
passes and two failures. Both failures came from a browser assertion that
still expected English missing-data text in the Italian case. After correcting
the assertion and the final weather-unit rendering, the 12 affected browser
cases passed in Chromium and WebKit. The 18 focused retry, expired-update,
destination and keyboard cases also passed. Django checks, translation checks,
JavaScript syntax and repository file checks passed. Rebuilding the map CSS
produced the same file. These results are local checks, not remote CI.

## Fixture states

Fixture pages are disabled by default. Enable them locally with
`MICOMETEO_UI_FIXTURE_PAGES=true` and open one of these routes:

```text
/map/fixture/loading/
/map/fixture/first_fetch/
/map/fixture/missing_data/
/map/fixture/older_update/
/map/fixture/request_error/
/map/fixture/no_results/
/map/fixture/location_denied/
/map/fixture/storage_unavailable/
/map/fixture/less_forest/
/map/fixture/ready/
```

Each non-ready route has a `data-fixture` identity and one visible
`data-state-message`. The ready route provides the selected result shell. The
fixture copy is illustrative and never appears on `/map/` unless a later ticket
supplies real stored data.

## CSS and browser evidence

`assets/css/input.css` and `assets/css/landing.css` are the source files.
`npm run build:css` writes `app.css` and `landing.css` under
`apps/application/web_ui/static/web_ui/`. The selected design uses Plus
Jakarta Sans for map controls, Newsreader for headings and JetBrains Mono for
coordinates, dates and measurements. Desktop layout targets 1440 by 900 and
phone layout targets 390 by 844 and 320 by 568.

The map shell uses explicit CSS tokens and responsive rules. The landing page
uses the Tailwind build configured in `tailwind.landing.config.cjs`. Both
outputs are committed and CI checks for generated-file drift.

Install the browser engines once, then run the browser checks:

```sh
uv run playwright install chromium webkit
uv run pytest tests/e2e
```

The e2e fixture starts a local Django server with fixture pages enabled. Set
`MICOMETEO_BASE_URL` when an existing server should be reused. The checks cover
browser language fallback, explicit switching, URL state preservation, date and
measurement formatting, keyboard focus, all nine shared states, and phone
overflow in Chromium and WebKit.

Every shared state runs in Italian and English at both phone sizes. Keyboard
checks use Tab in Chromium and Alt+Tab in WebKit to include buttons in its
macOS keyboard navigation. They open Layers, change the overlay and return
focus with Escape.

On 12 October 2026, the landing page and selected-area fixture were compared
in headed Chrome with `docs/design/final/` at 1440 by 900 and 390 by 844.
The map was also checked at 320 by 568. Temporary screenshots are under
`/tmp/micometeo55-*.png`.

The comparison restored the landing sections, regional cards, closing band
and footer. It also corrected the map's date strip, button borders, details
callout, phone zoom position and compact layout on short screens. On short
screens an open sheet hides the sample banner and footer, as in the approved
design. The date strip keeps its original eight days after date selection,
language changes and reloads.

Two differences follow the ticket boundaries and design decision. The map
background remains blank until #56 supplies Leaflet and map data. Both pages
use Plus Jakarta Sans, resolving the font choice assigned to #55. The landing
reference used DM Sans, so some line wrapping changes. Sample weather and
percentages only appear on the gated fixture routes. Search, location,
favorites and navigation show translated explanations that those features
come later.

The owner's landing-page correction on 12 October restores the four-card
probability scale from the Stitch reference and the illustrative altitude of
1,388 metres. The landing scale uses the supplied screenshot's wording and
ranges. This correction does not change the map legend or implement a live
six-hour update schedule.

Build the styles and translation catalogs with:

```sh
npm ci
npm run build:css
msgfmt --check apps/application/web_ui/locale/it/LC_MESSAGES/django.po
msgfmt --check apps/application/web_ui/locale/en/LC_MESSAGES/django.po
msgfmt --check apps/application/web_ui/landing_locale/it/LC_MESSAGES/django.po
uv run python apps/application/manage.py compilemessages --ignore .venv --locale it --locale en
```

The compiled `.mo` files are generated locally and remain ignored by Git.

The `#map` element owns the future persistent map instance. Details, shared
state messages and controls are separate templates that later requests can
replace. This shell reloads for a language change and restores state from the
URL. A later live map must restore that same state when replacing translated
controls.

Final local verification on 12 October 2026 passed 371 application checks and
100 browser checks, run separately. The browser run used
`MICOMETEO_BASE_URL=http://127.0.0.1:8035 uv run pytest tests/e2e --tb=short`.
CSS builds, translation compilation, Django checks and repository file checks
also passed. The final source review found no remaining material issues.
These are local results. Remote CI has not run for this change.

## Place and point selection

Issue #57 adds the selection state used by search, current location, map
clicks and the centre selection button. The browser emits a
`micometeo:selectionchange` event after the state changes.

The event detail contains:

- `point`, the exact latitude and longitude chosen by a search result,
  geolocation permission or a map click.
- `representative`, the configured square representative used when the
  visitor selects an area at the map centre.
- `destination`, which is the exact point when one exists and otherwise the
  representative point.
- `square`, the validated grid square ID, when the point is in coverage.
- `source`, one of `search`, `geolocation`, `map` or `centre`.
- `mapCentre`, the current map view centre. This remains separate from the
  selected destination.

Changing the target date, language, background, overlay or map centre keeps
the exact point and its source. A slower map response cannot replace a newer
selection. Search and geolocation first resolve the exact point against the
configured land geometry. The browser does not snap to a nearby square.
