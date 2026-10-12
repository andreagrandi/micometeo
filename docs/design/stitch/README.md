# Google Stitch mockup

This folder holds the Google Stitch result for #52. It is one of the two design
alternatives that #54 compares. Nobody has chosen it as the app design.

## Record

- Generated on 12 October 2026 by the owner in Google Stitch.
- Stitch project: https://stitch.withgoogle.com/projects/14625473845604887791.
  The project is private and opens only with the owner's Google account.
- Prompt: `docs/design/stitch_prompt.md` as committed in d248807, pasted
  unchanged.
- One follow-up request: the owner asked Stitch for a landing page in addition
  to the map app.
- No further prompt revisions were made.

## Files

| Folder | Content |
| --- | --- |
| `micometeo_design_alternative_a/` | Map app: `code.html` and the desktop screenshot `screen.png` |
| `micometeo_home_guida_esplorativa/` | Landing page: `code.html` and the full page screenshot `screen.png` |
| `micometeo_fieldwork/` | `DESIGN.md`: colours, type scale, spacing, corner radius and components |

## How to look at it

Open the two `screen.png` files for the desktop map and the landing page.

To see more screens, serve the folder and open the HTML files in a browser:

```sh
cd docs/design/stitch
python3 -m http.server 8765 --bind 127.0.0.1
```

Then open `http://127.0.0.1:8765/micometeo_design_alternative_a/code.html`.
The bar at the top switches the language and the screen size. The
"Audit & Required States" button shows the state messages. The pages load
Tailwind and Google Fonts from the internet.

The map app `screen.png` was reduced to 256 colours so it fits the 500 KB
limit of the repository's pre-commit check. The original export was 608 KB.
Trailing spaces and missing final newlines in the exported files were fixed
by the same check.

The HTML is a source of UI to copy. It is not app code and nothing in it is
used by the app.

## Design choices

- Colours: dark pine green for the header and main buttons, parchment for
  surfaces, and warm white to light brown for the estimate squares.
- Type: Newsreader, a serif, for place names and large percentages. A sans
  serif for body text and controls, and a monospaced face for coordinates and
  section labels.
- Desktop map app: a full width header with search, location and favorites.
  The sample notice runs under it. The map fills the left side, with zoom, map
  level and background controls floating on it. The eight dates sit in a strip
  along the bottom of the map. A fixed details panel sits on the right.
- Details panel: place and coordinate, save and navigation buttons, then the
  target date with a large percentage badge, the experimental notice, the
  contributing facts, weather and habitat tiles, rain history and sources.
- Phone map app: the details open as a sheet from the bottom with a close
  button. A "View estimate details" button sits over the map.
- Landing page: a hero with a sample estimate card for Abetone, a "why
  Micometeo" section, four method steps, a percentage scale, cards for four
  forest regions, a picking ethics section and a closing call to open the map.

## Feature checklist

The checklist comes from `docs/design/brief.md`. "Shown" means the UI for the
item is visible in the export. Most states are only reachable through the
"Audit & Required States" panel.

| Item | Result |
| --- | --- |
| F01 whole experimental percentage | Shown in the map squares and the details badge |
| F02 national forest view and no-estimate state | Shown as a map level and in the state panel |
| F04 today's estimate | Shown in the date strip |
| F05 next seven dates | Shown in the date strip, Italian and English short dates |
| F11 weather and habitat explanation | Shown in the details panel |
| F12 sources, update time, missing information | Shown in the details panel |
| F13 search, location and map selection with failures | Shown, failures in the state panel |
| F14 two backgrounds, visibility and opacity | Shown in the floating map panel |
| F18 target day weather and 7, 14, 21 day rain | Shown in the details panel |
| F23 favorites list, rename, recolor, reopen, remove | Shown in the favorites drawer |
| F39 external navigation | Shown as a details button |
| F70 free, no ads, no subscription | Shown in the header and landing page |
| F72 phone and desktop | Desktop shown. Phone shown only for the details sheet, see limitations |
| F75 Italian and English | Shown through the language switch |
| F76 no registration | Shown in the header and landing page |
| F81 coherent design for comparison | Yes, one visual style across both pages |

Required states in the state panel: first weather wait, missing data,
older update, request error with retry, no places found, location denied,
favorite not saved, and less than 10% forest. The loading state after a date,
map or layer change is missing.

## Limitations

- No phone map screen. At 390 by 844, the details sheet covers the map, so the
  export has no phone layout for the map, the date strip or the map controls.
  These need to be designed when the app UI is built.
- The map has no OpenStreetMap background. The squares sit on a plain green
  shape, so the export does not show how roads and place names read through
  the squares. Two map labels overlap and the colour key is cut off at the
  bottom left.
- The landing page copy is placeholder. It lacks the design and experimental
  notices, calls the sample "live", invents estimates for four regions and
  states method details that Micometeo does not have, such as wind checks and
  updates every 6 hours. Replace this text when the page is built.
- The project link is private. The files in this folder are the only record
  others can open.
