# Implemented features

What the system does **today**, written from the code (backend modules, mobile screens, portal
pages). Use [`next-steps.md`](next-steps.md) for what is missing and [`api.md`](api.md) plus the live
`/api/docs/` page for endpoint detail. When you add or change a feature, update this file in the same
pull request.

Status words: **Done** = works end to end and has tests (backend) or has been used manually
(frontends have no automated tests). **Partial** = works with the limits stated.

## 1. The people (roles)

| Role | Who | Signs in at | Can do |
|---|---|---|---|
| Shop owner | Runs a shop | Shop app | Everything for their shops, including adding team members. |
| Shop manager | Added by an owner | Shop app | Everything except adding members. |
| Shop staff | Added by an owner | Shop app | Read stock; record sales and goods received. Cannot change settings, adjust stock or create orders/groups. |
| Wholesaler owner / manager / staff | Runs a wholesale business | Portal | Manage business, offers, orders and group buys (staff are more limited). |
| Platform administrator | A user with `is_staff` (every superuser) | Portal `/admin` and Django admin | Verify or suspend wholesalers; maintain the shared catalogue. |

One account can hold several roles (own a shop and work for a wholesaler), except where a rule
forbids a conflict of interest (a person cannot order from, join a group for, or confirm for their
own wholesaler). People who are not members of a shop or business get `404`, not `403`, so existence
is not revealed.

## 2. Accounts and access (backend `accounts`, `shops`)

- **Done:** register and sign in with phone number and password (Kenyan numbers are normalised to E.164);
  JWT access token (15 minutes) with silent refresh (30-day rotating refresh token); `GET /me/`.
- **Done:** create shops, list your shops, edit a shop, add existing users as members with a role,
  per-shop permissions enforced on every endpoint, with tests that prove one shop cannot read another's data.
- **Done:** shop onboarding state and completion, a tracking preference (quick "simple" adjustments or
  full "transaction" receipts and sales).
- **Not built:** phone-number verification (OTP), password reset, logout/token revocation, adding a
  member who has no account yet.

## 3. Product catalogue (backend `catalog`)

- **Done:** a shared catalogue of products, each with a base unit (kg, litre, piece) and named units with
  conversion factors (for example `50 kg sack = 50 kg`). Search by name, brand, category or barcode.
- **Done:** shops can add **custom products** with their own units, and track catalogue products with opening stock.
- **Done:** platform administrators create, edit and deactivate shared products and units
  (`/admin/catalog/products/...`, portal pages `/admin/catalogue`). Duplicate name+brand is rejected; the base unit is protected.
- **Done:** `manage.py seed_catalog [--file my.csv]` loads products from CSV (idempotent; never deletes).
  The bundled file has 47 products and 87 units. `seed_demo_catalog` is an alias kept for old instructions.
- **Not built:** adding units to an existing product from the shop app, barcode scanning (the field and search exist).

## 4. Inventory engine (backend `inventory`, `sync`)

The core of the product. Stock is an **append-only ledger of movements**; the visible balance is a
cached total that tests prove reconciles with the ledger.

- **Done:** movement types `opening_stock`, `purchase_receipt`, `sale`, `return`, `damage`, `adjustment`, `reversal`.
- **Done:** unit conversion on the server (receive 1 sack of 50 kg, sell 1.5 kg; stock moves by exactly +50 and −1.5).
- **Done:** purchase receipts and sales with lines; stock adjustments; manager-only **reversal** of a mistaken
  movement with a reason (reversed lines are voided and excluded from reports).
- **Done:** **idempotency**: every write carries a UUID `idempotency_key`. Same key + same payload returns the original
  result (`Idempotent-Replayed: true`); same key + different payload is `409 idempotency_conflict`.
- **Done:** **concurrency safety** via row locks, with PostgreSQL race tests (simultaneous sales, orders, group joins).
- **Done:** **negative stock is blocked** (`409 insufficient_stock`) unless `ALLOW_NEGATIVE_STOCK=true`.
- **Done:** **stock counts**: start, enter counted quantities, submit, a manager approves (creating adjustment
  movements for the variances) or cancels.
- **Done:** **low-stock alerts** (per-item reorder level) and a **summary report** for a date range: tracked/low-stock/out-of-stock counts, sales count and total, purchases count and total cost, and top-selling products by revenue.
- **Done:** **offline sync endpoint** `POST /shops/{id}/sync/`: up to 100 queued operations per batch, each reported as
  `accepted`, `duplicate`, `conflict` or `rejected`; one failure never blocks the rest; resending a batch is always safe.
- **Partial:** alerts are ranked by absolute shortfall, which is not comparable across units (kg vs pieces).
- **Not built:** batch/expiry tracking and expiry alerts; barcode-driven entry; gross-margin or stock-valuation reports (unit costs are stored on receipts; no report uses them yet).

## 5. Wholesalers, offers and the marketplace (backend `suppliers`)

- **Done:** register a wholesale business (starts **pending**); a platform administrator **verifies** or **suspends**
  it. Shops only see offers from verified wholesalers (`SUPPLIER_VERIFICATION_REQUIRED`).
- **Done:** wholesaler team members with roles; per-business audit log.
- **Done:** **offers**: a product + purchase unit with price, minimum order, availability (`in_stock`, `limited`,
  `out_of_stock`), visibility and **volume price tiers**.
- **Done:** marketplace search and compare for shops, a **price quote** endpoint, and a verified-wholesaler directory.

## 6. Ordinary orders (backend `orders`)

- **Done:** a shop owner or manager places an order for an offer; **agreed terms are snapshotted**, so later catalogue
  price changes never alter an existing order.
- **Done:** lifecycle `submitted → confirmed → dispatched → received`, with `rejected` and `cancelled` branches;
  the wholesaler confirms with a delivery fee, rejects with a reason, dispatches or cancels with a reason.
- **Done:** receiving goods per item, including **shortages**; receiving adds the stock to the shop's ledger in base units.
- **Done:** delivery or collection per order; concurrency tests cover simultaneous order actions (PostgreSQL only).

## 7. Group buying (backend `groupbuying`)

One group = one wholesale offer in one unit (see `decisions.md`, Phase 5).

- **Done:** create a group (target quantity, deadline, delivery or collection point, delivery-fee estimate);
  browse open groups; **join, change or withdraw** while open; one commitment per shop.
- **Done:** lifecycle `open → closed → confirmed`, plus `failed` (target missed at deadline), `declined` (by the
  wholesaler) and `cancelled` (by the organiser while open). Expired groups close lazily when read and via
  `manage.py close_expired_groups` (run from cron; there is no background worker).
- **Done:** the **binding point** is wholesaler confirmation. At confirmation the unit price cannot exceed the tier price
  for the total quantity and the delivery fee cannot exceed the published estimate, so shops cannot be surprised upwards.
- **Done:** on confirmation one **order per participating shop** is created atomically; every shop pays the same
  tier price; the delivery fee is split by quantity using the largest-remainder method so shares sum exactly to the total.
- **Done:** `cost-breakdown` endpoint (a shop sees totals and its own line; the wholesaler sees one row per order,
  never the shops' other details); shop cancellation of group orders is refused (`409 group_order_locked`), wholesaler
  cancellation is allowed with a reason and recorded.

## 8. Audit log (backend `audit`)

- **Done:** significant actions (order and group transitions, member changes, verification, counts, reversals) are
  recorded as audit events; visible to shop owners and managers (shop settings) and to wholesaler owners and managers (portal settings).

## 9. API conventions (backend `common`)

- Versioned REST under `/api/v1/`, OpenAPI at `/api/schema/`, Swagger UI at `/api/docs/`.
- Error envelope `{"error": {"code", "message", "details", "request_id"}}` for every handled error, including 500s.
- `X-Request-ID` accepted or generated and echoed on every response (also exposed to browsers via CORS).
- Pagination `{count, next, previous, results}` (default 50, max 200); decimals are strings; timestamps ISO 8601 UTC.
- Health check `GET /api/v1/health/` (no auth), used by deploy checks.

## 10. Shop app (`apps/mobile`)

Expo Router screens, styled with a glass theme. See [`apps/mobile/README.md`](../apps/mobile/README.md) for the full table.

- **Done:** sign in/register; list and create shops; shop home with summary numbers.
- **Done:** inventory list and search, item detail (correct stock, reorder level), track a catalogue product with opening stock,
  add your own product with custom units.
- **Done:** record a sale; record goods received; movement history with manager reversal; low-stock alerts; stock counts.
- **Done:** marketplace (offers, quotes, wholesaler directory), place orders, order history, confirm delivery with shortages, cancel.
- **Done:** group buying (browse all open offers when starting one, start, join, change, withdraw, organiser close/cancel, cost breakdown).
- **Done:** shop settings: edit shop, tracking mode, add team members, finish setup, activity log.
- **Done (offline):** sales, goods received and stock corrections are **queued on the device** (AsyncStorage) when the network
  is down and replayed through the sync endpoint; a **Queue** screen shows pending/failed records with Sync now and Discard.
  Replays never double-apply.
- **Not built:** offline reading of lists (lists need a connection); orders, counts and groups need a connection; notifications;
  an Android/iOS store build configuration (no application id, icons or EAS setup yet).

## 11. Wholesaler portal (`apps/wholesaler-web`)

- **Done:** sign in/register; list and create businesses; dashboard (verification status, open orders, groups awaiting a decision).
- **Done:** offers list, create from the catalogue, edit price/availability/visibility/volume tiers.
- **Done:** incoming orders (confirm with delivery fee, reject, dispatch, cancel).
- **Done:** group buys (confirm, which is binding, or decline; see agreed terms).
- **Done:** settings (edit business, team members, audit log).
- **Done:** platform admin: pending wholesalers (verify/suspend) and the shared catalogue editor.
- **Not built:** a separate order detail page, reports, notifications.

## 12. Operations tooling

- **Done:** single-server deployment scripts (`deploy/`), nginx host-based routing, gunicorn, database backup script with 14-file retention.
- **Done:** GitHub Actions CI for the backend (lint, Django check, migration check, tests on PostgreSQL 16).
- **Not built:** monitoring/alerting, automated backups schedule, restore drill, CI for the frontends, container image publishing.

## 13. Business rules worth knowing

| Rule | Where it lives |
|---|---|
| Quantities are stored in **base units**, 6 decimal places; money has 2 | `apps/common/money.py`, `apps/inventory/units.py` |
| Not a member of a shop → 404; member without the role → 403 | `apps/shops/access.py`, `apps/suppliers/access.py` |
| Owner/manager can write; staff can only record sales and receipts | `apps/shops/access.py` |
| Wholesalers must be verified for offers to be visible | `SUPPLIER_VERIFICATION_REQUIRED` |
| Group joining is not binding; wholesaler confirmation is | `apps/groupbuying/services.py` |
| Delivery-fee split: proportional, largest remainder, ties by earliest join then shop id | `apps/groupbuying/costs.py` |
| Negative stock blocked by default | `ALLOW_NEGATIVE_STOCK` |
