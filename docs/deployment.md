# Deployment and operations

How to run DukaLink on a server, put it on the internet, and keep it healthy. The scripts in
`deploy/` are written for **one Linux server running Docker**, with an existing "front door"
(Cloudflare Tunnel, Caddy, or router port forwarding) that provides HTTPS. This is a pilot-grade
setup; see [`next-steps.md`](next-steps.md) for what to harden before many users depend on it.

## 1. How the pieces fit

```
Browser / phone
      |  HTTPS  (your front door: Cloudflare Tunnel, Caddy, ...)
      v
server:3007  ->  nginx container ("web")  --- picks the site by the Host header --->
                    api.<domain>        -> proxy to  backend:8000  (gunicorn + Django)
                    app.<domain>        -> static files  deploy/www/app        (shop app)
                    wholesale.<domain>  -> static files  deploy/www/wholesale  (portal)
                    anything else       -> connection closed (444)
backend  <->  db (PostgreSQL 16, volume "pgdata")
```

- Only port **3007** is published by `deploy/compose.yaml`. The database and gunicorn are reachable only inside Docker.
- nginx chooses the site from the `Host` header, so **the host name that reaches nginx must be one of
  `api.<domain>`, `app.<domain>`, `wholesale.<domain>`** (or you must rewrite it, see section 5).
- On every start the backend runs `migrate` and `collectstatic`, then gunicorn (2 workers).
- The frontends are static files built **ahead of time** with the API address compiled in.

## 2. One-time server preparation

```bash
# on the server
sudo apt install docker.io docker-compose-v2 rsync        # or follow Docker's official install guide
sudo usermod -aG docker $USER                             # log out and in again
sudo mkdir -p /srv/dukalink && sudo chown $USER /srv/dukalink
```

Your deploy machine (laptop) needs: Git, Node 22 + npm (to build the frontends), Python 3 (to generate
secrets), `rsync` and `ssh` access to the server.

## 3. Deploy

Run from the repository root on your **deploy machine**:

```bash
cd deploy
./make-env.sh example.com          # writes deploy/.env and deploy/nginx.conf for api./app./wholesale.example.com
./build-web.sh                     # builds both web apps against PUBLIC_API_URL into deploy/www/
./push.sh user@SERVER              # rsync to /srv/dukalink and `docker compose up -d --build`
```

Then, once, on the **server**:

```bash
cd /srv/dukalink/deploy
docker compose exec backend python manage.py createsuperuser     # platform admin
docker compose exec backend python manage.py seed_catalog        # product catalogue
curl -s http://localhost:3007/api/v1/health/ -H "Host: api.example.com"    # -> {"status":"ok"}
```

What each script does:

| Script | Details |
|---|---|
| `make-env.sh domain [lan]` | Public mode (default) writes `https://` addresses. `lan` mode writes `http://...:3007` addresses for testing on a home network. Keeps existing secrets when re-run, so the database password never changes under you. Writes `PUBLIC_API_URL`, `DJANGO_DEBUG=false`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `POSTGRES_*`. |
| `build-web.sh` | Reads `PUBLIC_API_URL` from `deploy/.env`, runs `expo export --platform web` and `vite build`, copies results to `deploy/www/app` and `deploy/www/wholesale`. |
| `push.sh user@host [dir]` | Refuses to run unless `deploy/www/` and `deploy/.env` exist. `rsync --delete`s `backend/`, copies `deploy/` (including `.env` and `nginx.conf`) and `deploy/www/`, then `docker compose up -d --build`. |
| `backup.sh` | Run on the server. Gzipped `pg_dump` into `~/backups/dukalink-YYYY-MM-DD.sql.gz`, keeps the newest 14. |

> **Important:** `push.sh` overwrites the server's `deploy/.env` and `deploy/nginx.conf` with the copies on
> your deploy machine. Always change configuration **on the deploy machine** and push, or your server-only edits will
> be lost on the next push. Keep a copy of `deploy/.env` in a password manager: it holds the database password and
> the Django secret key, and it is not in Git.

## 4. Updating an existing deployment

```bash
git pull
cd deploy
./build-web.sh        # only if frontend code or PUBLIC_API_URL changed
./push.sh user@SERVER
```

Migrations run automatically when the backend container starts. After recreating the backend,
restart nginx too, because nginx resolves the `backend` address once at start-up and keeps using
the old container's address otherwise (symptom: `502` or an empty reply right after a deploy):

```bash
cd /srv/dukalink/deploy && docker compose restart web
# or recreate both together
docker compose up -d --build --force-recreate backend web
```

Because built filenames are hashed, a normal rebuild gives browsers a new file name and they pick it up
automatically. If you ever patch built files in place (not recommended), browsers will keep the old copy until
site data is cleared.

## 5. The front door (HTTPS)

`deploy/compose.yaml` publishes plain HTTP on `server:3007`. You must put HTTPS in front of it.

### Option A: Cloudflare Tunnel (how the first pilot server was exposed)

Cloudflare only proxies certain ports. **Port 3007 is not one of them**, so a public address such as
`http://api.example.com:3007` simply hangs. Use hostnames without a port and point the tunnel at the local port.

In the tunnel's `config.yml` (usually `/etc/cloudflared/config.yml`), above the final catch-all:

```yaml
ingress:
  # ... your other services ...
  - hostname: api.example.com
    service: http://localhost:3007
  - hostname: app.example.com
    service: http://localhost:3007
  - hostname: wholesale.example.com
    service: http://localhost:3007
  - service: http_status:404
```

Create the DNS records (one per name) and restart:

```bash
cloudflared tunnel route dns <TUNNEL-ID> api.example.com      # repeat for app. and wholesale.
cloudflared tunnel --config /etc/cloudflared/config.yml ingress validate
sudo systemctl restart cloudflared
curl -s https://api.example.com/api/v1/health/
```

**Host names already taken?** The tunnel matches rules by hostname and the first match wins. If
`api.example.com` already serves another project, give DukaLink different public names and rewrite the Host header
so nginx still recognises them:

```yaml
  - hostname: dukalink-api.example.com
    service: http://localhost:3007
    originRequest:
      httpHostHeader: api.example.com        # what nginx's server_name expects
  - hostname: dukalink-app.example.com
    service: http://localhost:3007
    originRequest:
      httpHostHeader: app.example.com
  - hostname: dukalink-wholesale.example.com
    service: http://localhost:3007
    originRequest:
      httpHostHeader: wholesale.example.com
```

In this layout the settings must use the **public** names where the browser is involved and the **rewritten** name
where Django sees the request:

| Setting | Value |
|---|---|
| `PUBLIC_API_URL` (baked into the apps) | `https://dukalink-api.example.com/api/v1` |
| `DJANGO_ALLOWED_HOSTS` | `api.example.com,dukalink-api.example.com` (the rewritten Host plus the public name) |
| `CORS_ALLOWED_ORIGINS` | `https://dukalink-app.example.com,https://dukalink-wholesale.example.com` (the browsers' real origins) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://dukalink-api.example.com` |

Edit `deploy/.env` by hand for this (`make-env.sh` writes the simple `api./app./wholesale.` layout), rebuild the apps with
`./build-web.sh`, push, and **recreate the backend** (`docker compose up -d --force-recreate backend web`), since a
plain `restart` does not re-read `.env`.

### Option B: Caddy or another reverse proxy

Terminate TLS for the three host names and proxy to `server:3007`, passing the original `Host` and
`X-Forwarded-Proto: https`. Django trusts `X-Forwarded-Proto` when `DJANGO_DEBUG=false`.

### Option C: router port forwarding

Possible but not recommended: you then need your own certificates and the three DNS records must
point to your public IP.

### Home-network test mode

`./make-env.sh example.com lan` writes `http://api.example.com:3007` style addresses. Add the names to the
`/etc/hosts` of each test machine (`<server-ip> api.example.com app.example.com wholesale.example.com`) and remove them
afterwards: once they are removed the names resolve publicly again and the `:3007` address stops working. Django admin
logins do not work over plain HTTP with `DJANGO_DEBUG=false` because cookies are marked Secure.

## 6. Verifying a deployment

```bash
# 1. API through the whole chain
curl -s https://api.example.com/api/v1/health/                                  # {"status":"ok"}

# 2. Frontends are served, and contain the right API address
curl -s https://app.example.com/ | head -5
curl -s https://app.example.com/ | grep -o '_expo/static/js/web/[^"]*\.js'      # then grep that file for your API URL
grep -rhoE "https?://[a-z0-9.-]+(:[0-9]+)?/api/v1" deploy/www | sort | uniq -c   # on the deploy machine: one address only

# 3. CORS: must return access-control-allow-origin with the app's origin
curl -s -i -X OPTIONS https://api.example.com/api/v1/health/ \
  -H "Origin: https://app.example.com" -H "Access-Control-Request-Method: POST" | grep -i access-control

# 4. Admin: open https://api.example.com/admin/ and sign in with the superuser
```

## 7. Operating it

| Task | Command (on the server, in `/srv/dukalink/deploy`) |
|---|---|
| Status | `docker compose ps` |
| Logs | `docker compose logs --tail 100 backend` (also `web`, `db`); add `-f` to follow |
| Restart the API | `docker compose restart backend && docker compose restart web` |
| Django shell | `docker compose exec backend python manage.py shell` |
| Create another admin | `docker compose exec backend python manage.py createsuperuser` (interactive; when running it over SSH use `ssh -t user@host '...'`) |
| Reload the catalogue | edit `backend/apps/catalog/seed/duka_catalog.csv`, push, then `docker compose exec backend python manage.py seed_catalog` |
| Settle expired group buys | `docker compose exec -T backend python manage.py close_expired_groups` |

### Scheduled jobs (add with `crontab -e` on the server)

```cron
# every 5 minutes: close or fail group buys past their deadline
*/5 * * * * cd /srv/dukalink/deploy && docker compose exec -T backend python manage.py close_expired_groups >> $HOME/dukalink-cron.log 2>&1
# every night: database backup (keeps 14 files in ~/backups)
15 2 * * * /srv/dukalink/deploy/backup.sh >> $HOME/dukalink-backup.log 2>&1
```

Group deadlines are also settled lazily when a group is read, so the cron job is a safety net, not a hard dependency.

### Backups and restore

The database volume `pgdata` is the only copy of the production data. Copy `~/backups/` off the server regularly
(another machine or cloud storage). **A restore has not been rehearsed yet**; try it on a spare machine before you need it:

```bash
cd /srv/dukalink/deploy
docker compose stop backend
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"'
gunzip -c ~/backups/dukalink-YYYY-MM-DD.sql.gz | docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose start backend
```

### Secrets

- To rotate `DJANGO_SECRET_KEY`: edit `deploy/.env` on the deploy machine, push, recreate the backend. All users are signed out.
- Do not change `POSTGRES_PASSWORD` in `.env` alone: the existing database keeps the old password. Change it in PostgreSQL first
  (`ALTER USER dukalink PASSWORD '...'`) and in `.env` afterwards.

## 8. Problems met during the first deployment (and the fix)

| Symptom | Real cause | Fix |
|---|---|---|
| Requests to `http://api.example.com:3007/...` hang, then time out | Cloudflare does not proxy port 3007 | Use the tunnel hostnames without a port (section 5A) |
| `404 page not found` (plain text) from the public name | The tunnel has no rule for that host, or the rule points at another service's port | Fix the tunnel `ingress`; check with `ss -ltnp \| grep <port>` what is listening |
| `curl http://<server-ip>:3007/...` returns nothing / `000` | nginx ignores unknown hosts (`return 444`) | Send the right header: `curl -H "Host: api.example.com" ...` |
| `502` or empty reply right after redeploying the backend | nginx still uses the old backend container's address | `docker compose restart web` |
| Login page says "Cannot reach the server at http://...:3007/..." | The apps were built with the old address baked in | Fix `PUBLIC_API_URL`, `./build-web.sh`, `./push.sh`, then hard-refresh or clear site data in every browser profile that used it |
| Browser console shows a CORS error although the API works with `curl` | `CORS_ALLOWED_ORIGINS` is empty or missing the page's origin (it defaults to empty when debug is off) | Set it, recreate the backend |
| "CSRF verification failed" on `/admin/` login | `DJANGO_CSRF_TRUSTED_ORIGINS` lacks the API's `https://` origin | Set it, recreate the backend |
| cloudflared logs repeat `datagram manager` / `accept stream` errors | The QUIC connection to Cloudflare is unstable on some networks | Add `protocol: http2` to the cloudflared `config.yml` and restart it |
| Edits made directly on the server vanish | `push.sh` overwrote them | Make changes on the deploy machine |
