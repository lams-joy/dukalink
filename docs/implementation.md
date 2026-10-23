# DukaLink Implementation Roadmap

## Delivery principle

Build a working vertical slice in each phase. Keep changes small, testable and reviewable. Do not implement all database models before proving the main user journeys.

## Current progress

| Phase | Status |
|---|---|
| 0 Foundation | Done (Django, Postgres, Docker, CI, OpenAPI) |
| 1 Accounts, shops, catalogue | Done |
| 2 Inventory engine (backend) | Done; mobile SQLite/offline queue not started |
| 3 Mobile inventory experience | Not started |
| 4 Wholesaler catalogue and orders (backend) | Done; wholesaler web portal not started |
| 5 Group buying (backend) | Done (5a-5d); mobile and wholesaler web screens not started |
| 6 Pilot hardening | Not started |

Backend checks: `ruff check .`, `makemigrations --check`, and `pytest` on PostgreSQL 16 (race tests are skipped on SQLite).

## Phase 0 — Repository and foundation

### Work
- Confirm whether a repository already exists; inspect it before scaffolding.
- Set up backend, mobile and wholesaler web directories.
- Configure Django, PostgreSQL, local environment variables and Docker.
- Create the custom user model before the first migration.
- Add linting, formatting, test runner and CI.
- Establish API error, pagination, timestamp and decimal conventions.
- Publish OpenAPI docs.

### Exit criteria
- A fresh developer can follow README instructions to run the system.
- Database migrations run from an empty database.
- CI runs basic checks.
- Secrets are not committed.

## Phase 1 — Accounts, shops and catalogue

### Work
- Authentication and recovery foundation.
- Shop creation and membership roles.
- Shared products and custom shop products.
- Base units and product-specific conversion factors.
- Guided onboarding and opening-stock workflow.

### Exit criteria
- A new shop can be created and configured.
- Opening stock creates auditable movements.
- Cross-shop access tests pass.
- Invalid units/conversions are rejected.

## Phase 2 — Inventory engine

### Work
- Stock movement ledger and cached balances.
- Purchase receipts and sales.
- Simple stock adjustments and reversals.
- Idempotency and concurrency safety.
- Physical stock counts and approved variances.
- Low-stock alerts and basic reports.
- Mobile SQLite schema and offline operation queue.

### Exit criteria
- A 50 kg sack adds 50 kg.
- A 1.5 kg sale subtracts 1.5 kg.
- Duplicate requests do not double-apply.
- Concurrent operations cannot silently lose updates.
- Offline operations reconcile or surface explicit conflicts.
- Balance/ledger reconciliation tests pass.

## Phase 3 — Mobile inventory experience

### Work
- Home dashboard and inventory list/search.
- Add product and quick adjustment.
- Receipt and sale flows.
- Unit conversion preview.
- Opening stock wizard.
- Stock count.
- Alert list and movement history.
- Sync status and retry/reconciliation UI.

### Exit criteria
- Shopkeepers can complete common tasks with minimal navigation.
- Offline and error states are understandable.
- Usability test feedback is addressed.

## Phase 4 — Wholesaler catalogue and ordinary orders

### Work
- Supplier profile and verification workflow.
- Offer management and price tiers.
- Search and compare offers.
- Order submission and supplier confirmation.
- Dispatch, delivery receipt and shortage reporting.
- Wholesaler web portal.

### Exit criteria
- A test order can be placed, confirmed, fulfilled and received.
- Agreed terms remain unchanged when the catalogue price changes.
- Supplier permissions and audit events work.

## Phase 5 — Group buying

### Work
- Group creation and discovery.
- Participant commitments and deadlines.
- Target calculation and supplier confirmation.
- Per-shop order generation.
- Cost breakdown and delivery/collection point.
- Withdrawal, failed target, shortage and cancellation paths.
- Manual delivery coordination tools.

### Delivery chunks (backend)

Decisions for this phase are in `decisions.md` (2026-10-23). Each chunk ships with tests, a migration if needed, and a green PostgreSQL run.

- **5a Groups and commitments (done):** `GroupOrder` and `GroupParticipant` models; create, list, detail and progress; join, change and withdraw while open; one commitment per shop; cached committed quantity that reconciles to active commitments; idempotency, row locking, audit events; race tests for simultaneous joins and changes.
- **5b Lifecycle and supplier confirmation (done):** deadline handling (lazy close plus `close_expired_groups`), failed, cancelled and declined paths, wholesaler confirm with price and delivery-fee caps and a terms snapshot, binding point enforced, permissions and audit.
- **5c Orders and costs (done):** atomic generation of one order per participating shop, same tier price, largest-remainder delivery-fee split, `cost-breakdown` endpoint, reconciliation tests (aggregates equal commitments; costs equal totals), a full recruitment-to-receipt scenario test.
- **5e Cancelling a confirmed group order (done):** shop cancellation refused for group orders (409 `group_order_locked`), wholesaler cancellation kept with its reason, `cancelled_by` and `cancel_reason` on the cost breakdown, audit event linked to the group.
- **5d Wrap-up (done):** `api.md` and the README reconciled with the code, full PostgreSQL run.

### Exit criteria
- A complete group can progress from recruitment to delivery.
- Group aggregates reconcile with commitments.
- Costs reconcile with the total.
- No participant becomes bound before the documented confirmation point.
- Failed groups follow explicit rules.

## Phase 6 — Pilot hardening

### Work
- Monitoring and alerting.
- Backup and restore test.
- Supplier listing freshness workflow.
- Data export.
- Pilot onboarding and support process.
- Device/connectivity testing.
- Baseline and follow-up metrics.

### Exit criteria
- Team can diagnose sync, stock and order failures.
- Restore procedure is proven.
- Pilot participants understand pending versus confirmed states.
- Findings are documented before expansion.

## Phase 7 — Decide on next additions

Use pilot evidence to prioritise:
- M-Pesa integration.
- SMS/WhatsApp/push notifications.
- Barcode scanning.
- Improved expiry tracking.
- Restocking budget and demand estimates.
- Automated delivery routes.
- Advanced reporting.

Do not add a feature solely because it is technically possible. Evaluate user demand, operational complexity, privacy, cost and measurable benefit.

## Suggested first tickets

1. Repository inspection and local setup.
2. Django project and custom user model.
3. Shop/membership permissions.
4. Product and ProductUnit models.
5. ShopProduct and StockMovement models.
6. Opening-stock service and tests.
7. Receipt service and conversion tests.
8. Sale service and concurrency/idempotency tests.
9. Mobile onboarding and inventory list.
10. Local SQLite and sync operation model.

## Git workflow suggestion

- Work on short-lived feature branches.
- Keep one logical feature per pull request.
- Include migrations and tests with model changes.
- Run formatting, linting and tests before merging.
- Avoid broad UI refactors while implementing domain logic.
- Record architectural decisions in `decisions.md`.
