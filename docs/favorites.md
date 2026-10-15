# Browser favorites

Favorites use `localStorage` under the key `sporameteo.favorites`. The current
format is version 1:

```json
{
  "version": 1,
  "items": [
    {
      "id": "local-id",
      "kind": "grid",
      "latitude": 44.13,
      "longitude": 10.64,
      "cellId": "grid-cell-id",
      "name": "Faggeta Abetone",
      "color": "green"
    }
  ]
}
```

Point favorites contain `id`, `kind`, `latitude`, `longitude` and `name`.
Grid favorites also contain `cellId`. The optional color is one of `green`,
`amber`, `violet`, `blue` or `rose`. Coordinates are finite values within the
world latitude and longitude ranges. Names are text with at most 160
characters. A record with any other field is invalid and remains in the raw
`items` array when a later write succeeds.
Rows with duplicate IDs are all kept as raw invalid rows. Only an ID that
appears once is usable. Editing or removing a usable row does not change the
retained duplicate rows.

Grid duplicates use the same `cellId`. Point duplicates use the same exact
stored latitude and longitude. Saving a duplicate reopens the existing
favorite and does not add a second row. Reopening a grid favorite requests the
current map squares and selects only its saved `cellId`. It never picks a
neighboring square. A missing cell stays at its saved map center and shows the
translated unavailable state. Reopening a point sends its saved coordinates to
the normal point resolver with the `point` source. Reopening a grid sends its
saved coordinates to the normal map squares request, then requests the saved
cell from the current area results. The current lookup result fills the map
details.

The browser notice explains that favorites stay in this browser, do not sync
between devices and can disappear when browser data is cleared. A disabled
storage object or a write failure leaves the user-facing state unchanged and
shows a translated failure. A quota failure shows a separate full-storage
message. A version 1 wrapper with invalid rows keeps valid rows and preserves
the invalid rows during later writes while showing a warning. Invalid JSON and
unknown versions are read only and are never overwritten. Storage getters,
reads and writes are caught so the map remains usable.

Favorite IDs, names, colors and the full stored record stay in this browser.
The app does not put them in URLs, request bodies, headers or prediction
requests. Opening a point sends its saved coordinates to the normal resolver.
Opening a grid sends its saved coordinates and cell ID through the normal map
squares and area requests. Those coordinates and cell IDs identify the normal
lookup destination and can appear in those requests.

The browser checks cover the normal `/map/` route with intercepted API
responses. They add point and grid records, reload them, reopen the current
destination, rename, recolor, remove, and reject duplicate destinations. They
also inspect the point resolver request, exact grid ID requests, unsupported
point and cell destinations, missing weather, invalid typed coordinates,
literal HTML names, malformed rows, duplicate stored IDs, delayed location
callbacks, invalid JSON, future versions, disabled storage and quota failures.
The browser notice is checked in English on desktop viewports and Italian on a
phone viewport. The dialog is checked at 768 pixels wide, and favorites are
reopened at a 2560 pixel wide viewport. The default pytest browser matrix runs
the same checks in Chromium and WebKit.

Validation evidence from this work:

- `uv run pytest tests/e2e/test_favorites.py` passed all 34 cases in the
  default Chromium and WebKit matrix.
- `uv run pytest tests/e2e/test_favorites.py -k 'quarantine_all_rows or
  point_wins_over_delayed_geolocation_callback'` passed 4 focused Chromium
  and WebKit cases for the collision and callback coverage.
- `uv run python -m compileall -q tests/e2e/test_favorites.py` passed.
- A headed parent check passed on the normal `/map/` route at 1440 by 900 in
  English and 390 by 844 in Italian. It checked the desktop drawer and phone
  sheet, with no horizontal overflow or page JavaScript errors.
- Request inspection observed no stored favorite IDs, names, colors or
  serialized favorite record in request URLs, bodies or headers.
