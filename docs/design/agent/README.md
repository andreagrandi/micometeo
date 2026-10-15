# Agent mockup: daylight field map

This folder holds the agent-made design for #53. It is the second of the two
alternatives that #54 compares with the Stitch result in
`docs/design/stitch/`. Nobody has chosen it as the app design.

It is a disposable HTML, CSS and JavaScript prototype. It is a source of UI to
copy. Nothing in it is used by the app, and `apps/` is unchanged.

## How to look at it

Serve this folder and open the viewer:

```sh
python3 -m http.server 8766 --bind 127.0.0.1 --directory docs/design/agent
```

Then open `http://127.0.0.1:8766/index.html`. The toolbar picks the language,
the page, the state and the size: phone 390 by 844, small phone 320 by 568,
desktop 1440 by 900, or all three side by side. The desktop frame is scaled
down to fit, and the toolbar shows the scale.

The pages can also be opened directly:

- `app.html?lang=it` or `app.html?lang=en` is the map app.
- `app.html?lang=en&state=older_update` opens a state. The states are listed
  under "Required states".
- `landing.html?lang=it` is the landing page.

The pages load Leaflet, the Atkinson Hyperlegible Next font and OpenStreetMap
tiles from the internet. They read no production data and call no SporaMeteo
server.

## Files

| File | Content |
| --- | --- |
| `DESIGN.md` | Colours, type, spacing, controls, notices and layouts |
| `tokens.css` | The colours, sizes and notice styles shared by both pages |
| `index.html` | Viewer with the language, state and size pickers |
| `app.html`, `app.css`, `app.js` | Map app prototype |
| `strings.js` | Every Italian and English text of the map app |
| `landing.html`, `landing.css`, `landing.js` | Landing page, both languages |
| `build_sample_layers.py` | Builds the two files in `assets/` |
| `assets/italy_forest.png` | Forest share of Italy for the zoomed out view |
| `assets/sample_squares.js` | 1440 sample squares of 500 m around Abetone |

To rebuild the assets, run from the repository root:

```sh
uv run python docs/design/agent/build_sample_layers.py
```

The script reads the 2 km forest layer in
`data/processed/mvp_forest/italy-forest-copernicus-2018-v1/`, which is not
committed. The national image uses the real forest share and leaves out land
with less than 10% forest. The squares near Abetone take their forest share
from the same layer with random variation added. Their percentages are made
up. The Abetone square uses the brief's values: 68% forest, 42% on
12 October and 48% on 15 October.

## Design choices to compare with Stitch

- Look: near white surfaces, dark ink and one deep blue for buttons and the
  selected square. Stitch uses dark pine green, parchment and a serif face.
- Type: one face, Atkinson Hyperlegible Next, drawn for readers with low
  vision. It draws zero with a slash, so "2026" and "10:30" show slashed
  zeros. Turning this off is one CSS line if the owner prefers.
- Dates come first. On desktop the eight dates are a list on the left. Each
  row shows the full date and the selected square's percentage with a small
  bar, so the visitor can compare days at a glance. Stitch puts short dates in
  a strip under the map.
- Desktop details sit in a right column that shrinks the map instead of
  covering it. The dates, background and overlay controls stay in the left
  column, so they remain reachable while details are open.
- Phone layout: search and an eight-date chip row stay at the top. Details
  open as a sheet from the bottom with three heights. The sheet never covers
  the search or the dates, so the date can change with details open. "Back to
  map" closes it. Stitch has no phone map layout.
- The map shows real OpenStreetMap backgrounds under the squares. "High
  contrast" is the same tiles in grey with more contrast. Stitch shows the
  squares on a plain green shape.
- The zoomed out view shows the real forest share of all Italy in green,
  without estimates. Estimates appear when the map is 60 km wide or closer.
  The app works this out from the map width, not from a zoom level.
- Squares without an estimate never look like a low percentage. Missing data
  is grey with diagonal lines. Less than 10% forest is a dotted outline with
  no fill. The legend names both in words.
- Landing page: a hero with a small live map of the Abetone sample, then what
  the percentage means and does not mean, how the estimate is made, what the
  map can do, what is free and private, sources, and a reminder that picking
  rules depend on the region. Its copy uses only facts from the brief and the
  PRD.

## Required states

Pick a state in the viewer, or add `state=` to `app.html`. States that need a
selected square open on Abetone with 15 October chosen.

| State | Visible message and next action |
| --- | --- |
| `loading` | Progress bar on the map and "Loading estimates for Thursday 15 October" |
| `first_fetch` | "Waiting for weather for this area." in place of the percentage |
| `missing_data` | "No estimate because required data is missing.", "Pick another square" and "Try again" |
| `older_update` | Target 15 October 2026, assessment 11 October 2026, update 11 October 2026 at 10:30 CEST |
| `request_error` | Error with "Try again", and the older result shown with its dates |
| `no_results` | "No places found", with a hint to change the search or move the map |
| `location_denied` | "Location access was not granted", with search and map browsing still offered |
| `storage_unavailable` | "Favorite not saved in this browser", nothing pretends to be saved |
| `less_forest` | "This square has less than 10% forest. No estimate is available." |

## Working and static parts

These work in the prototype, with sample data:

- Selecting a square, the eight dates with a short loading step, and the
  details for any square.
- Search for "Abetone". Any other text gives the no results state.
- "Use my location", which moves to Abetone with a marker labelled as
  simulated.
- Both backgrounds, hide and show overlay, and the opacity slider.
- Favorites in browser storage: save, name, colour, rename, recolour, reopen
  and remove.
- "Open navigation", with Google Maps, Apple Maps and `geo:` links for the
  sample point.
- Language switch that keeps the square, date, map view and open panels.
- Keyboard use: Escape closes panels and focus returns to the control that
  opened them. Squares are drawn on a canvas and cannot take focus, so a
  "Select square at map centre" button appears when estimates are shown.

These are simulated or static:

- All values are sample values. Weather and rain are the same for every
  square and date.
- The location is never read. The states are set from the viewer, not caused
  by real failures.
- Changing background or overlay does not show the loading step. Only date
  changes and "Try again" do.

## Feature checklist

From `docs/design/brief.md`. "Working" means the interaction runs in the
prototype. "Static" means the UI is shown without real behaviour.

| Item | Where | Result |
| --- | --- | --- |
| F01 whole experimental percentage | Squares, date list, details, with the experimental notice under it | Working |
| F02 national forest view and no estimate state | Zoomed out forest view, `missing_data` state | Working |
| F04 today's estimate | First date row or chip, labelled "Today" | Working |
| F05 next seven dates | Date list on desktop, chip row on phones, full localised dates | Working |
| F11 weather and habitat explanation | Details: contributing facts, weather, forest share | Working |
| F12 sources, update time, missing information | Details: sources, update, 11 by 8 km weather area note, missing hail | Working |
| F13 search, location, map selection, failures | Search row and map, `no_results` and `location_denied` | Working, location simulated |
| F14 two backgrounds, visibility, opacity | Left column on desktop, Layers panel on phones | Working |
| F18 target day weather, 7, 14 and 21 day rain | Details | Working |
| F23 favorites | Favorites panel and save dialog, `storage_unavailable` | Working |
| F39 external navigation | Details, "Open navigation" | Working, opens real map links |
| F70 free, no ads, no subscription | Top bar line "Free, no account", landing page | Static |
| F72 phone and desktop | Every screen and state at 390, 320 and 1440 wide | Working |
| F75 Italian and English | Language switch on both pages and the viewer | Working |
| F76 no registration | Whole journey runs without sign in | Working |
| F81 coherent design | One set of rules in `DESIGN.md` for both pages | Static |

Both notices from the brief appear on every page. The design example notice
sits at the top and inside the details. The experimental notice sits under
every estimate percentage and nowhere else.

## Limitations

- At 320 by 568 the short sheet leaves about 140 px of map. To save room, the
  design notice band is hidden while a sheet or panel is open on screens under
  640 px high. The same notice stays inside the details.
- The squares are made-up values. They show the colour scale, not a forecast.
- The full keyboard path was checked only for focus return from panels, not
  tab by tab through every control.
- The Italian copy was written by the agent. The owner should reread it.
- Without internet, the map, tiles and font do not load.
