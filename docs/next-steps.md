# Next steps: what to fix, finish and build

Written for whoever continues the project. It separates **known gaps in what exists** from **new features**,
and says in what order to tackle them. Product-level ideas and their risks are in
[`probable-features.md`](probable-features.md); decisions that are still open are in
[`decisions.md`](decisions.md). Keep this file current: delete items when they are done.

Size guide: **S** = under a day, **M** = a few days, **L** = a week or more.

## 1. Before a real pilot (hardening what exists)

| # | Item | Size | Notes |
|---|---|---|---|
| 1 | **Phone verification and password reset** | M | Today anyone can register with any phone number and there is no reset flow. Needs an SMS provider decision (open in `decisions.md`). Add endpoints in `apps/accounts`, screens in both apps. |
| 2 | **Logout and token revocation** | S | Refresh tokens rotate but cannot be revoked. Use SimpleJWT's blacklist app. |
| 3 | **Backup schedule and a proven restore** | S | `deploy/backup.sh` exists; schedule it, copy backups off the server, and rehearse the restore in `deployment.md`. |
| 4 | **Monitoring and alerts** | M | Nothing watches the server. At minimum an uptime check on `/api/v1/health/`, disk space, and container restarts. Consider Sentry for the backend and apps (errors carry a `request_id` already). |
| 5 | **Run the container as a non-root user** | S | `backend/Dockerfile` has no `USER`; gunicorn runs as root. Add a user, check `staticfiles` permissions. |
| 6 | **Scheduler for group deadlines** | S | `close_expired_groups` must be run by cron (see `deployment.md`). Move to a worker (Celery/RQ) or keep cron, but make sure it is installed on every environment. |
| 7 | **Runtime API address for the frontends** | M | The API URL is compiled into each bundle, which caused a real outage-like confusion (stale `:3007` address cached in browsers). Serve a small `config.json` at runtime, or always rebuild and version-bump the files on deploy. |
| 8 | **Frontend CI** | S | Add a workflow that runs `npm ci && npm run typecheck` (shop app) and `npm ci && npm run build` (portal). Only the backend has CI today. |
| 9 | **Frontend tests** | M-L | None exist. Start with the API client (`src/api.ts`, `src/offline.ts`: token refresh, queue, replays), then the money/quantity forms. |
| 10 | **Finish the OpenAPI schema** | M | `python manage.py spectacular --validate` reports problems for inventory, suppliers, catalogue and sync views (no declared request/response serializers). Annotate them with `extend_schema` like `orders` and `groupbuying`, and extend `tests/test_schema.py`. Needed before generating typed clients. |
| 11 | **Data retention, export and account closure** | M | Open decision. Needed for privacy compliance before real shops join. |
| 12 | **Secrets and history hygiene** | S | Rotate any value that was ever committed (see `configuration.md` section 5) and make sure `deploy/.env` is backed up somewhere safe. |
| 13 | **Format the code base once** | S | 59 backend files are not `ruff format`-clean. Do a single formatting commit, then add `ruff format --check .` to CI. |

## 2. Known limitations in the current code

- **Alerts rank by absolute shortfall** (`apps/inventory/reports.py`), which is not comparable across units (kg vs pieces).
  Rank by percentage below reorder level or group by unit.
- **List endpoints are inconsistent**: the shops list is a plain array while most others are paginated.
- **Offline support covers writes only.** Sales, receipts and adjustments queue on the device (AsyncStorage). Lists and
  products are not cached, so the app shows nothing useful offline until it has loaded data online. The original plan
  specified a SQLite store on the device; the current queue is simpler and may need replacing.
- **Offline conflicts are reported, not merged**: a `conflict` (for example insufficient stock) needs the shopkeeper to decide.
- **Orders, stock counts and group buying need a connection** by design.
- **Group buying has no partial confirmation**: the wholesaler confirms the full committed quantity or declines.
  A cancelled group order can leave the wholesaler delivering less than agreed (accepted for the pilot; review with real cases).
- **Delivery fees are not added into stock unit cost** when goods are received.
- **Single currency (KES) per deployment**; **UTC storage** with a per-shop display timezone field.
- **No notifications** of any kind (no SMS, WhatsApp or push); users must open the app to see changes.
- **Payments are not handled**; payment is arranged outside the system.
- The mobile app has **no store-ready build configuration** (`apps/mobile/app.json` has no Android package id, icons or splash,
  and there is no EAS config).
- The portal has **no order detail page** (the list shows the details) and **no reports**.
- Adding units to an existing catalogue product is only possible for platform admins, not from the shop app.

## 3. Feature backlog (suggested order)

Take from the top; stop and validate with real shops before going further. Details, risks and feature gates are in
[`probable-features.md`](probable-features.md).

| Order | Feature | Why now | Rough size | Where to start |
|---|---|---|---|---|
| 1 | Notifications (SMS first) for low stock, order and group status | Users do not open the app daily; group deadlines and order updates are time-critical | M-L | New `apps/notifications`; hook into `orders`, `groupbuying`, `inventory.alerts` services. Needs consent and opt-out. |
| 2 | Reorder suggestions and "reorder from a previous purchase" | Cheapest way to make restocking faster | M | Use movement history; keep rules transparent (days of stock left from recent sales). |
| 3 | Expiry and batch tracking for selected goods | Reduces spoilage; planned in the MVP but not built | L | Needs batch allocation rules (open decision); extend `inventory` models and receipts. |
| 4 | Gross margin and stock valuation reports | Unit costs are already stored on receipts | M | Open decision on valuation method (FIFO/average). Add to `reports.py` and the shop home screen. |
| 5 | Wholesaler catalogue bulk upload (CSV) | Large catalogues are tedious; `seed_catalog` already shows the pattern | M | Reuse the CSV parsing of `seed_catalog`; add a review step before publishing. |
| 6 | Barcode scanning | Faster product setup and stock entry; the `barcode` field and search exist | M | `expo-camera` / barcode scanner in `apps/mobile`; keep manual entry as fallback. |
| 7 | Collection-point and delivery tracking for group orders | Makes pooled deliveries practical | M | Extend `groupbuying` with delivery status and handover records. |
| 8 | Kiswahili and low-data mode | Reach and cost | M | Introduce an i18n layer in both apps; validate wording with users. |
| 9 | M-Pesa (Daraja) payments and reconciliation | Only after manual payment records and support processes exist | L | Separate `apps/payments`; callbacks must be verified; do not start before the pilot proves the order flow. |
| 10 | Exports (CSV/PDF) of stock, sales and purchases | Owners keep paper and spreadsheets | S-M | Read-only endpoints respecting shop permissions. |

**Do not build yet** (see `docs/README.md` scope discipline): lending or credit scoring, a stored-value wallet or escrow,
advanced accounting, AI forecasting, automatic route optimisation, multi-branch management.

## 4. Open decisions (need the product owner)

From `decisions.md` ("Decisions still required before production"):

1. Authentication and phone verification provider.
2. Supported currencies and quantity precision rules.
3. Stock valuation method for margins.
4. Expiry and batch allocation rules.
5. Supplier verification evidence and dispute escalation.
6. Data retention, export and account-closure rules.
7. Deployment host, backup retention and recovery objectives.
8. Whether live M-Pesa payments belong in the pilot.

## 5. How to add a feature (conventions to follow)

Backend (each Django app under `backend/apps/<name>/`):

1. **Model + migration**: edit `models.py`, run `python manage.py makemigrations`, commit the migration file.
2. **Business logic in `services.py`**, not in views. Services run inside `transaction.atomic`, lock rows
   (`select_for_update`) when changing balances, and raise `DomainError(message, code=...)` for expected failures
   (these become the standard error envelope).
3. **Permissions** with the helpers in `apps/shops/access.py` (`get_membership(user, shop_id, roles=...)`) or
   `apps/suppliers/access.py` (wholesalers, `require_platform_admin`). Non-members get 404, wrong role 403.
4. **Serializers and views** are thin: validate input, call the service, shape the response. Writes take an
   `idempotency_key` and must be safe to retry; see `apps/sync/idempotency.py` and how `sales` uses it.
5. **Audit**: record significant actions with `apps/audit/services.py`.
6. **URLs** in the app's `urls.py` (they are all included from `config/api_urls.py`).
7. **Schema**: annotate with `extend_schema` (request and responses) and extend `tests/test_schema.py`.
8. **Tests** in `backend/tests/` (pytest + `APIClient`; fixtures in `conftest.py`). Add concurrency tests for anything that
   touches balances (they only run on PostgreSQL).
9. **Docs**: update `docs/features.md`, `docs/api.md` if the contract changed, and `docs/decisions.md` for any decision.

Frontends:

- API calls go through `src/api.ts` in each app (bearer token, silent refresh, error envelope, pagination, idempotency keys).
  Never call `fetch` directly from a screen.
- Mobile routes are files in `apps/mobile/app/` (Expo Router); shared UI is in `src/ui.tsx`, colours and spacing in `src/theme.ts`.
- Portal routes are declared in `apps/wholesaler-web/src/App.tsx`; pages are in `src/pages/`.
- Quantities and money arrive as strings. Do not convert them to JavaScript numbers for calculations that matter;
  display what the server computed.

Git workflow (from `implementation.md`): short-lived feature branches, one logical change per pull request, migrations and tests
in the same PR, run `ruff check .` and the tests before opening it, and record architectural decisions in `decisions.md`.
