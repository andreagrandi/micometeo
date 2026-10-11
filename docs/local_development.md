# Local development

This guide runs the Micometeo Django application on the laptop and a PostGIS
database in Docker. It needs no public domain, hosting account or paid service.

## Clean setup

Run these commands from the repository root. Install `uv`, Docker with Compose,
Homebrew and `direnv` first. Start Docker and enable the direnv hook for your
shell. The lockfile uses Python 3.14, which `uv sync` installs if needed.

Install the native libraries that GeoDjango uses on macOS:

```sh
brew install gdal geos proj libpq
```

Copy the environment template only when `.envrc` does not exist. This keeps an
existing file and its GBIF settings unchanged:

```sh
if [ ! -e .envrc ]; then cp .envrc.example .envrc; fi
```

If `.envrc` already exists, add the local application settings from
`.envrc.example` without replacing the existing GBIF settings. Set
`MICOMETEO_DJANGO_SECRET_KEY` and `MICOMETEO_DB_PASSWORD` to local values.
Keep the database name, user and port at their defaults for the commands below.
Add the Homebrew GEOS library path to `.envrc`:

```sh
export GEOS_LIBRARY_PATH="$(brew --prefix geos)/lib/libgeos_c.dylib"
```

On macOS, Django uses the GDAL library bundled with the locked Rasterio wheel.
Homebrew GDAL loads another Arrow library, which conflicts with PyArrow during
Parquet reads and writes. The application therefore prefers the bundled copy
over `GDAL_LIBRARY_PATH`. Use `MICOMETEO_GDAL_LIBRARY_PATH` only to select a
compatible custom build. On systems without the bundled library, Django uses
`GDAL_LIBRARY_PATH` or its normal native-library discovery.

Load the environment and install the locked Python environment:

```sh
direnv allow
uv sync --locked
```

Check and start the database. Compose publishes it only on the laptop loopback
address, so it does not listen on the local network:

```sh
docker compose config --quiet
docker compose up --wait database
docker compose ps
docker compose port database 5432
```

The last command reports `127.0.0.1:5542` with the default settings. Run the
Django migrations and start the application on its fixed local address:

```sh
uv run python apps/application/manage.py migrate
uv run python apps/application/manage.py runserver 127.0.0.1:8010
```

In another terminal, check the API:

```sh
curl --fail-with-body --silent --show-error http://127.0.0.1:8010/api/v1/health
```

The available response has these fields:

```json
{"application":"available","database":"available"}
```

The endpoint returns HTTP 503 and this body when PostgreSQL is unavailable:

```json
{"application":"available","database":"unavailable"}
```

It never includes database settings or connection error details.

## Database checks

Run the focused application checks while the database is healthy:

```sh
uv run pytest tests/app/test_application_setup.py
```

The checks query `PostGIS_Version`, store and read a temporary WGS84 point,
check the database UTC session, and verify both health responses. They create
no product tables. Product dates use `Europe/Rome`, while stored event
timestamps use UTC.

To check the unavailable and recovery responses manually, stop and start the
database while the Django server remains running:

```sh
docker compose stop database
curl --silent --show-error --include http://127.0.0.1:8010/api/v1/health
docker compose start database
docker compose up --wait database
curl --fail-with-body --silent --show-error http://127.0.0.1:8010/api/v1/health
```

The named `micometeo_pgdata` volume keeps database contents across service
restarts. Compare a migration row before and after recreating the container:

```sh
docker compose exec database psql \
  -U "${MICOMETEO_DB_USER:-micometeo}" \
  -d "${MICOMETEO_DB_NAME:-micometeo}" \
  -c "SELECT id, app, name, applied FROM django_migrations ORDER BY id LIMIT 1;"
docker compose down
docker compose up --wait database
docker compose exec database psql \
  -U "${MICOMETEO_DB_USER:-micometeo}" \
  -d "${MICOMETEO_DB_NAME:-micometeo}" \
  -c "SELECT id, app, name, applied FROM django_migrations ORDER BY id LIMIT 1;"
```

`docker compose down` removes the container but keeps the named volume.
`docker compose down --volumes` removes the local database contents and is only
needed for a deliberate reset.

## Phone access through Tailscale

The application works on the laptop without Tailscale. Tailscale Serve gives a
phone on the owner's private Tailscale network an HTTPS address, which browsers
need for location access. It does not publish the application to the internet.

Install and connect Tailscale on the laptop and phone using the same network.
The commands below also need `jq`. Find this laptop's certificate hostname and
check whether another application already uses Serve:

```sh
TAILSCALE_HOST="$(tailscale status --json | jq -r '.Self.DNSName' | sed 's/\.$//')"
printf '%s\n' "$TAILSCALE_HOST"
tailscale serve status
```

Tailscale publishes the certificate name, and therefore the network name, in
public certificate logs. See the [Tailscale HTTPS documentation](https://tailscale.com/docs/how-to/set-up-https-certificates).
Set the hostname in `.envrc` before starting or restarting Django:

```sh
export MICOMETEO_ALLOWED_HOSTS=127.0.0.1,localhost,laptop.tailnet-name.ts.net
export MICOMETEO_CSRF_TRUSTED_ORIGINS=https://laptop.tailnet-name.ts.net
```

Replace the example hostname with the value from `tailscale status`. Reload the
environment and restart `runserver`, then configure private HTTPS forwarding:

```sh
direnv allow
tailscale serve --bg --https=443 http://127.0.0.1:8010
tailscale serve status
```

If Serve asks you to enable HTTPS, follow its setup link before continuing.
If another application uses HTTPS port 443, choose port 8443 and add `:8443`
to the trusted origin and phone URL. Use the same port in the Serve shutdown
command. Keep the hostname without a port in `MICOMETEO_ALLOWED_HOSTS`.

On the phone, open this URL while it is connected to the same Tailscale
network:

```text
https://laptop.tailnet-name.ts.net/api/v1/health
```

Replace the hostname with the value from `TAILSCALE_HOST`. The phone should
receive the available JSON response. Do not enable Tailscale Funnel, which
opens the service to the internet. Turn Serve off with the matching command
when the check is complete:

```sh
tailscale serve --https=443 off
```

## Shutdown

Stop Django with `Ctrl+C` in its terminal. Turn off this application's Tailscale
Serve route if it is active, then stop PostGIS:

```sh
docker compose down
```

The database volume remains available for the next `docker compose up --wait database`.

## Directory map

```text
apps/application/manage.py       Django command entry point
apps/application/config/          settings, API, URLs and server entry points
apps/api/                         P5 synthetic API experiment
apps/web/                         P5 static demonstration
src/micometeo/                    experiment package and CLI
tests/app/                        Django and PostGIS foundation checks
docker-compose.yml                local PostGIS service only
```

## Book Corners references

The application follows [Book Corners](https://github.com/andreagrandi/book-corners)
patterns from `config/settings.py`, `config/urls.py`, `config/api.py` and
`docker-compose.yml` for environment settings, the PostGIS backend, API routing
and database health checks. Micometeo adds an explicit database availability
response to its health endpoint.

Book Corners installs geographic libraries in its `Dockerfile`. Micometeo
uses host libraries because Django runs on the host through `uv`. On macOS,
Rasterio supplies GDAL and Homebrew supplies GEOS.
It keeps one lockfile for the application and experiments. Only PostGIS runs
in Compose, using AMD64 emulation on Apple Silicon for the selected image.

Book Corners discovers dynamically assigned ports through `scripts/local_env.py`.
Micometeo uses fixed ports 8010 and 5542, and `docker compose port` reports the
database mapping. Change `MICOMETEO_DB_PORT` before starting Compose if 5542 is
occupied. Choose another `runserver` port if 8010 is occupied, then update the
local trusted origins and Tailscale forwarding target to match.

The application stays separate from the existing P5 directories. This local setup has no worker,
production tables, account system, frontend build, deployment job or hosting
credentials.

## Recorded walkthrough

On 2026-10-11, the locked environment ran on macOS with Python 3.14.8 and
Django 6.1.2. Compose started PostGIS on port 5542 and Django applied its
migrations. The focused checks passed against PostGIS, including the
geometry write and read with coordinate system 4326 intact. The full suite
passed after selecting Rasterio's GDAL library. An additional Parquet
regression check passed in the same process as GeoDjango.

The live health endpoint returned HTTP 200 locally. Removing the database
container changed the response to HTTP 503 while the application remained
available. Recreating the container restored HTTP 200 and retained the same
migration row, including its original timestamp. Private HTTPS through
Tailscale Serve returned HTTP 200 with a valid
certificate. The owner confirmed the requested phone health check worked.
