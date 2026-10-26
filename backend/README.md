# DukaLink backend

Django + DRF API. Built so far: Phase 0 foundation, accounts, shops/memberships, shared
catalogue with unit conversions, the inventory ledger (opening stock, purchase receipts,
sales, adjustments, reversals, stock counts) with idempotent writes and offline sync, wholesaler
suppliers and offers, ordinary orders, group buying (commitments, lifecycle, supplier
confirmation, per-shop orders and cost breakdown) and the audit log.

Interactive API docs are served at `/api/docs/` and the OpenAPI schema at `/api/schema/` when
the server is running.

## Run it locally

```bash
cp ../.env.example ../.env            # edit if needed
docker compose up -d db               # from the repo root; PostgreSQL on localhost:5434 (the .env.example default)

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
set -a; source ../.env; set +a        # Django reads real environment variables only

python manage.py migrate              # migrations are committed; do not run makemigrations unless you change a model
python manage.py seed_catalog         # loads the bundled duka product list (idempotent)
python manage.py createsuperuser      # phone number + full name + password
python manage.py runserver
```

* API base: `http://localhost:8000/api/v1/` · OpenAPI docs: `http://localhost:8000/api/docs/`
* Admin: `http://localhost:8000/admin/`

Migrations for every app are committed. CI fails if a model change has no migration, so after
editing a model run `python manage.py makemigrations` and commit the result.

## Tests

```bash
pytest                                  # against PostgreSQL (includes the concurrency test)
DB_ENGINE=sqlite pytest                 # quick run; the concurrency test is skipped
ruff check .                            # CI enforces this
# ruff format is not enforced yet (many files are unformatted); format only files you touch
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

## Offline sync

`POST /api/v1/shops/{shop_id}/sync/` takes queued operations (oldest first), max 100 per batch:

```json
{"operations": [{"operation_id": "<uuid>", "operation_type": "sale", "payload": {"items": []}}]}
```

Supported `operation_type`: `sale`, `purchase_receipt`, `stock_adjustment`, `opening_stock`
(payload includes `shop_product_id`), `stock_reversal` (payload includes `movement_id`).
`operation_id` is the idempotency key, so do not put `idempotency_key` in the payload.

One result per operation, in order: `accepted`, `duplicate` (already applied, original result
returned), `conflict` (clashes with current state, e.g. `insufficient_stock`; client must
reconcile), or `rejected` (invalid/not permitted; nothing recorded, safe to fix and resend).
Operations are independent, so one conflict does not block the rest. Resending a whole batch
after a network failure is always safe. Sales synced this way are stored with
`recording_source = "offline"`.

## Scheduled jobs

There is no background worker yet. Group orders past their deadline are settled lazily when read,
and this command settles the rest (safe to run any time; run it from cron every 5 minutes):

```bash
python manage.py close_expired_groups
```

## Not built yet

Batch/expiry and expiry alerts, notifications, payments.

## Known limitations

* **OpenAPI schema is partly incomplete.** The order and group-buying endpoints are fully described (`tests/test_schema.py` guards them). Inventory, suppliers, catalogue and sync views have no declared request or response serializers, so `manage.py spectacular --validate` still reports errors for them and skips those operations. Annotate them with `extend_schema` before a client is generated from the schema.
* **Alerts rank by absolute shortfall**, which is not comparable across units (kg vs pieces).
* Shop and catalogue lists are plain/paginated inconsistently (shops: plain array).
