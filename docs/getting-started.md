# Getting started

How to run DukaLink on your own machine, check that it works, and run the tests. Two ways are
described: **A. everything in Docker** (recommended, least setup) and **B. native development**
(Python and Node installed on your machine, only the database in Docker).

For the meaning of every setting see [`configuration.md`](configuration.md). To put it on a server
see [`deployment.md`](deployment.md).

## 1. Prerequisites

| Tool | Needed for | Notes |
|---|---|---|
| Git | getting the code | |
| Docker Engine + Docker Compose v2 (`docker compose`) | path A, and the database in path B | |
| Python 3.12 | path B (backend) | `python3 --version` |
| Node.js 22 and npm | path B (frontends) | the Docker path uses the `node:22` image |
| A phone with Expo Go (optional) | trying the shop app on a real phone | phone and computer must be on the same Wi-Fi |

Ports used on your machine: `8000` (API), `8081` (shop app), `5173` (portal), `5434` (PostgreSQL).
Stop anything already using them or change the mapping in `compose.yaml` / `compose.override.yaml`.

## 2. Path A: everything in Docker

```bash
git clone <repository-url> dukalink && cd dukalink
docker compose up --build
```

Docker Compose automatically merges `compose.yaml` (database + API) with `compose.override.yaml`
(shop app + portal), so one command starts four containers:

| Container | What it runs | Address |
|---|---|---|
| `db` | PostgreSQL 16 | `localhost:5434` (container port 5432) |
| `backend` | `migrate`, then Django `runserver` with your code mounted for live reload | http://localhost:8000 |
| `app` | `npm install`, then Expo web dev server | http://localhost:8081 |
| `portal` | `npm install`, then Vite dev server | http://localhost:5173 |

The first start is slow because both frontends run `npm install`. Later starts reuse the cached
`node_modules` volumes. Migrations run automatically on every start.

Then, once, in another terminal from the repository root:

```bash
docker compose exec backend python manage.py seed_catalog
docker compose exec backend python manage.py createsuperuser
```

- `seed_catalog` loads the shared product catalogue from `backend/apps/catalog/seed/duka_catalog.csv`
  (47 products, 87 units). It is safe to run again: nothing is deleted or duplicated.
- `createsuperuser` asks for a phone number, full name and password. Users sign in with their phone
  number (Kenyan format such as `0712345678`; it is stored as `+254712345678`). A superuser is also a
  **platform administrator**: it can verify wholesalers and edit the catalogue in the portal.

Stop with `Ctrl+C`; `docker compose down` removes the containers but keeps the database volume;
`docker compose down -v` also deletes the database.

### Using the dev stack from a phone or another computer

1. Find your computer's LAN address (for example `192.168.1.20`).
2. `export LAN_IP=192.168.1.20` before `docker compose up` (it is added to Django's allowed hosts).
3. In `compose.override.yaml` change `EXPO_PUBLIC_API_URL` and `VITE_API_URL` to
   `http://192.168.1.20:8000/api/v1`, then recreate the frontends:
   `docker compose up -d --force-recreate app portal`.
4. For Expo Go, run Expo outside Docker (path B) with `EXPO_PUBLIC_API_URL=http://192.168.1.20:8000/api/v1 npx expo start`
   and scan the QR code.

## 3. Path B: native development

### 3.1 Database

```bash
cp .env.example .env              # repository root; never commit it
docker compose up -d db           # PostgreSQL on localhost:5434
```

If you use your own PostgreSQL instead, create a database and user, then set the `POSTGRES_*`
variables in `.env` (default port 5432).

### 3.2 Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
set -a; source ../.env; set +a    # Django reads real environment variables, it does not load .env itself
python manage.py migrate
python manage.py seed_catalog
python manage.py createsuperuser
python manage.py runserver        # http://localhost:8000
```

Do **not** run `makemigrations` on a fresh clone: migrations are committed. Only run it after you
change a model, and commit the generated files.

### 3.3 Shop app (Expo)

```bash
cd apps/mobile
cp .env.example .env              # optional; the default API is http://localhost:8000/api/v1
npm install
npm run web                       # http://localhost:8081 in a browser
npm start                         # press w for the browser, or scan the QR code with Expo Go
npm run typecheck
```

If Expo reports a version mismatch run `npx expo install --fix`. The API address is read from
`EXPO_PUBLIC_API_URL` when the bundle is built or started.

### 3.4 Wholesaler portal (Vite)

```bash
cd apps/wholesaler-web
cp .env.example .env              # optional
npm install
npm run dev                       # http://localhost:5173
npm run build                     # typecheck + production build into dist/
```

The API address is read from `VITE_API_URL`.

## 4. Smoke test (15 minutes, proves the whole system works)

You need four different accounts, because the rules deliberately stop one person from ordering from
their own wholesaler or joining their own group.

1. **Platform admin**: the superuser created above. Sign in to the portal (http://localhost:5173) with it.
2. **Wholesaler**: in the portal choose *Create an account*, register, then *New business* and create
   a wholesale business. It is **pending**. Sign in as the platform admin, open `/admin`, and **verify** it.
3. **Offer**: as the wholesaler open *Offers* then *New*, pick a catalogue product, set a price,
   quantity available and optional volume tiers. Set it visible.
4. **Shop owner A**: in the shop app (http://localhost:8081) register, create a shop, then track a
   catalogue product with opening stock (*Inventory* then *Add*).
5. **Stock flows**: record a *Sale* and a *Receive* in different units (for example sell 1.5 kg of a
   product bought as a 50 kg sack). Check the stock level, *Movements* and *Alerts* screens.
6. **Ordinary order**: in *Market* open the wholesaler's offer, get a quote, place an order. As the
   wholesaler open *Orders*, confirm it (with a delivery fee), then dispatch it. As the shop open
   *Orders* and mark it received.
7. **Group buy**: register **shop owner B** with a second shop. Owner A opens *Groups* then *New* for the
   offer (target quantity, deadline, collection point, delivery fee estimate). Owner B joins. The
   organiser closes it once the target is met. As the wholesaler open *Groups* and confirm. Both shops
   get an order; the cost breakdown shows each shop's share, and the shares add up exactly.
8. **Offline**: in the browser dev tools set the network to Offline, record a sale, restore the network,
   and use *Sync now* (shop *Queue* screen). The sale appears once, even if you sync twice.

If any step fails see section 6.

## 5. Tests, lint and checks

### Backend (from `backend/`)

```bash
pytest                                  # PostgreSQL, includes the concurrency/race tests
DB_ENGINE=sqlite pytest -q              # no database needed; 15 concurrency tests skip. About 20 seconds.
ruff check .                            # lint (CI runs this)
# Do not run `ruff format .` over the whole repo: 59 files are not formatted yet and it would create a huge diff.
# Format only the files you touch: ruff format path/to/file.py
python manage.py check
python manage.py makemigrations --check --dry-run   # CI runs this; fails if a migration is missing
```

For PostgreSQL tests from your machine: start the db (`docker compose up -d db`) and export
`DJANGO_SECRET_KEY=local-test-key POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5434`. The tests set
`DJANGO_DEBUG=true` and a relaxed login throttle by default.

At the time of writing: 362 tests pass (15 skipped on SQLite) and `ruff check` is clean.

### OpenAPI schema

`python manage.py spectacular --validate` currently reports problems for inventory, suppliers, catalogue
and sync endpoints that lack declared serializers (orders and group buying are complete and guarded by
`tests/test_schema.py`). See [`next-steps.md`](next-steps.md).

### Frontends

There are **no automated frontend tests yet**. The checks available are `npm run typecheck` (shop
app), `npm run build` (portal; it typechecks first) and manual testing with section 4.

### CI

`.github/workflows/backend-ci.yml` runs on pushes to `main` and on pull requests that touch
`backend/**`: `ruff check`, `manage.py check`, the migration check, then `pytest` against PostgreSQL 16.
There is no CI for the frontends yet.

## 6. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| App shows "Cannot reach the server at http://..." | The browser cannot call the API. Check, in order: the API URL baked into the frontend (`EXPO_PUBLIC_API_URL` / `VITE_API_URL`); that the backend is running (`curl localhost:8000/api/v1/health/` returns `{"status":"ok"}`); and the browser console. A "blocked by CORS policy" message means the page's origin is missing from `CORS_ALLOWED_ORIGINS`. |
| `400 Bad Request` / `DisallowedHost` from the API | The host name you used is not in `DJANGO_ALLOWED_HOSTS`. |
| `429 Too Many Requests` on login | Auth endpoints are throttled (default `10/min`). Wait a minute or raise `AUTH_THROTTLE_RATE` in development. |
| Port already in use (5434, 8000, 8081, 5173) | Another process uses it. Stop it or change the left side of the `ports:` mapping. |
| Frontend still shows an old API address after you changed it | The address is compiled into the bundle. Restart the dev server or rebuild, then hard-refresh or clear site data, because browsers cache the JavaScript file. |
| `django.core.exceptions.ImproperlyConfigured: DJANGO_SECRET_KEY must be set` | `DJANGO_DEBUG` is off and no secret is set. Set `DJANGO_SECRET_KEY`, or `DJANGO_DEBUG=true` for development. |
| `connection refused` to PostgreSQL from the backend on your machine | Wrong port: the compose database is on **5434**, not 5432. Check `POSTGRES_PORT` and that `docker compose ps` shows `db` healthy. |
| `psycopg` / `pg_config` errors on install | Use `pip install -e ".[dev]"` (it installs `psycopg[binary]`), and Python 3.12. |
| Expo "version mismatch" warnings | `cd apps/mobile && npx expo install --fix`. |
| Wholesaler's offers do not appear for shops | The wholesaler must be **verified** by a platform admin (`/admin` in the portal) and the offer must be active and visible. |
| Django admin login fails with "CSRF verification failed" | Only happens behind HTTPS: add the API's `https://` origin to `DJANGO_CSRF_TRUSTED_ORIGINS`. |
| Django admin cannot log in over plain `http` when `DJANGO_DEBUG=false` | Cookies are marked Secure outside debug mode, so the admin needs HTTPS. Use debug mode locally. |
