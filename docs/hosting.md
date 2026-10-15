# Hosting

SporaMeteo runs as its own Dokku app on the Hetzner VPS that also hosts book
corners. The setup copies the book corners method from its `HOSTING.md` and
`DEPLOYMENT.md`. The VPS has 2 ARM CPUs, 3.7 GB of memory and 25 GB of free
disk. Before this setup it had about 1.9 GB of free memory and no swap.

Every SporaMeteo resource on the VPS has its own name: the app `sporameteo`,
the database service `sporameteo-db` and the storage folder
`/var/lib/dokku/data/storage/sporameteo`. No step changes a book corners app,
service, folder or Cloudflare zone.

Run the server commands as the `deploy` user over
`ssh deploy@vps.bookcorners.org` until `vps.sporameteo.com` resolves. After
each step, check that book corners still answers:

```sh
curl -s -o /dev/null -w "%{http_code}\n" https://www.bookcorners.org/health/
```

The answer must be `200`.

## Swap

The VPS has no swap, so a memory spike in either app ends with the kernel
killing a process. The owner approved a 2 GB swap file. A low `swappiness`
keeps the kernel from moving memory to disk while free memory remains.

```sh
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab
echo "vm.swappiness=10" | sudo tee /etc/sysctl.d/99-swappiness.conf
sudo sysctl --system
free -h
```

`free -h` must show `Swap: 2.0Gi`. Run it again after the next reboot to check
that the line in `/etc/fstab` works.

## App and database

The database uses the same PostGIS image and tag as `book-corners-db`, so the
VPS keeps only one copy of the image. Read the tag from the existing service
first:

```sh
sudo dokku postgres:info book-corners-db --version
```

Pass that value to `--image-version`. In October 2026 it was
`17-3.6-bookworm`. The `deploy` user may run only `dokku` without a password,
and `sudo` drops the `POSTGRES_IMAGE` variables that the book corners docs use,
so the flags replace them. The swap and folder steps need the sudo password.

```sh
sudo dokku apps:create sporameteo
sudo dokku postgres:create sporameteo-db \
  --image imresamu/postgis --image-version "<tag of book-corners-db>"
sudo dokku postgres:link sporameteo-db sporameteo
sudo dokku postgres:info sporameteo-db
sudo dokku postgres:info book-corners-db
```

The two `postgres:info` outputs must show the same version and two different
container IDs. The link sets `DATABASE_URL`, which `config/settings.py` reads
before the `SPORAMETEO_DB_*` variables.

## Memory limits

The measured peaks are 142 MB for the estimate step and 160 MB for the map
cache warm-up. Both run in the `worker` process. The `web` process runs two
gunicorn workers, and each one loads Django and GDAL.

| Process | Limit | Reason |
|---|---|---|
| `web` | 512 MB | Two gunicorn workers and the gunicorn main process. |
| `worker` | 384 MB | More than twice the 160 MB warm-up peak. |

```sh
sudo dokku resource:limit --memory 512m --process-type web sporameteo
sudo dokku resource:limit --memory 384m --process-type worker sporameteo
sudo dokku resource:report sporameteo
```

The Dokku docs describe limits per process type and do not say whether the
`app.json` cron tasks get them. After the first night, check the real use with
`sudo docker stats --no-stream` and update this table.

## JRC tree files

The app reads 37 JRC host tree files at runtime. They stay on the host so a
deploy does not remove them. The container runs as root, so the folder needs
no change of owner. Issue #88 copies the files into it.

```sh
sudo mkdir -p /var/lib/dokku/data/storage/sporameteo/jrc_host_trees
sudo dokku storage:mount sporameteo \
  /var/lib/dokku/data/storage/sporameteo/jrc_host_trees:/app/data/jrc_host_trees
```

## Environment

Generate the secret key on the laptop:

```sh
uv run python -c "import secrets; print(secrets.token_urlsafe(50))"
```

```sh
sudo dokku config:set --no-restart sporameteo \
  SPORAMETEO_DJANGO_SECRET_KEY="<generated key>" \
  SPORAMETEO_ALLOWED_HOSTS="www.sporameteo.com,sporameteo.com" \
  SPORAMETEO_CSRF_TRUSTED_ORIGINS="https://www.sporameteo.com,https://sporameteo.com" \
  SPORAMETEO_SECURE_SSL_REDIRECT="true" \
  SPORAMETEO_SESSION_COOKIE_SECURE="true" \
  SPORAMETEO_CSRF_COOKIE_SECURE="true" \
  SPORAMETEO_SECURE_HSTS_SECONDS="31536000" \
  SPORAMETEO_FOREST_BUILD_VERSION="tuscany-forest-italy-forest-copernicus-2018-v1-56" \
  SPORAMETEO_TERRAIN_BUILD_VERSION="tuscany-terrain-italy-terrain-glo30-2021-v2-56" \
  SPORAMETEO_JRC_DIRECTORY="/app/data/jrc_host_trees" \
  RESEND_API_KEY="<Resend key>" \
  NIGHTLY_ALERT_EMAIL="<owner address>"
```

The two apps share one Resend account. The app sends from
`noreply@sporameteo.com`, so `sporameteo.com` must be a verified domain in
Resend. The build versions match the Tuscany dump in `docs/hosting_data.md`.
`--no-restart` avoids errors before the first deploy.

## Domain and HTTPS

Cloudflare holds the `sporameteo.com` zone. It needs three A records, all
pointing at the VPS address:

| Record | Proxy |
|---|---|
| `sporameteo.com` | Proxied |
| `www.sporameteo.com` | Proxied |
| `vps.sporameteo.com` | DNS only |

`vps.sporameteo.com` skips Cloudflare, so SSH and `git push` reach the VPS.
Add a Cloudflare redirect rule that sends `sporameteo.com/*` to
`https://www.sporameteo.com/${1}` with status 301.

```sh
sudo dokku domains:set sporameteo www.sporameteo.com sporameteo.com
```

After the first deploy, map port 80 and start the worker. The `Dockerfile`
exposes port 8000, so without `ports:set` nginx listens on 8000 instead of 80.
Dokku starts only the `web` process unless told otherwise.

```sh
sudo dokku ports:set sporameteo http:80:8000
sudo dokku ps:scale sporameteo worker=1
```

Then enable HTTPS with the same notification email as book corners:

```sh
sudo dokku letsencrypt:set sporameteo email \
  "$(sudo dokku letsencrypt:report book-corners --letsencrypt-email)"
sudo dokku letsencrypt:enable sporameteo
```

The Let's Encrypt plugin and its renewal cron job already exist for book
corners. `letsencrypt:enable` adds the `https:443:8000` mapping. Then set the
Cloudflare SSL mode for the zone to Full Strict, and turn on Always Use HTTPS.

## Deploys from CI

The `deploy` job in `.github/workflows/ci.yml` runs after all checks pass on a
push to `master`. It asks Dokku which commit it runs and pushes only when one
of these paths changed since that commit: `apps/`, `src/`, `assets/`,
`pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`, the CSS build
configs, the map library package files under `tools/map_checks/`, `Dockerfile`,
`Procfile`, `app.json` and the workflow itself. A push that touches only
`reports/` or `docs/` does not deploy.

The job needs one repository secret, `DOKKU_SSH_PRIVATE_KEY`. Create a key pair
for it and give the public key to Dokku:

```sh
ssh-keygen -t ed25519 -N "" -f ~/.ssh/sporameteo_deploy
cat ~/.ssh/sporameteo_deploy.pub | ssh deploy@vps.sporameteo.com \
  "sudo dokku ssh-keys:add sporameteo-ci"
gh secret set DOKKU_SSH_PRIVATE_KEY < ~/.ssh/sporameteo_deploy
```

For a manual deploy from the laptop:

```sh
git remote add dokku dokku@vps.sporameteo.com:sporameteo
git push dokku master
```

## Checks

```sh
curl -s -o /dev/null -w "%{http_code}\n" https://www.sporameteo.com/health/
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" https://sporameteo.com/
curl -s -o /dev/null -w "%{http_code}\n" https://www.bookcorners.org/health/
```

The first and last must print `200`. The second must print `301` and
`https://www.sporameteo.com/`.

## Setup log

| Step | Date | Result |
|---|---|---|
| Swap | 15 October 2026 | 2 GB swap file in `/etc/fstab`, `swappiness` 10. |
| App and database | 15 October 2026 | `sporameteo-db` and `book-corners-db` both run `imresamu/postgis:17-3.6-bookworm`, in different containers. |
| Memory limits | 15 October 2026 | `web` 512 MB, `worker` 384 MB. |
| JRC storage | 15 October 2026 | Folder mounted at `/app/data/jrc_host_trees`, still empty. |
| Environment | 15 October 2026 | All variables set. `RESEND_API_KEY` and `NIGHTLY_ALERT_EMAIL` copied from the book corners `RESEND_API_KEY` and `ADMIN_NOTIFICATION_EMAIL`. `sporameteo.com` verified in Resend. Domains set. |
| DNS and redirect | 15 October 2026 | Wildcard redirect rule `https://sporameteo.com/*` to `https://www.sporameteo.com/${1}`, 301. The path and query string carry over. |
| First deploy | 15 October 2026 | `f953ade` pushed from the laptop. Migrations and both health checks passed. Port 80 mapped, one worker started. |
| Let's Encrypt | 15 October 2026 | Certificate valid until 13 January 2027. The VPS answers `/health/` with 200 and a valid certificate for both names. |
| Cloudflare Full Strict | 15 October 2026 | Set by the owner. `/health/` answers 200 through Cloudflare, and plain `http` redirects to `https`. |
| CI deploy key | 15 October 2026 | Dokku key `sporameteo-ci`, private key in the `DOKKU_SSH_PRIVATE_KEY` secret. `git ls-remote` with it returns the deployed commit. |
