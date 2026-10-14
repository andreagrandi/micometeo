# Local acceptance

This report collects the local checks before the owner's acceptance in #63.
#62 adds the browser, phone and nightly update sections.

## Tuscany launch

Issue #61 checked the Tuscany launch on 14 October 2026. Decision D22 in
`docs/decisions.md` limits the first version to Tuscany, region 09. Other
regions come later. These are software and data checks. They do not check
whether the estimated chances match real finds. No field visit, purchase,
server or deployment was needed.

### Figures reused from #96

Coverage, provider calls, calculation time, stored size and serving times are
in [tuscany_acceptance.md](tuscany_acceptance.md). This ticket did not
measure them again. In short, Tuscany has 71,031 forest squares in 333
weather cells. The first load used 1,092 counted calls, and a normal night is
planned at 666.

### Launch coverage in the product

- The landing page says in Italian and English that estimates cover Tuscany
  and that other regions are coming soon. It no longer mentions all Italy,
  Sicily or Sardinia. The four example cards now name Tuscan areas: the
  Abetone Apennines, Garfagnana, the Casentino forests and Mount Amiata.
- The header tagline says "Tuscan forests".
- A view outside Tuscany, a forest square outside the published run and a
  place outside Tuscany now say that estimates cover Tuscany for now and that
  other regions are coming soon.
- The area details without an update now return `outside_prepared_area` for
  a forest square that has no estimate in the published run. They returned
  `estimate_not_available` before.

On the local database `micometeo`, a squares request near Rieti in Lazio
returned `outside_coverage`. A request near Florence returned 20 squares that
were either available or without forest. The landing page in both languages
held the Tuscany wording and none of the removed phrases.

### Checks in `tests/app/test_local_pipeline.py`

The module runs the whole chain once, against a fake Open-Meteo service and
the local PostGIS test database: weather for the night, the estimate run,
publication and the map cache.

| Test | What it shows |
|---|---|
| `test_a_night_stores_weather_publishes_eight_dates_and_warms_the_map` | One night stores the weather, publishes eight dates and fills the map cache. |
| `test_map_overview_and_details_agree_on_square_date_value_update_and_credits` | The map, overview and details agree on square, date, percentage and update on four of the eight dates, and carry the source dates and credits. |
| `test_a_failed_next_night_keeps_the_run_of_the_night_before` | A slow, refused or interrupted fetch, missing hours, a reached daily limit or a failed calculation on the next night leaves the earlier run published. With the clock one day later, the map and details offer only the seven remaining dates. The values stay the same and keep their real assessment date. The day before and an eighth day are refused. |
| `test_squares_outside_the_prepared_area_give_a_reason_and_no_percentage` | A forest square outside the run, a square without forest, a view in Paris and a point in Paris each give their reason and no percentage. No weather request starts. |

The single-step failure tests already in `test_scheduled_weather.py`,
`test_weather_requests.py`, `test_forecast_runs.py` and
`test_published_forecast_api.py` stay as they are.

### Commands

```sh
docker compose up --wait database
uv run python apps/application/manage.py compilemessages --ignore .venv --locale it --locale en
uv run pytest tests/app
uv run pytest tests/e2e/test_place_search.py tests/e2e/test_published_forecast_map.py tests/e2e/test_area_details.py
```

On 14 October 2026 all 527 app tests and the 180 selected browser tests
passed.

### Not checked here

- The nightly chain on two consecutive real nights belongs to #62. See
  "Nightly updates" below.
- The slow fetch test raises a timeout at once. It does not wait for a real
  slow answer.
- Coverage of other regions, including the Alps, Sicily and Sardinia, waits
  for the later all-Italy version.

## Browser and phone

Issue #62 checked the complete visitor journey on 14 October 2026. The
published run had the assessment date 13 October 2026. No night ran on 14
October, so the map offered seven dates, 14 to 20 October, and labelled
every result as an older result from 13 October. The eighth date of a fresh
run, 21 October, could not be seen.

### Environments

| Kind of evidence | Environment |
|---|---|
| Live data, manual | Chromium from Playwright, desktop window 1280 by 800 and phone-sized window 390 by 844, against `runserver` on port 8010 and the local database `micometeo`. |
| Live data, automated | `tests/e2e/test_mvp_journey.py` in Chromium and WebKit from Playwright. The phone runs use a 390 by 844 window with touch and mobile mode. This is browser emulation, not a phone. |
| Controlled fixtures, once | Checks that held, failed or changed single API answers with `page.route`. They ran once and are not kept. |
| Real phone | Not performed. See "Not checked". |

The Chrome extension tab was also used, but Chrome treats that tab as hidden.
The map only draws when a screenshot is taken, so a first load there looked
like it took 18 seconds. In a visible Playwright window the squares answer
arrived 0.34 seconds after the page opened. The extension tab was not used
for timing.

Place search uses Photon at photon.komoot.io. During the manual check one
Photon request took 31 seconds from this machine, and the page showed "Place
search took too long. Try again." twice. The automated journey replaces
Photon with a fixed answer for Abetone. Everything else in the journey reads
the local database.

### Journey on live data

The automated journey runs once for each language and each window size. It
opens the map zoomed out, searches Abetone, selects the square on the map,
compares today and the last date, switches language, reads the three rain
periods and the sources, changes background and opacity, saves and renames a
favorite, reloads, reopens it and checks the navigation link. Every
percentage, assessment date and update is compared with `/api/v1/squares` and
`/api/v1/areas/` for the same square and date. The test fails on any console
error.

The manual desktop run in Italian on square `500m_E4372500_N2337000` near
Abetone gave these values:

| Step | Observed |
|---|---|
| Today, 14 October | 38%. Target date 14 ottobre 2026, assessment date 13 ottobre 2026, last update 14 ott 2026 09:50. The API gave 38. |
| Day seven, 20 October | 25%. The API gave 25. The date strip showed 38, 36, 36, 35, 31, 28 and 25%. |
| Facts | Rain in the 30-day period 61,0 mm, retained water 28,8 mm, corrected mean temperature 8,6 °C, forest share 97,9 %. |
| Rain periods | 7 days 39,5 mm from 6 to 12 October, 14 days 41,8 mm, 21 days 41,8 mm. Each period ends on 12 October, the last completed day before the assessment date. |
| Sources | Region boundaries, Copernicus forest map 2018, Copernicus elevation model and Open-Meteo, each with version, retrieval time, credit and licence. |
| Background and opacity | High contrast and 35% were applied and kept in the address. |
| Favorite | Saved as "Abetone prova", renamed to "Abetone bosco" with a colour. After a fresh page load it reopened the square with today's 38%. |
| Navigation | A map press opened Google Maps at the pressed point. A reopened favorite opened it at the square's representative point. |
| Language switch | With day 16 October and details open, the switch to English kept square, date and details. The page then showed 36%, 59.9 mm and "Fri 16 Oct". |

### Feature matrix

IT and EN mean the check ran in both languages. Desktop and phone mean the
1280 by 800 and 390 by 844 windows. No row has real-phone evidence.

| Feature | Evidence | IT and EN | Desktop and phone |
|---|---|---|---|
| F01 | Percentage per square and date, equal to the API, in the journey test and the manual run. | Yes | Yes |
| F02 | Tuscany estimates. A view near Milan shows the stated reason and no squares, in `test_real_data_view_outside_tuscany_explains_the_gap`. | Yes | Desktop only |
| F04 | Today, 14 October, selected by default. | Yes | Yes |
| F05 | Six following dates, to 20 October. The eighth date needs a run for 14 October, which did not exist. | Yes | Yes |
| F11 | Four key facts with the decimal mark of the language, and more facts on request. | Yes | Yes |
| F12 | Sources with versions, retrieval times, credits and licences. The older result note names 13 October. | Yes | Yes |
| F13 | Place search with a fixed Photon answer, map selection, and a refused location in the one-off failure checks. A location that the browser grants was not checked on live data. | Yes | Yes |
| F14 | Light and high contrast backgrounds, overlay switch and opacity. | Yes | Yes |
| F18 | Weather for the selected day and rain over 7, 14 and 21 completed days. | Yes | Yes |
| F23 | Save, rename, colour, reload and reopen in the same browser. | Yes | Yes |
| F39 | Google Maps link with the selected coordinates. The test opens it in a stand-in page and does not load Google. | Yes | Yes |
| F70 | No payment, advertising or subscription screen anywhere in the journey. | Yes | Yes |
| F72 | No sideways scroll at 390 by 844. Details open as a bottom sheet on the phone. | Yes | Yes |
| F75 | Labels, dates, weekdays, decimals and errors follow the language. Source names are now translated. Licence texts and dataset versions from the data providers stay in their original English. | Yes | Yes |
| F76 | The whole journey runs as an anonymous visitor with no account. | Yes | Yes |
| F81 | Layout follows `docs/design/decision.md`. The details heading shows a plain label instead of a place name, see the findings. | Yes | Yes |

### Failure states, checked once

These checks changed single API answers on purpose. They ran once in Italian
and English, in Chromium and WebKit, and all passed. They are not kept in the
repository. The owner tests failure states by hand.

| Check | What it showed |
|---|---|
| Slow, then failed squares request | The loading text, then the error with a retry button, no squares and no details. Retry drew the squares. |
| Late details answer after a date change | The page kept the newer date's percentage and date. |
| Square with no estimate, square without forest | Each showed its reason, no percentage and no experimental notice. |
| Older estimates | "Older result from" with the real date in the details and the date panel. A refused weather fetch shows the same way, because pages never fetch weather since #100. |
| Refused location | The localized reason. Nothing selected and search still usable. |
| No search results | The message, and the map stayed where it was. |
| Blocked browser storage | The favorites dialog said favorites cannot be stored and never showed "saved" or a count. |

Existing modules such as `test_area_details.py`, `test_place_search.py` and
`test_favorites.py` keep their own checks of these states.

### Repeated use, checked once

A test that is no longer in the repository dragged the map on the phone
window and, between drags, zoomed, changed date, background and opacity, and
opened and closed the details. After every action it checked that the page
answered within 2 seconds and that the map, the selected date and the details
agreed. Each drag started at Abetone and held still for 250 ms before release,
because a fast drag otherwise let the map glide up to 11 km, out of Tuscany.

Five-minute runs on emulated phones, 14 October 2026:

| Browser | Actions | Drag mean and slowest | First third mean | Last third mean | Slowest page answer |
|---|---|---|---|---|---|
| WebKit | 332 | 0.68 s, 0.78 s | 0.47 s | 0.47 s | 0.014 s |
| WebKit | 352 | 0.68 s, 0.77 s | 0.48 s | 0.47 s | 0.010 s |
| Chromium | 372 | 0.83 s, 1.25 s | 0.62 s | 0.57 s | 0.112 s |

No run slowed down over time, lost the squares layer or showed a details
date different from the selected date. The map kept one map instance and
eight listeners throughout. This is emulation on a desktop processor. It
does not reproduce the iPhone 15 freeze from P5 and does not replace the
real phone check.

After a page load, the loading message clears about 0.25 s before the
squares are drawn. A click in that gap selects nothing. This is too short to
matter for a person and was left as it is.

### Keyboard and readability

Tab reaches the date buttons, the layer controls, zoom, the map, the credits,
the language buttons, search, location and favorites, and each shows a focus
ring. The map canvas does not select an area with Enter. A keyboard visitor
can choose an area through search, location or a favorite. The owner removed
the centre selection button from the map in #105. The colour key names
missing data and less than 10% forest with words, and the details show the
percentage as a number, so no information depends on colour alone.

### Findings

| Finding | Status |
|---|---|
| The live date panel showed today, 14 October, as the assessment date until the estimates arrived, then 13 October. The server filled in today's date. | Fixed. The live page now shows the loading text until the run's date is known. Fixture pages keep their sample date. |
| The details heading showed the square code, such as `500m_E4372500_N2337000`. The design asks for a place name. | Fixed with a plain label, "Area selezionata" or "Selected square", as the owner chose. The code stays in `data-square-id`. Municipality names could come from the ISTAT municipality boundaries already in `data/raw/mvp_boundaries/`, without a remote request. |
| On the Italian page the region boundary and elevation sources used the providers' English dataset names. | Fixed. The cards use the translated names, such as "Confini regionali ISTAT". The dataset name stays on the version line. |
| On the phone, the Layers and Legend buttons covered part of the map credits. | Fixed. The credits sit 60 px higher on screens narrower than 900 px. |
| Photon took 31 seconds for one search. | Not a defect in the app. The page showed the timeout message and stayed usable. |
| The map canvas does not select an area with Enter. | Kept. The owner removed the centre selection button in #105. |

### Not checked

- Real iPhone with Safari. No phone was available during this check, so AC3
  stays open. The owner said on 14 October 2026 that the first release
  targets desktop and that phone use will not block it. WebKit emulation in
  Playwright is supporting evidence only.
- Location permission granted on a real phone through the Tailscale address.
- The eighth date of a fresh run, because no night ran on 14 October.

### Commands

```sh
docker compose up --wait database
uv run pytest tests/e2e/test_mvp_journey.py
```

The journey module took 98 seconds on 14 October 2026, or 44 seconds with
`-n 4`. It skips itself when the database
holds no published run, as in the empty database of the nightly WebKit check
in CI.

## Nightly updates

Not checked. The owner decided on 14 October 2026 not to schedule or run real
nights on the local machine. The two consecutive real nights of AC7, and any
command that runs the whole night in one go, wait until the application is
deployed, if it is deployed. No night ran for this report, so no times,
counted calls, HTTP attempts, refusals or database sizes are recorded. The
planned cost of a normal night stays 666 counted calls in 8 HTTP requests,
from `refresh_tuscany_weather --dry-run` on 14 October.
