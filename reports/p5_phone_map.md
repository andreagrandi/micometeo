# P5 phone map prototype with a small API

Issue #10.

## Question

Can someone comfortably explore ready-made scores on a phone?

## Answer

Yes. Serving ready-made scores to a phone is fast and cheap. The prototype
page has one known bug on the iPhone.

On an iPhone 15 with Safari the page opened quickly, text was readable and
squares were easy to tap. Moving the map got slower with each move and then
froze. The API answered all 9 square requests of that session with 200, and
the views were small, so the freeze is a bug in this prototype page, not a
limit of serving the data. Its cause was not looked for, because the page is
a throwaway prototype.

In a phone-sized Chromium window the page is usable 0.9 to 3.5 seconds after
it opens, and 2.5 to 3.8 seconds with a slowed connection and a 4 times slower
processor. A full phone screen of squares at the starting zoom is 7.4 KB
compressed. The widest view the page allows holds 1,086 squares and is 27 KB
compressed. The API uses about 40 MB of memory and answers in 1 to 11 ms on
this laptop.

All scores are made up. Every API answer and the page say so.

## What was built

- `apps/api/` is the API. It runs as its own program with Python 3.12 and
  only the standard library. The addresses are documented in
  `apps/api/README.md`:
  - `GET /api/v1/health` checks that the API answers.
  - `GET /api/v1/info` lists species, the 14 days that can be chosen, the map
    area, the most squares per request and the lowest zoom.
  - `GET /api/v1/squares` takes a species, `assessment_date`, `target_date`
    and a map area, and returns grid squares as GeoJSON.
- Each square has `cell_id`, `species`, `assessment_date`, `target_date`,
  `days_ahead`, `score_type`, `score`, `reliability`, `sources` and
  `demo_data`. The score type is `conditions_today` for the same day and
  `forecast` for 1 to 7 days ahead. Reliability is high up to 2 days ahead,
  medium up to 5 and low for 6 and 7.
- Every answer, errors included, has `"demo_data": true`, a `notice` sentence
  and the header `X-Demo-Data: true`. The page shows a yellow notice that
  cannot be closed, and the square details end with "Made-up demo data".
- The made-up grid has 7,049 squares of 500 m from `docs/data_formats.md`
  over Pistoia province and the Apennines, from 10.62 to 11.05 E and 43.72 to
  44.18 N. `apps/api/tools/make_demo_grid.py` rebuilds it. The P2 grid has
  only 504 squares, too few to test how large requests get.
- The API refuses a request with more than 4,000 squares and asks the user to
  zoom in. The page asks for squares only from zoom 11.
- `apps/web/` is the page: plain HTML and JavaScript with MapLibre GL JS
  4.7.1, a free map library under the BSD 3-Clause licence. It has a map, a
  species picker, a date picker and a target date picker, and shows a
  square's details in a panel at the bottom when tapped.
- The background map is the OpenFreeMap "liberty" style. OpenFreeMap is free,
  needs no key or account, and allows this use. The map data is
  OpenStreetMap, credited in the corner.
- The page and the API run as two programs on ports 8000 and 8080. The page
  gets all scores from the API. Only the background map comes from
  OpenFreeMap.
- `docker build -t sporameteo-api:p5 apps/api` builds the API as a container
  image, and `docker run --rm -p 8080:8080 sporameteo-api:p5` runs it. #12 can
  use this image.

## Measurements

### Data size and answer time of the API

`uv run sporameteo run p5_phone_map` starts the API, asks for squares the way a
phone window of 390 by 844 pixels would, and writes
`reports/p5_api_requests.csv` and `reports/p5_api_memory.csv`. Each view was
asked for on the same day, 2 days ahead and 7 days ahead. The table shows the
same-day view. The other days differ by less than 2 percent.

| Map zoom | What fits on screen | Squares | Plain size | Compressed size | Median answer time |
|---|---|---|---|---|---|
| 10 | about 21 by 46 km | refused, over 4,000 | | 164 B | 1 ms |
| 11 | about 11 by 23 km | 1,086 | 519 KB | 27 KB | 11 ms |
| 12, the start | about 5 by 12 km | 279 | 134 KB | 7.4 KB | 3 ms |
| 13 | about 3 by 6 km | 84 | 40 KB | 2.5 KB | 2 ms |

Compression makes each request about 19 times smaller, because every square
repeats the same field names and dates. Without compression the widest view
would be half a megabyte.

### Memory of the API

| Where | Memory |
|---|---|
| Python on the laptop, after start | 40 MB |
| Python on the laptop, after all requests | 42 MB |
| Container, measured with `docker stats` | 35 MB |

### Time until the page is usable

"Usable" means the first squares are drawn and the map has stopped loading.
The page records this moment in `window.sporameteoUsableMs`. Each load started
with an empty browser cache, in Chromium through Playwright, with a phone
window of 390 by 844 pixels, touch turned on and an iPhone user agent.

| Setting | Three loads | Squares request |
|---|---|---|
| Laptop speed | 2.7 s, 3.5 s, 0.9 s | 9 to 52 ms |
| Connection slowed to 1.6 Mbit/s with 150 ms delay, processor 4 times slower | 3.8 s, 2.5 s, 3.5 s | 156 to 203 ms |

Most of the time goes to the map library, 211 KB compressed, and the
background map from OpenFreeMap. The squares themselves take at most 0.2
seconds. The page used 16 to 21 MB of JavaScript memory.

## How it feels to use by touch

### On a real phone

The user tried the page on an iPhone 15 with Safari, on the same Wi-Fi as the
laptop, on 11 October 2026.

- Opening: quick.
- Moving the map: smooth at first, then slower with each move, and then the
  page froze. The phone sent 9 square requests in 25 seconds before it
  stopped. Each view held a few hundred squares, and the API answered every
  request with 200.
- Zooming: pinch to zoom worked at first.
- Reading text: readable without zooming the page.
- Tapping squares: easy at the starting zoom.

### In a simulated phone window

These checks used Chromium with a simulated touch screen.

- Moving the map: a one-finger drag moves the map, and the page asks for the
  new area about 250 ms after the map stops.
- Zooming: a two-finger pinch zooms in and the page loads the smaller set of
  squares. Below zoom 11 the squares disappear and a line says "Zoom in to
  see squares".
- Reading text: the notice, hints and details use 15 px and the pickers 16 px,
  so an iPhone does not zoom in when one is tapped. Picker labels use 12 px,
  the legend 13 px and the map credit 11 px. Place names stay readable under
  the coloured squares at 55 percent opacity.
- Tapping squares: a tap opens the details panel and outlines the square in
  blue. The close button is 44 by 44 px. A tap outside the squares closes the
  panel. At the starting zoom a square is about 36 px wide on screen, a
  comfortable size for a finger. At zoom 11 a square is about 18 px wide and
  harder to hit.
- The three pickers sit side by side at 117 px each. The first version showed
  "Same day, 11 Oct" and cut it off, so the target date picker now shows only
  the date, such as "13 Oct +2".

### Looking for the freeze

Chromium did not freeze. With the processor slowed 6 times and a phone window
at 3 device pixels per CSS pixel, 25 moves of the map in a row each loaded
275 to 298 squares in 11 to 41 ms. The page never blocked for longer than
58 ms, and JavaScript memory went up and down between 21 and 57 MB without
growing. Safari could not be started on this laptop for the same test.

So the freeze comes from Safari on the iPhone. The likely suspects, none of
them proven:

- The OpenFreeMap "liberty" background is a detailed vector map that the phone
  draws itself, at 3 device pixels per CSS pixel.
- MapLibre GL JS 4.7.1 and Safari on iOS may use up graphics memory together.
- Each move replaces the whole set of squares on the map.

If the page is reused, the first check is to load it on the iPhone three ways: without the
background map, with a simple background of ready-made images, and without the
squares. The one that does not freeze shows the cause.

## What this does not show

- Only one real phone was used, an iPhone 15 with Safari, and it froze. The
  cause is not known. No Android phone was tried.
- The scores are made up, so this says nothing about whether they are right.
- One user at a time. There was no load test.

## What would change for a real app

- The map must not freeze on an iPhone. Until the cause is found, a lighter
  background map is the first thing to try.
- At zoom 11 a square is 18 px wide and hard to tap. A real app could show larger
  summary squares when zoomed out, or ask for squares only from zoom 12.
- Each square repeats `species`, the dates and the sources. Moving the shared
  values to the top of the answer, or sending vector tiles, would shrink the
  plain size. With compression the gain is small.
- Scores computed in advance for 7,049 squares, 2 species, 14 days and 8 days
  ahead make about 1.6 million values. A real API would read them from a
  file or database instead of computing them on request.

## Evidence

- Run record: `reports/runs/p5_phone_map/20261011T111704Z-e8170c.json`
- API sizes and times: `reports/p5_api_requests.csv`
- API memory: `reports/p5_api_memory.csv`
- Tests: `tests/test_p5_api.py`
