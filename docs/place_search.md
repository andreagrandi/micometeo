# Place search

SporaMeteo sends place searches through its own `/api/v1/places/search` route.
The browser never calls the provider and never receives a provider credential.
The current provider is Photon, the free OpenStreetMap search service operated
by Komoot. The endpoint can change through `SPORAMETEO_PLACE_SEARCH_URL`.

Photon has no service level agreement and no numeric quota that SporaMeteo can
rely on. Its public demo server has not met the desired autocomplete speed.
On 2026-10-13, direct requests took 1.85 to 2.76 seconds, while an exact cached
query through SporaMeteo took 76 milliseconds. SporaMeteo keeps successful exact
results for 30 days and empty exact results for 15 minutes. A read-only prefix
preview can use another unexpired cached query, but it never becomes an exact
cache row and does not avoid a provider request when the preview is incomplete.
Photon asks clients to keep requests reasonable. SporaMeteo therefore uses a
minimum query length, a 220 millisecond browser delay, a result limit, separate
positive and empty database cache lifetimes, and one database locked request
interval for all workers.
These are SporaMeteo limits. They do not claim to be Photon policy.
Each fresh response removes up to 100 expired cache rows through an indexed
expiry lookup. Exact cache hits and preview requests do not perform cleanup.

The backend sends `countrycode=IT` and the city, locality and district layers.
For Italian browser text it sends Photon's `default` language value because
Photon does not accept `it` on the public endpoint. English requests use `en`.
It keeps the result name, useful place context, coordinates and optional bounds.
The response includes OpenStreetMap and Photon attribution. The search result
list also links to [Photon](https://photon.komoot.io/) and
[OpenStreetMap](https://www.openstreetmap.org/copyright). A provider 429
response becomes a short retry response with `Retry-After` when Photon sends
one. A timeout and an unavailable provider remain separate API error codes.
The same route accepts `cached_only=1` for a read-only autocomplete check. It
returns an exact unexpired result, including an exact empty result, with
`complete: true`. A result assembled from related cached prefixes has
`complete: false` and is never saved under the new query.

The browser keeps up to 100 exact responses in page memory for 30 minutes,
or one minute for empty responses. Repeated queries skip the browser delay and
network request. Matching names from earlier responses appear immediately as
the query changes. The shared cache supplies previews for other visitors while
Photon loads the full result list. If that request fails, matching cached
suggestions remain selectable. This cache does not use browser storage or
contain geolocation selections.

Selecting a search result or using current location sends a same-origin JSON
`POST` to `/api/v1/places/resolve` with the exact WGS84 coordinates. The route
checks the point against the completed ISTAT region geometry and the matching
`GridBuildCell.land_geometry`. It does not use a broad country rectangle or
move a point to its nearest cell. A point outside Italy and a point in Italy
outside configured coverage have separate responses when the region data is
available. The returned square representative is only a map destination. It
does not describe a road, trail, parking area or known mushroom position.
The resolver response is marked `no-store`.

Search and manual map selections retain their map state in the URL. A current
location selection stays in one temporary `sessionStorage` entry for the open
tab. It stores the exact point and current map view so a language reload can
restore the selection. It never adds a location history, uses `localStorage`,
or writes GPS coordinates, square IDs, representatives or map centres to the
navigable URL. A later search, map selection or cleared selection removes the
temporary entry.

Local configuration uses these environment variables:

- `SPORAMETEO_PLACE_SEARCH_URL`, default `https://photon.komoot.io/api`.
- `SPORAMETEO_PLACE_SEARCH_TIMEOUT`, default `4` seconds.
- `SPORAMETEO_PLACE_SEARCH_CACHE_SECONDS`, default `2592000` seconds.
- `SPORAMETEO_PLACE_SEARCH_EMPTY_CACHE_SECONDS`, default `900` seconds.
- `SPORAMETEO_PLACE_SEARCH_REQUEST_INTERVAL`, default `1` second.
- `SPORAMETEO_PLACE_SEARCH_LIMIT`, default `8` results.
- `SPORAMETEO_PLACE_SEARCH_MIN_LENGTH`, default `2` characters.
- `SPORAMETEO_PLACE_SEARCH_USER_AGENT`, default `SporaMeteo/1.0 place search`.

On 2026-10-13, a live check of [Photon](https://photon.komoot.io/) returned
Italian results for Pistoia, Abetone, Femminamorta and Momigno. The check used
the public endpoint without credentials. Photon documents its API at
<https://github.com/komoot/photon/blob/master/docs/api-v1.md>. The provider
endpoint and response terms must be checked again before a public deployment.
The [Geoapify pricing page](https://www.geoapify.com/pricing/) lists a free
tier of 3,000 credits per day and 5 requests per second, with an account
required. Switching to it requires a separate API adapter and latency checks.
The
[Nominatim policy](https://operations.osmfoundation.org/policies/nominatim/)
does not allow autocomplete, so SporaMeteo does not use it for this feature.
The map still credits OpenStreetMap and OpenFreeMap separately from the search
provider.

The browser calls geolocation only after the visitor presses the location
button. It does not watch the device or store a location history. A secure
context is required, except for localhost. A mocked browser permission check
does not prove that a physical phone can grant permission. Headed desktop and
phone-sized browser checks passed with mocked location callbacks. A real phone
check needs the HTTPS instructions in
[local development](local_development.md#phone-access-through-tailscale) and
remains pending until the owner runs it.
No paid domain, server or provider account is needed for local testing.

Run the background worker alongside the web server when testing live estimates:

```text
uv run python apps/application/manage.py run_background_worker
```

Place suggestions do not need the worker. Weather downloads and estimate
calculations do. Without it, new areas remain pending even when place search
and map movement work. Check that the selected square shows a completed
assessment before handing over a live test session.

Focused checks:

```text
uv run pytest tests/app/test_place_search.py
uv run pytest tests/e2e/test_place_search.py
```
