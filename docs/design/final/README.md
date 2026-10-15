# Combined mockup

This folder holds the combined design for #54. It follows the owner's choice in
`docs/design/decision.md`. The look comes from the Stitch mockup. The phone
layout, the map, the nine states and the plain app labels come from the agent
mockup. When this folder and `decision.md` disagree, `decision.md` wins.

It is a disposable HTML, CSS and JavaScript prototype. It is a source of UI to
copy. Nothing in it is used by the app, and `apps/` is unchanged. The two
original mockups in `docs/design/stitch/` and `docs/design/agent/` stay as they
were.

This folder holds the map app and the landing page. The landing page is
`landing.html` and `landing.js`. It is a copy of the Stitch landing page with
its Tailwind setup, colours and fonts. Only text that claimed things
SporaMeteo does not have was changed, and `landing.js` adds English.

## How to look at it

Serve this folder and open the viewer:

```sh
python3 -m http.server 8771 --bind 127.0.0.1 --directory docs/design/final
```

Then open `http://127.0.0.1:8771/index.html`. The toolbar picks the language,
the page, the state and the size: phone 390 by 844, small phone 320 by 568,
desktop 1440 by 900, or all three side by side.

The map app can also be opened directly:

- `app.html?lang=it` or `app.html?lang=en` is the map app.
- `landing.html?lang=it` or `landing.html?lang=en` is the landing page.
- `app.html?lang=en&state=older_update` opens a state. The states are listed
  under "Required states".
- `app.html?lang=en&select=1` opens Abetone with 15 October chosen.
- `panel=layers`, `panel=legend`, `panel=favorites`, `panel=save` and
  `panel=nav` open a panel. `sheet=half` and `sheet=tall` set the phone sheet
  height. `bg=contrast`, `overlay=off` and `opacity=30` set the map controls.

The page loads Leaflet, the three fonts from Google Fonts and OpenStreetMap
tiles from the internet. It reads no production data and calls no SporaMeteo
server.

## Files

| File | Content |
| --- | --- |
| `tokens.css` | Colours, type, spacing, shadows and the two notice styles |
| `index.html` | Viewer with the language, page, state and size pickers |
| `app.html`, `app.css`, `app.js` | Map app prototype |
| `strings.js` | Every Italian and English text of the map app |
| `build_sample_layers.py` | Builds the two files in `assets/` |
| `assets/italy_forest.png` | Forest share of Italy for the zoomed out view |
| `assets/sample_squares.js` | 1440 sample squares of 500 m around Abetone |

To rebuild the assets, run from the repository root:

```sh
uv run python docs/design/final/build_sample_layers.py
```

The script reads the 2 km forest layer in
`data/processed/mvp_forest/italy-forest-copernicus-2018-v1/`, which is not
committed. The national image uses the real forest share. Land with less than
10% forest is fully transparent, so the map shows through. The squares near
Abetone take their forest share from the same layer with random variation
added. Their percentages are made up. The Abetone square uses the brief's
values: 68% forest, 42% on 12 October and 48% on 15 October.

## What changed from the two originals

- Look: Stitch fonts, colours, 4 px and 8 px corners and shadows only on what
  floats over the map. Section titles are in sentence case.
- Header: dark green band with the name, one line about the site, search,
  "Use my location" and favorites with a count. There is no free badge and no
  language switch.
- Desktop dates: a strip at the bottom centre of the map with the short
  weekday, the date and the percentage. The assessment date sits at the right
  end of the strip title. The left column is gone.
- Desktop controls: the background and overlay card at the top right of the
  map, zoom buttons of 36 px under it, the colour key at the bottom left and a
  footer line under the map with the language switch and the attribution.
- Phone: the agent layout with a chip row, a map with "Layers" and "Legend"
  buttons and a three height sheet. Zoom buttons are 44 px. The language
  switch sits in the footer line.
- Squares show colour only, with no numbers. They sit in their own map layer
  that multiplies with the map, so low values leave the map almost untouched
  and roads and place names stay readable. Squares have no border when zoomed
  out and a faint hairline once they are 16 px wide. The light background is
  the OpenStreetMap tiles muted to a parchment tone.
- Cards: the background and overlay card and the colour key fold with a
  chevron button. Both start open.
- Language switch: a globe icon and "IT / EN" with the current language in
  bold, in the footer line on desktop and phones.
- Weather area: a dashed outline of the 11 by 8 km weather area surrounds the
  selected square, with a label. The sample has no real weather grid, so the
  area is a block of 22 by 16 squares placed around Abetone.
- Zoomed out view: forest share of Italy, transparent where there is no
  forest.
- Details: place name and coordinate, "Save favorite" and "Open navigation"
  side by side, the date with the percentage in a dark badge, the
  experimental notice with an info icon and no title, the reason for the
  estimate, four tiles, past rain, the weather area note, and sources with the
  update times. The panel can be closed.
- Favorites: a drawer from the right on desktop and a full height sheet on
  phones. A card shows the colour dot, the name, the coordinate and today's
  percentage, with "Riapri", "Rinomina e colore" and "Rimuovi".

## Required states

Pick a state in the viewer, or add `state=` to `app.html`. States that need a
selected square open on Abetone with 15 October chosen.

| State | Visible message and next action |
| --- | --- |
| `loading` | Thin progress bar along the top of the map and "Loading estimates for Thursday 15 October" |
| `first_fetch` | "Waiting for weather for this area." in place of the percentage |
| `missing_data` | "No estimate because required data is missing.", "Pick another square" and "Try again" |
| `older_update` | Target 15 October 2026, assessment 11 October 2026, update 11 October 2026 at 10:30 CEST |
| `request_error` | Error with "Try again", and the older result shown with its dates |
| `no_results` | "No places found", with a hint to change the search or move the map |
| `location_denied` | "Location access was not granted", with search and map browsing still offered |
| `storage_unavailable` | "Favorite not saved in this browser", nothing pretends to be saved |
| `less_forest` | "This square has less than 10% forest. No estimate is available." |

Errors are red, older results are amber and waits are pine green.

## Working and static parts

These work in the prototype, with sample data:

- Selecting a square, the eight dates with a short loading step, and the
  details for any square.
- Search for "Abetone". Any other text gives the no results state.
- "Use my location", which moves to Abetone with a marker labelled as
  simulated.
- Both backgrounds, the overlay switch and the opacity slider.
- Zoom buttons, which also change between the forest view and the estimates.
- Favorites in browser storage: save, rename and recolour together, reopen and
  remove.
- "Open navigation", with Google Maps, Apple Maps and `geo:` links for the
  sample point.
- Language switch that keeps the square, date, map view and open panels.
- Keyboard use: Escape closes panels and the favorites drawer, and focus
  returns to the control that opened them. Squares are drawn on a canvas and
  cannot take focus, so a "Select square at map centre" button appears when
  estimates are shown.

These are simulated or static:

- All values are sample values. Weather and rain are the same for every
  square and date.
- The location is never read. The states are set from the viewer, not caused
  by real failures.
- Changing background or overlay does not show the loading step. Only date
  changes and "Try again" do.

## Limitations

- On a desktop screen under 1440 px wide with the details open, or under
  1000 px wide with them closed, the map is too narrow for the colour key and
  the date strip side by side. The strip then takes the full width and the
  colour key sits above it.
- On desktop the colour key is one small card with the five estimate
  swatches, the two no estimate swatches and a "More" toggle for the rest.
  Phones keep the full Legend panel.
- At 320 by 568 the short sheet leaves about 90 px of map. While a sheet or
  panel is open on screens under 640 px high, the design notice band and the
  footer line are hidden. The same notice stays inside the details.
- The squares are made-up values. They show the colour scale, not a forecast.
- The Italian copy was written by the agent. The owner should reread it.
- Without internet, the map, tiles and fonts do not load.
