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

- The nightly chain on two consecutive real nights belongs to #62. No nightly
  worker had run when this report was written.
- The slow fetch test raises a timeout at once. It does not wait for a real
  slow answer.
- Coverage of other regions, including the Alps, Sicily and Sardinia, waits
  for the later all-Italy version.
