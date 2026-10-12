# Google Stitch design prompt

Create one coherent, polished design alternative for a free Micometeo website.
This prompt is complete on its own. Do not rely on another file or discussion.

## Product and audience

Micometeo helps people in Italy choose a forest area to explore for porcini. It
shows a whole-number estimate for the chance that porcini are growing in a
selected area on a selected day.

The visitor can browse without an account or location permission. The complete
journey must work in Italian and English on a phone and a desktop computer.
Choose a deliberate visual direction, type system, spacing, colors, map style
and panel placement. Do not produce a generic dashboard or default component
library screen. Leave the exact composition to your design decisions.

The owner will compare this Stitch alternative with a separate independent
alternative later. The independent alternative must not be a recolor of this
design. The owner will choose one design or a specified combination. Do not
claim that this design has been chosen.

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

## Shared illustrative sample

Use this exact sample in every screen and annotation. It is design content, not
a live forecast or a validated prediction.

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

Use these two separate notices in every screen that needs them:

> Design example: all values shown here are illustrative and are not from a
> live forecast.

> Experimental estimate: this percentage is unvalidated. It does not mean your
> personal chance of finding porcini.

The first notice labels the sample. The second notice labels growth estimates.
Do not apply the second notice to forest share or overlay opacity.

## Shared Italian and English copy

Use this exact copy in all screens and annotations. Keep `42%` as `42%` in
both languages.

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

## Screens and journey

Show every screen at 390 by 844 CSS pixels and 1440 by 900 CSS pixels. Check
a 320 by 568 phone too. Keep phone controls reachable when details are open.
Use desktop space for the map and details. The exact composition is yours.

Include these named screens:

- National forest view for Italy, Sicily and Sardinia, with no estimates while
  zoomed out.
- Estimate map at about 40 to 60 km wide or closer, with forest squares and a
  selected result.
- Search, optional location and manual map selection.
- Eight-date control with readable Italian and English dates.
- Selected-area details with estimate, weather, facts, sources and update time.
- Background and overlay controls.
- Favorite list, editing and removal.
- External navigation handoff.
- Language switch.

The map and details must show the same selected square, target date and update.
On a phone, show a clear return from details to the map.

Show this journey:

1. Open without registration and choose Italian or English.
2. Search for Abetone, use optional location or browse manually.
3. See forests across Italy, then zoom to the estimate view.
4. Read 42% for today, then select 15 October and read 48%.
5. Read weather, rain history, forest share, facts, sources and notices.
6. Change background, hide and show the overlay, and adjust opacity.
7. Save `Faggeta Abetone`, choose green, rename it `Abetone nord`, recolor it,
   reopen it and remove it.
8. Open external navigation for the selected representative point.
9. Switch language while keeping the same square and 15 October selected.

Explain that favorites remain in this browser, do not synchronize between
devices and can be lost when browser data is cleared. Reopening a favorite on
a later visit shows current estimates for its saved location.

## Required states

Show every state on phone and desktop. Use a working interaction when possible.
Otherwise show a clearly marked annotation with its trigger, message and
recovery action.

- Interaction loading after a date, map or layer change.
- First-fetch wait for the selected area.
- Required-input no estimate with a recovery action.
- Older stored update showing target 15 October 2026, assessment 11 October
  2026 and update 11 October 2026 at 10:30 CEST.
- Recoverable request error with retry and any older result clearly dated.
- No search results with changed search and manual browsing.
- Denied location with search and manual browsing still available.
- Unavailable browser storage with an honest unsaved favorite.
- Squares with less than 10% forest, shown without an estimate and with a text
  reason.

## Visual and accessibility requirements

Use real text and full dates. Let long Italian labels wrap. Use touch targets
of at least 44 by 44 CSS pixels. Make every control keyboard reachable with a
visible focus indicator. Return focus to the control that opened a panel.
Give the selected result a text alternative. Explain status with words and
text, not color alone. Keep the selected square and date through language and
layer changes.

## Feature checklist

Cover every item in a screen or clearly marked annotation:

- F01 appears in Estimate map and Selected-area details as a whole experimental percentage.
- F02 appears in National forest view and the required-input no-estimate state.
- F04 appears in Estimate map and Eight-date control for today.
- F05 appears in Eight-date control for the next seven dates.
- F11 appears in Selected-area details through weather and habitat explanations.
- F12 appears in Selected-area details through sources, update time, missing information, uncertainty and input detail.
- F13 appears in Search, location and map selection, including failure states.
- F14 appears in Background and overlay controls through two backgrounds, visibility and opacity.
- F18 appears in Selected-area details through target-day weather and 7, 14 and 21 completed-day rain totals.
- F23 appears in Favorite list, editing and removal through saving, names, colors, reopening and removal.
- F39 appears in External navigation handoff for the selected point.
- F70 appears throughout all named screens as free access without advertising or subscriptions.
- F72 appears in every named screen and required state on phone and desktop.
- F75 appears in Language switch and all named screens and required states in Italian and English.
- F76 appears throughout all named screens as a complete journey without registration.
- F81 appears across all named screens as a coherent design for comparison with the other alternative.

## Requested output

Generate exactly one coherent Google Stitch alternative. Provide inspectable
phone and desktop views, the narrow-phone check, both languages, all named
screens, all required states and the full feature checklist.

Include a short rationale for the visual direction, type, spacing, colors, map
style, panel placement and control grouping. Identify which states or controls
are working and which are annotations. Record the generation date, prompt,
output reference and any prompt iterations with the design handoff.

Do not add accounts, advertising, subscriptions, species selection, offline
downloads, route planning, parking, GPS recording, return guidance, separate
terrain, forest or soil explorers, weather-station browsing, journals, community tools,
alerts, sharing or automatic model learning. Habitat facts may remain inside
the selected-area explanation.

Do not require a paid tool, purchase, server, deployment or sign-in. Static
artwork cannot prove working interaction or runtime performance. The owner
will compare this alternative with an independent composition before choosing a
direction.
