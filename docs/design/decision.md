# Design decision for the map app and landing page

This file records the owner's choice between the two mockups for #54 and turns
it into rules for #55, #56 and #58.

## Status

- Decided by the owner on 12 October 2026.
- Choice: a specified combination. The look comes from the Google Stitch
  mockup. The phone layout, the map, the required states and the plain app
  labels come from the agent mockup. The sections below list every part.
- The combined mockup in `docs/design/final/` shows the result. When this file
  and the combined mockup disagree, this file wins.
- The owner approved the combined mockup as final on 12 October 2026, after
  two review rounds. Smaller issues are left for the app work in #55.
- Neither original mockup is rejected as a whole. Both stay unchanged as
  reference.

## The two alternatives

| | Stitch | Agent |
| --- | --- | --- |
| Issue | #52 | #53 |
| Folder | `docs/design/stitch/` | `docs/design/agent/` |
| How to view | `docs/design/stitch/README.md` | `docs/design/agent/README.md` |
| Map app | `micometeo_design_alternative_a/code.html` | `app.html` |
| Landing page | `micometeo_home_guida_esplorativa/code.html` | `landing.html` |
| Design rules | `micometeo_fieldwork/DESIGN.md` | `DESIGN.md` |

The Stitch `DESIGN.md` names DM Sans, but the Stitch pages the owner looked at
use Plus Jakarta Sans and JetBrains Mono. The pages are the reference, so this
file uses the fonts and colours from the `tailwind.config` block in the Stitch
`code.html`.

## Comparison

The owner compared both mockups on 12 October 2026, using screenshots at 1440
by 900 and 390 by 844 of the same Abetone sample in Italian. The journey and
states come from `docs/design/brief.md`.

### Journey

| Task from the brief | Stitch | Agent | Chosen |
| --- | --- | --- | --- |
| 1. Open without account, pick language | No language switch in the app, only in the viewer bar. Landing has "IT / EN" | "Italiano, English" switch in the header of both pages | Switch on the landing header and at the bottom of the map page |
| 2. Search, location, map browsing | Header search and location. Failures only in a separate panel | Header search and location, failures drawn in place | Stitch header look, agent failure messages |
| 3. Forests of Italy, zoom to estimates | Two "map level" buttons. No real map | Real forest share on OpenStreetMap, switches by map width with a hint | Agent behaviour, with transparent areas where there is no forest |
| 4. Read 42% today, then 48% on 15 October | Date strip under the map with short dates and percentages | Date list on the left with full dates and bars | Stitch strip on desktop, agent chip row on phones |
| 5. Details: weather, rain, forest, facts, sources | Badge, tiles, always open, jargon labels | Plain rows, can be closed | Stitch look, agent order and labels, can be closed |
| 6. Background, overlay, opacity | Floating card at the top right of the map | Left column on desktop, Layers panel on phones | Stitch card on desktop, agent Layers panel on phones |
| 7. Favorites | Drawer from the right with full actions | Centred dialog | Stitch drawer on desktop, full sheet on phones |
| 8. External navigation | Button in details | Button in details with three map links | Stitch button look, agent links |
| 9. Switch language keeping square and date | Not shown in the app | Works and keeps square, date and panels | Agent behaviour |
| Phone layout | None: the details sheet covers the whole map | Complete, with chips, map and a three height sheet | Agent |
| Landing page | Rich layout, invented facts, account icon | Plain layout, facts from the brief | Stitch layout, agent facts |

### Required states

| State from the brief | Stitch | Agent | Chosen |
| --- | --- | --- | --- |
| Loading after a date, map or layer change | Missing | Progress bar and message on the map | Agent |
| First weather wait | Listed in the state panel only | In place of the percentage | Agent |
| Missing data, no estimate | Listed in the state panel only | Message with "Pick another square" and "Try again" | Agent |
| Older stored update | Listed in the state panel only | Notice with target, assessment and update dates | Agent |
| Request error with retry | Listed in the state panel only | Error with "Try again" and the older result dated | Agent |
| No places found | Listed in the state panel only | Message under search, map still usable | Agent |
| Location denied | Listed in the state panel only | Message, search and map still offered | Agent |
| Browser storage unavailable | Listed in the state panel only | "Favorite not saved in this browser" | Agent |
| Less than 10% forest | Grey square with text | Dotted outline, no fill, text reason | Agent |

All states keep the agent wording and next actions, drawn with the Stitch
colours: red for errors, amber for older results, pine green for waits.

## Owner's decisions

These are the owner's answers on 12 October 2026, with the choice and the
reason they gave.

- D1 colours and type: Stitch. Monospace stays for coordinates and small
  numbers. Section titles use sentence case, not monospace capitals.
- D2 desktop header: Stitch dark green band with the agent's contents, but
  without the "Gratuito / Free" badge. The language switch moves out of the
  map header to the bottom of the map page and the landing header.
- D3 desktop dates: Stitch strip under the map. The owner finds that dates
  read left to right show a sequence better than a vertical list, which can be
  read in either direction.
- D4 map controls: the Stitch background and overlay card. Zoom buttons are
  smaller and sit on the right side. The "map level" card is removed. The
  colour key must not be cut off.
- D5 map drawing: an OpenStreetMap background is required so people know
  where a place is. Squares show colour only, never numbers, and the map
  under them must stay readable. In the zoomed out forest view, areas without
  forest are transparent so the map shows through. The 11 by 8 km weather
  area outline from Stitch appears around the selected square.
- D6 details: Stitch look, which the owner finds easier to read and
  understand. The panel can be closed, as in the agent mockup. The
  experimental notice loses the "Avviso stima sperimentale" title and the
  warning triangle, because "Avviso" reads like a danger warning.
- D7 phone layout: the agent's layout in Stitch colours and type.
- D8 favorites: Stitch drawer on desktop, full sheet on phones.
- D9 states: the agent's messages and actions in Stitch colours.
- D10 language switch: see D2.
- D11 landing page: the Stitch landing page as it is, with its colours,
  fonts, sections and footer. Only text that claims something Micometeo does
  not have changes. The account icon is not shown now. Its top right place in
  the header is kept free if accounts come later.
- Second review on 12 October 2026: the owner rejected the first combined
  landing page because it dropped the Stitch sections, footer, closing band
  and colours. The owner also rejected numbers inside the map squares and the
  muddy look of warm squares over the green OpenStreetMap forests. Both map
  cards must fold, and the language switch must use the Stitch "IT / EN"
  style.
- D12 wording: Stitch's warm tone for landing headlines and empty states. The
  agent's plain labels inside the app.

## Handoff

### Tokens

Fonts from Google Fonts:

- Newsreader for place names, the large percentage and landing headlines.
- Plus Jakarta Sans for body text, labels and controls.
- JetBrains Mono for coordinates, dates in the strip and small numbers only.

Use `font-variant-numeric: tabular-nums` for every percentage, date and
measurement.

Colours from the Stitch `tailwind.config`:

| Name | Value | Use |
| --- | --- | --- |
| `pine-900` | `#11221B` | Header band, dark landing band, text on light squares |
| `pine-800` | `#1B352A` | Main buttons, selected date, percentage badge |
| `pine-600` | `#2E5645` | Hover, focus ring, selected square outline |
| `pine-100` | `#E5ECE8` | Selected chip background, wait messages |
| `parchment` | `#FCFAF6` | Page and panel background |
| `parchment-100` | `#F5F0E6` | Cards, secondary buttons |
| `parchment-200` | `#ECE3D2` | Borders and dividers |
| `parchment-900` | `#2B261D` | Main text |
| `earth-700` | `#5C432D` | Secondary text |
| `earth-100` | `#F3ECE4` | Experimental notice background |
| `earth-600` | `#7A5A3D` | Experimental notice border and info icon |
| error | `#BA1A1A` on `#FFDAD6` | Errors |
| older result | `#7A4B00` on `#FFF1D6` | Older stored update |

Estimate squares, from warm white to warm light brown:

| Range | Fill |
| --- | --- |
| 0 to 19% | `#FFF9F0` |
| 20 to 39% | `#F3E6D0` |
| 40 to 59% | `#EBD6B5` |
| 60 to 79% | `#DCBC91` |
| 80 to 100% | `#C99E6B` |

Square borders stay `rgba(17,34,27,0.25)`. Missing data uses a grey diagonal
hatch with a dashed border. Less than 10% forest uses a dotted grey outline
without fill. Both are named in the colour key with words.

The forest view uses `pine-500` `#3C6E59` with transparency that grows with
forest share. Land without forest is fully transparent.

Shape: 4 px radius for buttons, inputs and chips, 8 px for cards, panels and
sheets. Shadows only on what floats over the map, as in the Stitch level 2 and
level 3 shadows.

### Desktop layout, 900 px wide and up

- Header band in `pine-900`, 64 px: name with logo mark, the line "Stima
  sperimentale dei porcini nei boschi italiani", search field, "Use my location" and favorites with a
  count. No free badge and no language switch.
- Map fills the space under the header. The details panel, 440 px, opens on
  the right when a square is selected and the map shrinks to make room. It
  never covers the map.
- On the map:
  - Top right: the background and overlay card from Stitch. Two background
    buttons, an overlay switch, and the opacity slider with its value.
  - The background and overlay card and the colour key card each fold to
    their title row with a chevron button. Both start open.
  - Right side, under the card: zoom in and zoom out, 36 px.
  - Bottom centre: the date strip with eight days. Each day shows the short
    weekday, the date and, once a square is selected, the percentage. Today
    says "Oggi" or "Today". The selected day is `pine-800`. The assessment
    date sits at the right end of the strip title.
  - Bottom left: a compact colour key card, fully visible above the footer.
    One row holds the five estimate swatches labelled 0, 20, 40, 60 and 80+.
    Two rows below name missing data and less than 10% forest. A "Più voci"
    toggle shows the selected square, weather area and forest view entries.
  - When the map is under about 1000 px wide, the date strip takes the full
    width and the colour key sits above it. This happens on screens under
    1440 px with details open.
  - "Select square at map centre" for keyboard users, as in the agent mockup.
- Footer line under the map, 36 px: language switch on the left, map
  attribution on the right.

### Phone layout, under 900 px

Follow the agent mockup, with Stitch colours, type and controls:

- Header band in `pine-900`, 56 px: name and favorites.
- Search row with location button.
- Date chip row under the search. It scrolls sideways and keeps the selected
  day in view.
- Map below. "Layers" and "Legend" buttons float at the bottom right.
  Zoom buttons are 44 by 44 px on phones because they are touch targets.
- Details open as a sheet with three heights. It never covers the search or
  the dates. "Back to map" closes it.
- Footer line with the language switch at the bottom of the map. The sheet
  may cover it while it is open.
- The 320 by 568 phone keeps the agent rule that hides the design notice band
  while a sheet is open.

### Map

- OpenStreetMap background always, in the two styles from the brief.
- Zoomed out: forest share across Italy, transparent where there is no
  forest, and the hint "Zoom in until the map is about 50 km wide to see
  estimates" with the current width.
- Estimates switch on by map width, not zoom level, as in the agent mockup.
- The "Chiaro" background is the OpenStreetMap tiles muted to a light
  parchment tone with a CSS filter. "Alto contrasto" is the same tiles in
  grey with more contrast.
- Squares show colour only, with no numbers. They are drawn in their own
  layer with `mix-blend-mode: multiply`, so roads, paths and place names stay
  readable through them. They have no border at the 50 km view and at most a
  faint hairline when they are 16 px or wider.
- Selected square: 3 px `pine-600` outline with a 2 px white halo.
- When a square is selected, a dashed outline shows the 11 by 8 km weather
  area that contains it, with a small label "Area meteo di circa 11 per 8 km".

### Details panel and sheet

Order and labels follow the agent mockup. The look follows Stitch.

1. Place name in Newsreader, coordinate in JetBrains Mono with "Coordinata
   illustrativa del design" in the mockup. A close button at the top right.
2. "Salva preferito" as a secondary button and "Apri navigazione" as a main
   button, side by side.
3. Selected date with the percentage in the dark Stitch badge.
4. Experimental notice directly under the badge: `earth-100` background, a
   3 px `earth-600` left border, an info icon, no title. The text is the
   brief's notice, starting with the bold words "Stima sperimentale:".
5. "Perché questa stima": the contributing facts text.
6. "Meteo del giorno": four Stitch tiles for forest share with a bar,
   temperature with minimum and drying, frost, and hail.
7. "Pioggia passata, giorni completati": three rows for 7, 14 and 21 days,
   with a line saying these are past totals, not future rain.
8. "Area meteo e dimensione dell'area": the 11 by 8 km explanation.
9. "Fonti e aggiornamento": the three sources and the update time.

The badge, the facts and the states use the same square, date and update as
the map.

### States

Use the agent mockup's state messages, positions and actions for all nine
required states. Restyle them with the colours in the token table. The loading
state shows a thin `pine-600` progress bar along the top of the map.

### Favorites

- Desktop: a drawer from the right, as in Stitch. The browser storage note at
  the top. One card per favorite with its colour dot, name, coordinate and
  today's percentage, and "Riapri", "Rinomina e colore" and "Rimuovi". A
  "Salva l'area selezionata" button at the bottom.
- Phone: the same content in a full height sheet with "Back to map".
- Saving and renaming use the agent mockup's name and colour form.

### Language

- The Stitch landing switch: a globe icon followed by "IT / EN", with the
  current language bold. It sits in the landing header and in the footer
  line of the map page.
- Switching keeps the square, date, map view and open panels, as in the agent
  mockup.
- Italian labels may wrap. No label is cut off.

### Landing page

- The Stitch landing page `code.html` is the layout, with its own colours and
  DM Sans font. Keep every section: header, hero with the Abetone card and
  three figures, the four "why" cards, the regions section labelled as
  illustrative, the four method steps, the percentage scale, the ethics
  section with the four picker rules, the dark closing band and the four
  column footer.
- The ethics notice card is titled "Stima sperimentale", not "Avviso".
- No map in the landing page hero.
- No account icon. The header keeps its top right place free for accounts in
  #37.
- Text and facts from the agent landing page and the brief. The key figures
  are facts Micometeo has, such as 500 m squares, eight dates and all Italy.
  Remove "live", "20 regioni", updates every 6 hours, weather stations,
  "200.000 ettari" and every other claim the PRD does not support.
- Both notices from the brief appear as in the agent landing page.

### Parts to take from each mockup

| From Stitch | From the agent mockup |
| --- | --- |
| Fonts, colours, radius, shadows | Phone layout and sheet heights |
| Header band | Map behaviour, OpenStreetMap, width switch |
| Background and overlay card | Squares outside the scale |
| Date strip on desktop | Date chips on phones |
| Details panel look, badge and tiles | Details order, labels, close button |
| Favorites drawer | State messages and actions |
| Whole landing page, with true facts | Facts from the brief and the PRD |
| Weather area outline | Language behaviour and keyboard rules |

## Unresolved

- Mockup shortcuts that the app must not copy: sample squares exist only in
  about 20 by 18 km around Abetone, the weather area outline is one fixed
  block around Abetone instead of the area of the selected square, and
  weather and rain are the same for every square and date.
- The two Stitch pages use different sans serif faces: Plus Jakarta Sans in
  the map app and DM Sans on the landing page. Each combined page keeps its
  own Stitch face. #55 should pick one.
- Free access, F70: the map app header no longer says "free, no account"
  because the owner dropped the badge. The landing page says it. If the map
  app must say it too, the footer line is the place.
- Logo mark: neither mockup has one. Stitch uses an emoji in the app and a
  plain tree icon on the landing page. The combined mockup uses the tree
  icon. A real mark is not needed for #55.
- Competitors' date controls were not studied in detail. The feature
  comparison only notes a date slider in Fung.es and today, 3 and 7 day
  buttons in Mushroom Forecast. Weather map sites such as Windy use a
  timeline along the bottom of the map, like the chosen strip.
- The Italian copy of both mockups was written without a native review of
  every label. The owner should reread the combined mockup.
