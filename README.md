# DukaLink

Mobile-first inventory and wholesale-ordering platform for Kenyan duka (small shop) owners.
Shops track stock and sales (even offline), restock from verified wholesalers, and pool orders with
nearby shops through group buying. Wholesalers manage offers, orders and group buys in a web portal.

This repository contains everything needed to run the product locally and to deploy it.

## What is in the repository

| Path | What it is | Tech |
|---|---|---|
| `backend/` | The API, admin site and all business rules | Python 3.12, Django 5.2, Django REST Framework, PostgreSQL 16 |
| `apps/mobile/` | Shop owner app. One codebase for Android (Expo Go / builds) and the browser | React Native, Expo SDK 57, Expo Router, TypeScript |
| `apps/wholesaler-web/` | Wholesaler portal and platform-admin screens | React 19, Vite 7, React Router, TypeScript |
| `deploy/` | Scripts and compose file for a single-server deployment | Docker Compose, nginx, bash |
| `compose.yaml`, `compose.override.yaml` | Local development stack (database, API, both web apps) | Docker Compose |
| `docs/` | Product, architecture, API, decisions and handover documentation | Markdown |
| `.github/workflows/backend-ci.yml` | CI: lint, Django checks, migration check, tests | GitHub Actions |

## Quick start (about 10 minutes, needs only Git and Docker)

```bash
git clone <repository-url> dukalink && cd dukalink
docker compose up --build          # database + API + shop app + wholesaler portal
```

Wait until the logs show the Django server and both web servers listening (the first run downloads
npm packages, which takes a few minutes). In a second terminal:

```bash
docker compose exec backend python manage.py seed_catalog          # load the product catalogue (47 products)
docker compose exec backend python manage.py createsuperuser       # platform admin: phone number, full name, password
```

| What | Where |
|---|---|
| Shop owner app (browser) | http://localhost:8081 |
| Wholesaler portal | http://localhost:5173 |
| API | http://localhost:8000/api/v1/ (health check: `/api/v1/health/`) |
| Interactive API docs (Swagger) | http://localhost:8000/api/docs/ |
| Django admin | http://localhost:8000/admin/ |

No `.env` file is needed for this path. Full instructions, including running without Docker, testing on a
phone and a 15-minute smoke test, are in [`docs/getting-started.md`](docs/getting-started.md).

## Where to read next

| If you want to... | Read |
|---|---|
| Run it, test it, troubleshoot it | [`docs/getting-started.md`](docs/getting-started.md) |
| Know every setting and which files are needed | [`docs/configuration.md`](docs/configuration.md) |
| See exactly what already works | [`docs/features.md`](docs/features.md) |
| Know what to build or fix next | [`docs/next-steps.md`](docs/next-steps.md) |
| Deploy to a server and operate it | [`docs/deployment.md`](docs/deployment.md) |
| Understand why things work the way they do | [`docs/decisions.md`](docs/decisions.md), [`docs/documentation.md`](docs/documentation.md), [`docs/database.md`](docs/database.md) |
| Look up endpoints | [`docs/api.md`](docs/api.md) and the live `/api/docs/` page |
| Use one-page guides per project | [`backend/README.md`](backend/README.md), [`apps/mobile/README.md`](apps/mobile/README.md), [`apps/wholesaler-web/README.md`](apps/wholesaler-web/README.md) |

The full index is [`docs/README.md`](docs/README.md).

## Everyday commands

```bash
# Backend (from backend/, with a virtualenv and the database running; see getting-started.md)
pytest                                  # full test suite on PostgreSQL
DB_ENGINE=sqlite pytest -q              # quick run, no database needed (15 concurrency tests are skipped)
ruff check .                            # lint (CI enforces this)
python manage.py makemigrations --check --dry-run   # fails if a model change has no migration

# Shop app (from apps/mobile/)
npm run typecheck

# Wholesaler portal (from apps/wholesaler-web/)
npm run build                           # typecheck + production build
```

## Ground rules

- Never commit secrets. `.env` files, `deploy/www/` and `deploy/nginx.conf` are git-ignored on purpose.
- Every model change needs a committed migration and tests. CI enforces both.
- All write endpoints are idempotent (they need an `idempotency_key`). Keep it that way.
- Money and quantities are decimals serialised as strings, never floats. Quantities are stored in base units.
- Record decisions in [`docs/decisions.md`](docs/decisions.md) and keep [`docs/features.md`](docs/features.md) in step with the code.
