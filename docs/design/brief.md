# SporaMeteo shared design brief

## Purpose and audience

SporaMeteo is a free website for people in Italy who want to choose a forest
area to explore for porcini. It shows a whole-number estimate for the chance
that porcini are growing in a selected area on a selected day.

The visitor can browse without an account or location permission. The journey
must work in Italian and English on a phone and a desktop computer. The design
must feel finished, calm and easy to read outdoors.

This brief gives two designers the same product, sample and comparison rules.
It does not choose the final visual direction.

## Fixed scope

- Cover all Italy, including Sicily and Sardinia.
- Show today and the next seven days, for eight dates in total.
- Start with a forest-only map when zoomed out.
- Show estimates after the map is about 40 to 60 km wide or closer.
- Show selected forest squares of 500 m with at least 10% forest.
- Explain that weather is grouped in areas about 11 by 8 km while the displayed
  square is 500 m. This difference does not prove accuracy.
- Show the selected estimate, weather, habitat facts, sources and update time.
- Offer two readable OpenStreetMap backgrounds, visibility and opacity controls.
- Draw the estimate squares over the OpenStreetMap background, never on an
  empty map. Colour them from warm white for low percentages to warm light
  brown for high ones, and keep roads and place names readable through them.
  Squares without forest or without an estimate use a look outside that scale.
- Save private browser favorites with a name and optional color. Allow rename,
  recolor, reopen and remove.
- Open the selected representative point in an external navigation app.
- Keep every capability free, without advertising, subscriptions or sign-in.

The estimate concerns porcini growing somewhere in the selected area on the
selected day. It is experimental and unvalidated. It is not a visitor's
personal chance of finding porcini and does not promise a mushroom at a point.

When weather is first requested for an area, show a short first-fetch wait. If
an older result is shown, keep its original target date and update time. Missing
required data means no estimate. It must never become 0% by default.

## Exclusions

Keep accounts, advertising, subscriptions, species selection, offline
downloads, route planning, parking, GPS recording, return guidance, separate
terrain, forest or soil explorers, weather-station browsing, journals, community tools,
alerts, sharing and automatic model learning out of both designs.

Habitat facts may appear inside the selected-area explanation.

## Shared illustrative sample

Both designs must use this exact sample. It is design content, not a live
forecast or a validated prediction.

- Place: `Abetone, Tuscany`
- Selected area: one 500 m square
- Representative point: `44.1318 degrees N, 10.6625 degrees E`
- Point label: `Illustrative design coordinate`
- Forest share: `68%`
- Weather grouping: one area of about 11 by 8 km
- Backgrounds: `Light / Chiaro` and `High contrast / Alto contrasto`
- Estimate overlay: visible at `60%` opacity, with hide, show and opacity controls
- Assessment date: `12 October 2026`
- Eight dates: `12, 13, 14, 15, 16, 17, 18 and 19 October 2026`
- Today, 12 October: `42%`
- Selected future date, 15 October: `48%`
- Illustrative update: `12 October 2026 at 10:30 CEST`
- Modelled weather for the selected area: `13°C`, minimum `8°C`, low drying,
  no frost indicated by the model, hail information unavailable
- Completed rain history assessed on 12 October:
  - 7 days, 5 to 11 October: `18 mm`
  - 14 days, 28 September to 11 October: `37 mm`
  - 21 days, 21 September to 11 October: `54 mm`

The rain history stays 18, 37 and 54 mm when 15 October is selected. It is
history through 11 October, not future rain.

Name these sources: `Copernicus forest map`, `Open-Meteo modelled weather` and
`OpenStreetMap map data`. Source dates are unavailable in this design sample.
Do not invent source history or claim that sample values are live.

Use two separate notices in every artifact:

> Design example: all values shown here are illustrative and are not from a
> live forecast.

> Experimental estimate: this percentage is unvalidated. It does not mean your
> personal chance of finding porcini.

The first notice labels the sample. The second notice labels growth estimates.
Do not apply the second notice to forest share or overlay opacity.

## Shared Italian and English copy

Use this copy in both designs. Keep `42%` as `42%` in both languages.

| Purpose | English | Italian |
| --- | --- | --- |
| Language switch | `Italiano / English` | `Italiano / English` |
| Search | `Search for a place` | `Cerca un luogo` |
| Location | `Use my location` | `Usa la mia posizione` |
| Date | `Select date` | `Seleziona data` |
| Hide overlay | `Hide overlay` | `Nascondi sovrapposizione` |
| Show overlay | `Show overlay` | `Mostra sovrapposizione` |
| Opacity | `Overlay opacity` | `Opacità della sovrapposizione` |
| Favorite | `Save favorite` | `Salva preferito` |
| Navigation | `Open navigation` | `Apri navigazione` |
| Retry | `Try again` | `Riprova` |
| First fetch | `Waiting for weather for this area.` | `In attesa del meteo per questa area.` |
| No estimate | `No estimate because required data is missing.` | `Nessuna stima perché mancano dati obbligatori.` |
| No results | `No places found` | `Nessun luogo trovato` |
| Location denied | `Location access was not granted` | `Accesso alla posizione non concesso` |
| Unsaved favorite | `Favorite not saved in this browser` | `Preferito non salvato in questo browser` |
| Less forest | `This square has less than 10% forest. No estimate is available.` | `Questa area ha meno del 10% di foresta. Nessuna stima disponibile.` |
| Optional weather | `Hail information unavailable.` | `Informazioni sulla grandine non disponibili.` |
| Design notice | `Design example: all values shown here are illustrative and are not from a live forecast.` | `Esempio di design: tutti i valori mostrati sono illustrativi e non provengono da una previsione in tempo reale.` |
| Experimental notice | `Experimental estimate: this percentage is unvalidated. It does not mean your personal chance of finding porcini.` | `Stima sperimentale: questa percentuale non è stata validata. Non indica la tua probabilità personale di trovare porcini.` |
| Contributing facts | `This illustrative estimate uses 18 mm of rain in the last 7 completed days, 68% forest cover and modelled temperature of 13°C. These facts explain the example, not a validated accuracy result.` | `Questa stima illustrativa usa 18 mm di pioggia negli ultimi 7 giorni completati, il 68% di copertura forestale e una temperatura modellata di 13°C. Questi dati spiegano l'esempio, non indicano un'accuratezza validata.` |

## Journey

1. Open the site without registration and choose Italian or English.
2. Search for Abetone, use optional location or browse the map manually.
3. See forests across Italy. Zoom until the estimate view is available.
4. Read 42% for today, then select 15 October and read 48%.
5. Open details for weather, rain history, forest share, facts, sources and
   the experimental notice.
6. Change background, hide and show the overlay, and adjust its opacity.
7. Save `Faggeta Abetone`, choose green, rename it `Abetone nord`, recolor it,
   reopen it and remove it.
8. Open external navigation for the selected representative point.
9. Switch language while keeping the same square and 15 October selected.

Explain that favorites remain in this browser, do not synchronize between
devices and can be lost when browser data is cleared. Reopening a favorite on
a later visit shows current estimates for its saved location.

## Screens and states

Show every item below at 390 by 844 CSS pixels and 1440 by 900 CSS pixels.
Check a 320 by 568 phone too. The phone must keep controls reachable when
details are open. The desktop must use its space for the map and details.

Named screens:

- National forest view, with Italy, Sicily and Sardinia and no estimates while
  zoomed out.
- Estimate map, with the 40 to 60 km view, forest squares and selected result.
- Search, location and map selection.
- Eight-date control with readable Italian and English dates.
- Selected-area details with estimate, weather, facts and sources.
- Background and overlay controls.
- Favorite list, editing and removal.
- External navigation handoff.
- Language switch.

The map and details must show the same selected square, target date and update.
On a phone, show a clear return from details to the map.

Required states:

- interaction loading after a date, map or layer change
- first-fetch wait for the selected area
- required-input no estimate with a recovery action
- older stored update showing target 15 October 2026, assessment 11 October
  2026 and update 11 October 2026 at 10:30 CEST
- recoverable request error with retry and any older result clearly dated
- no search results with changed search and manual browsing
- denied location with search and manual browsing still available
- unavailable browser storage with an honest unsaved favorite
- squares with less than 10% forest, shown without an estimate and with a text reason

Show the visible message and next action for each state on both devices.

## Visual and accessibility guidance

Ask for a deliberate visual direction, typography, spacing, colors, map style
and panel placement. Leave the final composition to each alternative.

Use real text and full dates. Let long Italian labels wrap. Use touch targets
of at least 44 by 44 CSS pixels. Make every control keyboard reachable with a
visible focus indicator. Return focus to the control that opened a panel.
Give the selected result a text alternative. Explain status with words and
text, not color alone. Keep the selected square and date through language and
layer changes. Static artwork cannot prove runtime behavior or performance.

## Feature checklist

Mark each item as a working interaction or a static annotation in each artifact.

- [ ] F01 appears in Estimate map and Selected-area details as a whole experimental percentage.
- [ ] F02 appears in National forest view and the required-input no-estimate state.
- [ ] F04 appears in Estimate map and Eight-date control for today.
- [ ] F05 appears in Eight-date control for the next seven dates.
- [ ] F11 appears in Selected-area details through weather and habitat explanations.
- [ ] F12 appears in Selected-area details through sources, update time, missing information, uncertainty and input detail.
- [ ] F13 appears in Search, location and map selection, including failure states.
- [ ] F14 appears in Background and overlay controls through two backgrounds, visibility and opacity.
- [ ] F18 appears in Selected-area details through target-day weather and 7, 14 and 21 completed-day rain totals.
- [ ] F23 appears in Favorite list, editing and removal through saving, names, colors, reopening and removal.
- [ ] F39 appears in External navigation handoff for the selected point.
- [ ] F70 appears throughout all named screens as free access without advertising or subscriptions.
- [ ] F72 appears in every named screen and required state on phone and desktop.
- [ ] F75 appears in Language switch and all named screens and required states in Italian and English.
- [ ] F76 appears throughout all named screens as a complete journey without registration.
- [ ] F81 appears across all named screens as a coherent design for comparison with the other alternative.

## Artifact requirements and owner choice

Exactly two alternatives are required overall.

- #52 must be an actual Google Stitch result. Record the generation date,
  prompt, output reference and any prompt iterations in
  `docs/design/stitch/README.md`. Show inspectable phone and desktop views.
- #53 must be an independently composed design, not a recolor of Stitch. Keep
  its source and local viewing instructions in `docs/design/agent/README.md`.
- Both alternatives use this sample, this copy, both languages, the same
  screens, states and checklist. Later screenshots belong under `/tmp/`.
- Static artwork must be labelled as static and cannot prove working
  interaction or performance.

For #54, compare the same journey at both sizes. Record readability, control
access, state recovery, language behavior, sample notices and which parts are
working or annotated. The owner chooses Stitch, the independent design or a
specified combination. A pending choice means no direction is selected.

## Source references

Product scope is in `docs/product_prd.md`. Decisions D15 through D20 are in
`docs/decisions.md`. Feature examples are in
`reports/Porcini app feature comparison.md`. Phone findings are in
`reports/p5_phone_map.md`. Downstream specifications are in
`docs/issues/mvp/52.md`, `docs/issues/mvp/53.md` and `docs/issues/mvp/54.md`.
