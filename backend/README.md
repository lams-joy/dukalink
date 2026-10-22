# DukaLink backend

Django + DRF API. Built so far: Phase 0 foundation, accounts, shops/memberships, shared
catalogue with unit conversions, and the inventory ledger (opening stock, purchase receipts,
sales, adjustments, reversals) with idempotent writes.

## Run it locally

```bash
cp ../.env.example ../.env            # edit if needed
docker compose up -d db               # from the repo root; PostgreSQL on :5432

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
set -a; source ../.env; set +a        # Django reads real environment variables only

python manage.py makemigrations accounts shops catalog inventory sync   # FIRST TIME ONLY
python manage.py migrate
python manage.py seed_demo_catalog
python manage.py createsuperuser      # phone number + full name + password
python manage.py runserver
```

* API base: `http://localhost:8000/api/v1/` · OpenAPI docs: `http://localhost:8000/api/docs/`
* Admin: `http://localhost:8000/admin/`

`makemigrations` must be run (and the migration files committed) before the first `migrate`,
so the custom user model is part of the initial migration. Do not skip this.

## Tests

```bash
pytest                                  # against PostgreSQL (includes the concurrency test)
DB_ENGINE=sqlite pytest                 # quick run; the concurrency test is skipped
ruff check --fix . && ruff format .     # run once, then keep clean
```

## Conventions (Phase 0)

| Topic | Rule |
|---|---|
| Errors | `{"error": {"code", "message", "details", "request_id"}}` on every handled error; 500s return the same envelope with no internals |
| Request IDs | `X-Request-ID` accepted/generated on every request and echoed on the response |
| Pagination | `{count, next, previous, results}`, `page_size` (default 50, max 200) |
| Money / quantities | `Decimal`, serialised as strings. Quantities: 6 decimal places in **base units**; money: 2 |
| Timestamps | ISO 8601, UTC |
| Idempotency | Write endpoints require an `idempotency_key` (UUID). Same key + same payload → original response (`Idempotent-Replayed: true`); same key + other payload → `409 idempotency_conflict`; failed attempts are not cached and can be retried |
| Not a member of a shop | `404` (existence is not revealed); member without the needed role → `403` |

## Roles (provisional)

| Action | owner | manager | staff |
|---|---|---|---|
| Read shop, inventory, movements | ✔ | ✔ | ✔ |
| Record purchase receipts and sales | ✔ | ✔ | ✔ |
| Track a product, edit settings, opening stock, adjustments, edit shop | ✔ | ✔ | ✖ |
| Add members | ✔ | ✖ | ✖ |

## Provisional choices to confirm (these are open items in `decisions.md`)

* **Auth:** JWT via SimpleJWT (15-minute access, 30-day rotating refresh), login by phone number + password.
* **Negative stock:** rejected with `409 insufficient_stock` (`ALLOW_NEGATIVE_STOCK=false`).
* **Currency:** KES by default; one currency per deployment for now.
* **Adding members:** only people who already have an account can be added.

## Not built yet

Stock counts, low-stock alert endpoint, reports, batch/expiry, the `/shops/{id}/sync/` batch
endpoint, a reversal endpoint (the service exists), custom shop products, onboarding-complete,
suppliers, orders, group buying, notifications, audit log.
