# Micometeo demo map

This page shows a map of 500 m grid squares coloured by a score from 0 to 100.
All scores are made up. They do not describe real mushrooms.

The page is plain HTML, CSS and JavaScript. It needs no build step and no npm.
It gets all score data from the API in `apps/api/`.

## Run it

1. Start the API on port 8080. See `apps/api/` for the command.
2. From the repository root, serve this folder:

   ```
   python3 -m http.server 8000 --directory apps/web
   ```

3. Open http://localhost:8000.

## Open it from a phone

1. Connect the phone to the same Wi-Fi as the laptop.
2. Start the API so it listens on all network addresses, not only on
   localhost. Run `MICOMETEO_API_HOST=0.0.0.0 python3 -m micometeo_api` in
   `apps/api`, or use the Docker command in `apps/api/README.md`. Serve the
   page with `--bind 0.0.0.0` added to the command above.
3. Find the laptop address, for example 192.168.1.20.
4. Open http://192.168.1.20:8000 on the phone.

`config.js` builds the API address from the host name in the page address, so
the phone asks the laptop at port 8080. If the API cannot be reached, the page
shows the address it tried.

## Map tiles and licences

- The background map uses the OpenFreeMap "liberty" style from
  https://tiles.openfreemap.org/styles/liberty. It is free and needs no key.
  The map data comes from OpenStreetMap contributors. The attribution stays
  visible in the bottom right corner.
- MapLibre GL JS 4.7.1 is loaded from unpkg. It uses the BSD 3-Clause licence.

## Measurement values

The page sets two values for timing checks:

- `window.micometeoUsableMs`: milliseconds from page start until the first
  squares are drawn and the map is idle.
- `window.micometeoLastRequest`: `url`, `bytes`, `squares` and `ms` of the last
  squares request.
