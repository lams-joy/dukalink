# Configuration and files needed to run

Everything environment-specific comes from environment variables. This page lists every variable,
which file holds it, what is and is not in Git, and what is generated.

## 1. Backend environment variables

Read in `backend/config/settings.py`. Django does **not** load `.env` files by itself: in Docker
Compose they arrive through `environment:` / `env_file:`; natively use
`set -a; source .env; set +a` before starting Django.

| Variable | Default | Required? | Purpose |
|---|---|---|---|
| `DJANGO_DEBUG` | `false` | no | `true` only for development. When off, `DJANGO_SECRET_KEY` is mandatory, cookies are Secure and the proxy header `X-Forwarded-Proto` is trusted. |
| `DJANGO_SECRET_KEY` | none (dev fallback only in debug) | **yes when debug is off** | Signs sessions and tokens. Generate one: `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`. Changing it signs everyone out. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` in debug, empty otherwise | **yes in production** | Comma-separated host names the API answers to. The name must match the `Host` header the proxy forwards. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | for `/admin/` behind HTTPS | Comma-separated full origins, e.g. `https://api.example.com`. The JSON API uses bearer tokens and does not need it. |
| `CORS_ALLOWED_ORIGINS` | the four localhost dev origins in debug, empty otherwise | **yes in production** | Comma-separated origins of the shop app and portal, e.g. `https://app.example.com,https://wholesale.example.com`. Without it browsers block every call. |
| `DB_ENGINE` | `postgres` | no | `sqlite` for quick local test runs only (no row locking). |
| `POSTGRES_DB` | `dukalink` | no | Database name. |
| `POSTGRES_USER` | `dukalink` | no | Database user. |
| `POSTGRES_PASSWORD` | `dukalink` | **change in production** | Database password. |
| `POSTGRES_HOST` | `localhost` | no | `db` inside Docker Compose. |
| `POSTGRES_PORT` | `5432` | no | The development compose database is published on **5434**. |
| `AUTH_THROTTLE_RATE` | `10/min` | no | Rate limit for register/login/refresh. |
| `DEFAULT_PHONE_COUNTRY_CODE` | `254` | no | Used to normalise numbers such as `0712...`. |
| `DEFAULT_CURRENCY` | `KES` | no | One currency per deployment for now. |
| `SUPPLIER_VERIFICATION_REQUIRED` | `true` | no | Wholesalers must be verified by a platform admin before shops see their offers. |
| `ALLOW_NEGATIVE_STOCK` | `false` | no | `false` rejects a sale that would take stock below zero (`409 insufficient_stock`). Offline sales that would do so come back as a `conflict`. |
| `LOG_LEVEL` | `INFO` | no | Python logging level (logs go to the console). |

Fixed in code (not environment variables): JWT lifetimes (access 15 minutes, refresh 30 days, rotating),
quantity precision (6 decimals) and money precision (2 decimals), time zone UTC.

## 2. Frontend variables (compile-time)

These are **baked into the JavaScript bundle when it is built or started**. Changing them later
requires a rebuild, and browsers may keep the old file cached.

| Variable | Used by | Default | Meaning |
|---|---|---|---|
| `EXPO_PUBLIC_API_URL` | `apps/mobile` | `http://localhost:8000/api/v1` | API base URL **including `/api/v1`**. |
| `VITE_API_URL` | `apps/wholesaler-web` | `http://localhost:8000/api/v1` | Same, for the portal. |
| `PUBLIC_API_URL` | `deploy/.env` | none | Single value that `deploy/build-web.sh` passes to both of the above. Django ignores it. |

Examples: `http://192.168.1.20:8000/api/v1` for a phone on your Wi-Fi, `https://api.example.com/api/v1`
in production. Never leave a port such as `:3007` in a public HTTPS address unless that port is
actually reachable from the user's network.

## 3. Which files you need

### Needed to run locally (all in Git)

| File or folder | Why |
|---|---|
| `compose.yaml` | Development PostgreSQL + Django (`runserver`, source mounted for reload). |
| `compose.override.yaml` | Adds the Expo web server and the Vite server. Docker Compose loads it automatically. |
| `backend/` (`manage.py`, `config/`, `apps/`, `pyproject.toml`, `Dockerfile`) | The API. All migrations are committed under each `apps/*/migrations/`. |
| `backend/apps/catalog/seed/duka_catalog.csv` | The product catalogue loaded by `seed_catalog`. Edit it in any spreadsheet app. |
| `apps/mobile/` (`app/`, `src/`, `package.json`, `package-lock.json`, `app.json`, `tsconfig.json`) | Shop app. |
| `apps/wholesaler-web/` (`src/`, `index.html`, `package.json`, `package-lock.json`, `vite.config.ts`, `tsconfig.json`) | Portal. |
| `.env.example` | Template for a root `.env` (only needed for native development). |

For the Docker path you do **not** need a `.env` file: the compose files carry safe development values
(`DJANGO_DEBUG=true`, a throw-away secret key, the `dukalink` database password).

### Needed to deploy (in Git, under `deploy/`)

| File | Purpose |
|---|---|
| `make-env.sh` | Generates `deploy/.env` (with fresh random secrets) and `deploy/nginx.conf` for your domain. Safe to re-run: existing secrets are kept. |
| `build-web.sh` | Builds the shop app and portal against `PUBLIC_API_URL` into `deploy/www/`. |
| `compose.yaml` | Production-style stack: `db`, `backend` (gunicorn), `web` (nginx, published on host port 3007). |
| `push.sh` | Uploads backend + deploy files to a server over SSH/rsync and starts the stack. |
| `backup.sh` | Dumps the database to `~/backups/`, keeping the last 14. |

### Not in Git (created on your machine; ignored on purpose)

| File | Created by | Notes |
|---|---|---|
| `.env` (repo root) | you, from `.env.example` | Local native development. |
| `deploy/.env` | `deploy/make-env.sh` | Production secrets. Mode `600`. Back it up somewhere safe. |
| `deploy/nginx.conf` | `deploy/make-env.sh` | Host-name routing for nginx. |
| `deploy/www/` | `deploy/build-web.sh` | The built shop app (`www/app`) and portal (`www/wholesale`). |
| `node_modules/`, `dist/`, `.expo/` | npm / Expo | |
| `backend/.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `*.egg-info/`, `db.sqlite3`, `staticfiles/` | Python tooling | |
| Docker volumes `dukalink_pg`, `app_node_modules`, `portal_node_modules` (dev); `pgdata`, `static` (production) | Docker | `pgdata` holds the **only copy of the production data**: back it up. |

## 4. Ports at a glance

| Port | Used by | Context |
|---|---|---|
| 8000 | Django | development; inside the production network (not published) |
| 5434 | PostgreSQL | development compose database as seen from your machine |
| 8081 | Expo web | development |
| 5173 | Vite | development |
| 3007 | nginx container | production-style compose, the one published port |

## 5. Secrets checklist

- `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` must be random and unique per environment.
- The development password `dukalink` and key `dev-only-not-a-secret` must never be used on a server.
- Rotate anything that was ever committed. An early commit named "Stop tracking .env" suggests a `.env`
  was committed once; check with `git log --all -p -- .env` and treat any real value found there as public.
- Create the first platform admin with `createsuperuser` on the target environment; do not copy a
  development database to production.
