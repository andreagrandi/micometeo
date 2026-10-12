# Application read API

The Django application serves anonymous reads under `/api/v1`. The generated
schema is at `/api/v1/openapi.json` and the interactive reference is at
`/api/v1/docs`. Run the application with the completed national grid, terrain
and forest builds, the weather migrations and the estimate migrations.

These routes return stored product data. The percentage is experimental and
unvalidated. It does not measure a visitor's chance of finding a mushroom.

| Route | Purpose |
| --- | --- |
| `GET /info` | Today's Italian date, eight target dates, national coverage and map limits. |
| `GET /forest-layer` | The simplified national forest polygons, with no estimates or weather request. |
| `GET /squares?bbox=west,south,east,north&target_date=YYYY-MM-DD` | Squares and stored estimates for the visible map. |
| `GET /areas/{square_id}?target_date=YYYY-MM-DD&update_id=UUID` | One exact saved estimate and the inputs behind it. Omit the UUID only to classify a square with no selected update. |

Coordinates use WGS84 longitude and latitude. Square IDs identify the national
500 m grid. Dates use Europe/Rome. The map accepts today through seven days
ahead. Details accept the eight original dates of the requested update,
including a retained previous assessment.

## Metadata and forest layer

```sh
curl http://127.0.0.1:8010/api/v1/info
curl --compressed http://127.0.0.1:8010/api/v1/forest-layer
```

The metadata supplies `today`, `target_dates`, `coverage`,
`forest_build_version`, `max_width_km`, `max_height_km`, `max_squares` and
`forest_layer`. The layer descriptor contains its URL, SHA-256 and compressed
and uncompressed sizes. Coverage is the national grid's bounding box, not a
promise that every point inside the box is Italian land.

The forest layer is the immutable artifact recorded by the completed forest
build. Its only per-polygon value is `forest_share`. The endpoint checks its
checksum and sizes. Neither metadata nor the forest layer calls the weather
provider.

## Map squares

```sh
curl --compressed \
  'http://127.0.0.1:8010/api/v1/squares?bbox=10.60,44.10,10.70,44.20&target_date=2026-10-12'
```

Replace the date with one returned by `/info`. A successful response is a
GeoJSON `FeatureCollection` with `target_date`, `square_count` and `features`.
Every feature has its square ID, WGS84 polygon and these properties. This is
an illustrative available-result excerpt:

```json
{
  "state": "available",
  "percentage": 65,
  "unavailable_reason": null,
  "reason": null,
  "target_date": "2026-10-12",
  "assessment_date": "2026-10-12",
  "update_id": "550e8400-e29b-41d4-a716-446655440000",
  "calculated_at": "2026-10-12T08:30:00Z",
  "message_key": "estimate.available"
}
```

The response also includes `cell_id`. Copy the feature ID, target date and
update ID together when opening details. One view can contain updates from
different assessment dates. An older estimate keeps its original dates and
calculation time. It never gains a new eighth date when the clock advances.

| State | Percentage | Meaning |
| --- | --- | --- |
| `available` | Whole integer, including a valid zero | The stored result is available. |
| `noforest` | `null` | The square has less than ten percent forest. |
| `unavailable` | `null` | A required input is missing. The reason identifies it. |
| `noresultyet` | `null` | Weather or estimate work has not produced a result yet. |
| `expired` | `null` | The requested day lies outside the saved update's dates. |

For example, no forest has `state: "noforest"` and `reason: "noforest"`.
A missing old-rain input has `state: "unavailable"` and
`reason: "older_rain"`. Pending work has `state: "noresultyet"` and
`reason: "pending"`. None of these means zero percent. The current method
normally produces values from 5 through 95. The storage and API contracts
still preserve a valid stored zero.

The provisional view limit is 60 km on each axis and 16,000 squares. Bounds
must be finite numbers in coordinate range, with west before east and south
before north. A broader view returns HTTP 400 before any weather work:

```json
{
  "code": "view_too_large",
  "message": "Zoom in for estimates before requesting this view.",
  "message_key": "map.zoom_in_for_estimates",
  "details": {
    "width_m": 90000,
    "height_m": 70000,
    "max_width_m": 60000,
    "max_height_m": 60000
  }
}
```

A permitted view asks the weather service for its distinct forest weather
cells. The service reuses today's completed work or queues the missing work.
The map waits at most three seconds for weather. It reads stored estimate
rows after that lookup. Calculation happens in the worker.

The server cache includes the date, bounds, forest build, weather state,
snapshot identities and estimate update UUIDs. Responses support gzip.
Map and forest-layer responses use `Cache-Control: no-cache`, so a browser
must revalidate them. Their ETags change with the selected update or artifact.
Full weather histories and contributing facts belong to details and do not
repeat for every polygon.

## Selected-area details

```sh
curl 'http://127.0.0.1:8010/api/v1/areas/500m_E4370000_N2330000?target_date=2026-10-12&update_id=550e8400-e29b-41d4-a716-446655440000'
```

Use a real square ID and update UUID from `/squares`. The example UUID above
is illustrative. The endpoint never fetches weather or substitutes the newest
update for the requested one.

The selected square must belong to the update's weather cell. A UUID from
another area returns `update_square_mismatch` and attaches no weather data.
For map squares with a null update ID, omit that query value. The endpoint
checks the configured forest build and returns a structured state error for
no forest, missing forest data or an estimate that is not available yet.
It never invents an update or silently chooses the newest one.

| Response group | Stored content |
| --- | --- |
| `selection` | Square ID, polygon, bounds, centroid, representative coordinates, target date, assessment date, days ahead and update UUID. |
| `estimate` | State, `whole_percentage`, unavailable reason, calculation time, method version, `experimental_unvalidated`, availability translation key and `experimental_explanation_key`. |
| `facts` | Actual method inputs and derived factors, units, inclusive periods, source IDs, completed and forecast day counts and translation keys. |
| `weather` | Selected-day values, rain totals for the previous 7, 14 and 21 completed days, source metadata, missing values and limitations. |
| `sources` | Exact forest, terrain and weather source records, release dates, retrieval dates, checksums, real source detail, credits and gaps. |

`selection.representative_coordinates` identifies the selected square. Use it
for favorites and navigation. Do not replace it with the current map centre.

Map `properties.percentage` and detail `estimate.whole_percentage` refer to
the same stored byte. The detail rebuilds facts from that update's exact
weather snapshot and habitat builds. A later update cannot change a retained
previous update's explanation.

A contributing fact has `role_key`, `actual_value`, `unit`, `period_start`,
`period_end`, `source_id`, `source_ids`, `completed_day_count`,
`forecast_day_count`, `method_factor` and `translation_key`. The schema also
exposes equivalent `role`, `value`, `period`, `source` and `normalized_factor`
fields. Product text can translate complete sentences from the keys and
values. Source names and required attribution remain intact.
The experimental explanation key is `estimate.experimental_unvalidated`.
The generated schema types timestamps as `date-time` and defines the nested
fact periods, source identities, gaps, terrain tiles and weather attribution.

Weather attribution includes the exact credit `Weather data by Open-Meteo.com`,
the link `https://open-meteo.com/` and `CC BY 4.0`. The website must show the
applicable credits with the data. Forest and terrain records retain their
dataset-specific attribution and source dates.

For an assessment on 12 October, the recent seven-day period is 5 through
11 October. The 14-day period starts on 28 September and the 21-day period on
21 September. None contains rain forecast for 12 October or later. Each
period reports both boundaries, its unit, missing reason and source attempts.

Optional soil and evaporation values remain null when unavailable. Frost
appears only when the stored minimum temperature supports its derivation.
There is no invented hail value, numerical prediction confidence or accuracy
label based only on days ahead. The limitation keys explain that multiple
500 m squares can share weather covering several kilometres.

## Errors

Errors contain `code`, `message`, `message_key` and `details`. Clients should
translate `message_key` with the supplied values. The readable English message
also helps inspect an API response.

| HTTP status | Code | Meaning |
| --- | --- | --- |
| 400 | `missing_parameter`, `invalid_bbox`, `invalid_date`, `invalid_update_id`, `invalid_square_id` | Malformed or missing input. |
| 400 | `unsupported_date` | The map target is outside today's eight dates. |
| 400 | `view_too_large`, `square_limit_exceeded` | Zoom in before requesting estimates. |
| 400 | `outside_coverage` | The view intersects no national grid square. |
| 404 | `square_unknown` | The square does not belong to the requested update's forest build. |
| 409 | `update_square_mismatch` | The square and update refer to different weather cells. |
| 409 | `no_forest`, `missing_forest_data`, `estimate_not_available` | The square has no selected saved estimate. No unrelated weather is attached. |
| 410 | `update_expired` | The requested update UUID is no longer available. Refresh the map. |
| 503 | `forest_build_unavailable`, `forest_layer_unavailable` | The configured completed build or checked artifact is unavailable. |

A deleted update returns this shape, with the requested UUID in `details`:

```json
{
  "code": "update_expired",
  "message": "The requested estimate update is no longer available.",
  "message_key": "area.update_expired",
  "details": {"update_id": "550e8400-e29b-41d4-a716-446655440000"}
}
```

## Largest-view measurements

### Live request through the worker

On 12 October 2026, the view `10.653,44.137,10.661,44.143` near Abetone
returned six pending squares. The normal database worker then made one
Open-Meteo request for the weather cell centred at 44.15, 10.65. It stored
29 daily rows, eight summaries and estimates for all 340 forest squares of
that weather cell.

The next map response returned six available squares. Details for
`500m_E4373000_N2336500` matched its saved map value of 5 and update
`5aac5767-92d1-4bd5-bc30-44fca00ced81`. The weather retrieval time was
`2026-10-12T02:08:41.172757Z`, with attempt
`b4d638f5-fef5-4561-891b-3fcd40a343ac`. Open-Meteo returned model-grid
coordinates 44.149982, 10.645727 and reference elevation 1,319 m.

A repeated map request and the detail request made no further provider call.
An Italy-wide request returned `view_too_large` and created no weather fetch.
This checks the live data path and identity agreement, not prediction accuracy.
The local evidence is `/tmp/agents/micometeo-live-pipeline-verified.json`.

The normal worker command used for this check was:

```sh
uv run python apps/application/manage.py run_background_worker \
  --batch --no-startup-delay --no-reload --max-tasks 10
```

### National response and desktop drawing costs

The 12 October 2026 local measurement used the national habitat builds and
the disposable database from [the estimate benchmark](estimate_updates.md).
Its percentages came from labelled synthetic benchmark weather. A stored
snapshot lookup replaced weather acquisition, so this measures database
reads, polygon conversion, JSON and compression without provider latency.
It made no weather HTTP request.

The laptop was an Apple M2 Pro with 32 GiB of memory. Each view measured
about 59.4 by 59.2 km. Each request made five database queries. The first
read populated the response cache, followed by two cached reads.

| View | Squares | Forest squares | Raw bytes | Gzip bytes | First read | Cached reads |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Northern Apennines | 14,286 | 13,356 | 9,260,493 | 819,559 | 2.1085 s | 1.0526 and 1.1008 s |
| Alps | 14,261 | 12,511 | 9,196,599 | 830,451 | 1.6551 s | 1.0818 and 1.1194 s |
| Calabria | 13,145 | 11,013 | 8,432,366 | 759,762 | 1.6254 s | 1.0831 and 1.0047 s |

Gzip length can differ by a few bytes because Django adds random padding.
The broad Italy view returned `view_too_large` with zero weather calls.
The 16,000-square limit allows these near-60-km national views. It remains
provisional until drawing on a physical phone is measured. A desktop browser
with a phone-sized window is not a physical-phone acceptance check.

The same saved responses were drawn with MapLibre GL JS 4.7.1 in a visible
Chrome 154.0.8037.98 window, 1,440 by 900 CSS pixels at two device pixels per
CSS pixel. The measurement used an isolated persistent browser profile and
an empty background map. It timed `addSource` through the first `idle` event
after adding the fill layer. It excludes background tiles and network transfer
from a deployed server.

| View | Three drawing times |
| --- | --- |
| Northern Apennines | 334.1, 313.4 and 312.2 ms |
| Alps | 309.2, 316.9 and 312.5 ms |
| Calabria | 309.7, 312.0 and 312.4 ms |

These results support retaining the provisional desktop limit. They do not
establish a safe phone limit. [Follow-up #64](https://github.com/andreagrandi/micometeo/issues/64)
tracks the physical-phone check required before closing #49. Any closer starting view needs the owner's
agreement, as required by that ticket.

The local measurement artifacts are under `/tmp/agents/` on the development
laptop. `micometeo-map-measurements.json` records response sizes and timings.
`micometeo-map-drawing-measurements.json` records browser timings.
`micometeo-map-drawing.html` draws the saved response files. To repeat the
desktop drawing measurement with those artifacts:

```sh
python3 -m http.server 8769 --bind 127.0.0.1 --directory /tmp/agents
node /tmp/agents/measure_micometeo_drawing.cjs
```

The temporary scripts and responses are local measurement artifacts, not a
product frontend. For a fresh dataset, request the documented views from the
application and save each GeoJSON response before running the drawing page.

For API contract checks, run:

```sh
uv run pytest tests/app/test_map_api.py tests/app/test_area_api.py
```

The fixtures cover saved values, unchanged previous updates, expired updates,
rain periods, missing required and optional inputs, source credits, broad
views, invalid bounds, date limits and cache identities. They replace external
weather and never depend on a live provider.
