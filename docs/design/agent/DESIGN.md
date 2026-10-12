# Daylight field map: design rules

These are the visual and layout rules of the agent mockup for #53. The map
app and the landing page share them. They are written so the app UI can copy
them if the owner chooses this direction in #54.

## Direction

The page should read like a clear printed walking map in daylight. Surfaces
are near white, text is dark ink, and the only strong colour is a deep lake
blue for actions and the selected square. The estimate squares keep the warm
white to light brown scale from the brief, so blue never competes with them.

This differs from the Stitch result on purpose. Stitch uses dark pine green,
parchment and a serif face, with a fixed details panel on the right and the
dates in a strip under the map. This design uses one legible sans serif face,
puts the dates first, and gives the phone its own layout.

## Colours

Define every colour once as a CSS custom property in `tokens.css`.

| Token | Value | Use |
| --- | --- | --- |
| `--paper` | `#FBFAF7` | Page and panel background |
| `--paper-raised` | `#FFFFFF` | Cards, inputs, sheet |
| `--paper-sunk` | `#F1F0EB` | Section bands, pressed controls |
| `--ink` | `#1C2326` | Main text |
| `--ink-muted` | `#55605F` | Secondary text, at least 4.5 to 1 on paper |
| `--line` | `#D8DAD3` | Borders and dividers |
| `--lake` | `#1F4E79` | Main buttons, links, focus ring, selected square outline |
| `--lake-soft` | `#E4EDF5` | Selected date row, selected chip |
| `--note-bg` | `#FFF6DC` | Experimental notice background |
| `--note-ink` | `#6B4A00` | Experimental notice text and border |
| `--sample-bg` | `#EEF0F3` | Design example notice background |
| `--sample-ink` | `#3A4350` | Design example notice text, dashed border |
| `--error-bg` | `#FCEBE8` | Error messages |
| `--error-ink` | `#9A2A1F` | Error text and border |
| `--wait-ink` | `#1F4E79` | Loading and first weather wait, same as lake |

Estimate scale, five steps with text labels in the legend:

| Range | Fill | Legend label EN | Legend label IT |
| --- | --- | --- | --- |
| 0 to 19% | `#FFF8EC` | 0 to 19% | da 0 a 19% |
| 20 to 39% | `#F6E3C3` | 20 to 39% | da 20 a 39% |
| 40 to 59% | `#E9C99A` | 40 to 59% | da 40 a 59% |
| 60 to 79% | `#D9AE76` | 60 to 79% | da 60 a 79% |
| 80 to 100% | `#C8955A` | 80 to 100% | da 80 a 100% |

Squares have a 1 px border in `rgba(28,35,38,0.25)` so neighbours with the
same fill stay distinct. The overlay opacity applies to the fill only.

Squares outside the scale:

- Missing required data: no fill colour from the scale. Grey diagonal hatch
  with a dashed grey border. Legend label: "No estimate, data missing" and
  "Nessuna stima, dati mancanti".
- Less than 10% forest: no fill, dotted grey border, drawn only when the map
  is about 15 km wide or closer. Legend label: "Less than 10% forest" and
  "Meno del 10% di foresta".
- Selected square: 3 px lake blue outline with a 2 px white halo outside it.

National forest view: forest share in green `#3F7D4E` with transparency that
grows with forest share, over the light background. This green appears only
in the zoomed out view and in its legend.

## Type

- One family: Atkinson Hyperlegible Next from Google Fonts, falling back to
  `system-ui, sans-serif`. It was drawn for readers with low vision, which
  also helps in bright light outdoors.
- Numbers use `font-variant-numeric: tabular-nums` so percentages and dates
  line up.
- Scale in CSS pixels: 13 caption, 15 body, 17 control labels and lead text,
  20 section headings, 26 page headings, 44 for the large percentage, 56 for
  the landing page title on desktop and 36 on phones.
- Weights: 400 body, 600 labels and headings, 700 for percentages.
- Line height 1.45 for body text, 1.2 for headings.

## Spacing, shape and controls

- Spacing steps of 4, 8, 12, 16, 24, 32 and 48 px.
- Corner radius 12 px for cards, panels and the sheet, 8 px for inputs and
  buttons, fully round for chips.
- Every control is at least 44 by 44 px.
- Focus: 3 px lake blue outline with 2 px offset on every focusable element.
- Shadows only on things that float over the map: the sheet, the layer
  panel and the map buttons. Use one shadow,
  `0 2px 8px rgba(28,35,38,0.18)`.
- Main button: lake fill, white text. Secondary button: white fill, lake text,
  lake border. Quiet button: no border, ink text, sunk background on hover.

## Notices

- Design example notice: dashed `--sample-ink` border, `--sample-bg`, a
  leading label "Design example" in caps at 13 px. It sits once at the top of
  every page and inside the details next to the sample values.
- Experimental notice: solid left border 4 px in `--note-ink`, `--note-bg`,
  directly under every estimate percentage. Never next to forest share or
  opacity.

## Map app layout

### Desktop, 1440 by 900

- Top bar, 64 px: name and short line "Free, no account", search field with
  location button, favorites button, language switch.
- Design example notice in a 36 px band under the top bar.
- Left date column, 320 px wide: heading "Select date", then the eight dates
  as a vertical list. Each row shows the full weekday and date, such as
  "Thursday 15 October", and the percentage for the selected square with a
  small bar. Today's row is labelled "Today". Before a square is selected the
  rows show the dates only, with the hint "Select a forest square to compare
  dates". Below the list sit the legend and the layer controls: two
  backgrounds, hide or show overlay, opacity slider with its value.
- Map in the middle, filling the rest.
- Details column on the right, 400 px, opens when a square is selected and
  closes with a "Close details" button. The map shrinks, it is never covered.
- The dates and the layers stay in the left column, so they are always
  reachable while details are open.

### Phone, 390 by 844 and 320 by 568

- Top bar, 56 px: name, favorites button, language switch.
- Search row: search field and a 44 px location button.
- Date row: eight chips in a row that scrolls sideways, with the selected chip
  scrolled into view. Each chip shows two lines, "Thu" and "15 Oct", and the
  percentage under them once a square is selected. Today's chip says "Today".
- Map below, filling the rest.
- Layers button and the legend button float at the bottom right of the map.
- Details open as a sheet from the bottom with three heights:
  - Short: place, date and the percentage with the experimental notice,
    plus "More details" and "Back to map".
  - Half: about half the screen, scrolls inside.
  - Tall: up to the bottom of the date row, never higher.
- The top bar, search and date row are never covered by the sheet, so the
  date can change while details are open.
- "Back to map" closes the sheet and returns focus to the map.

## Landing page layout

- Same top bar style with language switch and an "Open the map" button.
- Hero: the title, one short paragraph, the main button, and a live Leaflet
  preview of the Abetone sample squares with the selected square marked.
- Sections, each in plain words: what the percentage means and what it does
  not, how the estimate is made, what you can do on the map, what it costs,
  sources, and a reminder that picking rules depend on the region.
- Desktop uses two columns where text sits next to an example. Phones use one
  column.
- The design example notice sits at the top and the experimental notice next
  to every sample percentage.

## Data format of the sample layers

`assets/sample_squares.js` sets one global value:

```js
window.MICOMETEO_SAMPLE = {
  dates: ["2026-10-12", ..., "2026-10-19"],
  selected_square_id: "abetone-sample",
  national_forest: {
    url: "assets/italy_forest.png",
    bounds: [[south, west], [north, east]],
  },
  squares: [
    {
      id: "r12c34",
      bounds: [[south, west], [north, east]],
      forest_share: 68,
      estimates: [42, 45, 47, 48, 46, 43, 40, 38],
      no_estimate_reason: null,
    },
  ],
};
```

`forest_share` is a whole number from 0 to 100. `estimates` has one whole
number per date, or is `null`. `no_estimate_reason` is `null`,
`"missing_data"` or `"less_forest"`. Every value is illustrative.
