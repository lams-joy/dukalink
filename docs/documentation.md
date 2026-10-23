# DukaLink Product and Technical Documentation

## 1. Purpose

This document defines the shared product and engineering rules for the DukaLink MVP. It is the baseline for implementation. When code and documentation diverge, update the documentation and record consequential changes in `decisions.md`.

## 2. Proposed technology stack

### Mobile
- React Native with Expo and TypeScript.
- Local SQLite database for inventory cache and pending operations.
- A small API client with typed request/response schemas.
- Push notifications may be added; local notifications can support scheduled reminders where appropriate.

### Web
- React + TypeScript for the wholesaler portal and lightweight admin.
- Shared API contract and generated types where practical.
- Do not force the wholesaler portal into the mobile app's navigation architecture.

### Backend
- Python and Django.
- Django REST Framework for versioned REST APIs.
- PostgreSQL as the source of truth.
- A background job mechanism for notifications, reconciliation and scheduled work when needed. Keep the first deployment simple.
- OpenAPI documentation for the API.

### Operations
- Docker-based local development.
- Separate development, staging and production configuration.
- Environment-based secrets; never commit credentials.
- Automated tests, structured logs, database backups and restore drills.

These are proposed defaults, not evidence that the repository already exists or that any dependency has been installed.

## 3. Architectural shape

Use a modular monolith initially. Keep clear domain boundaries without introducing microservices before traffic or team structure justifies them.

Suggested backend domains:
- `accounts`: users, authentication and memberships.
- `shops`: shop profiles, settings and roles.
- `catalog`: products, categories and units.
- `inventory`: shop products, stock movements, receipts, sales, stock counts and alerts.
- `suppliers`: wholesaler profiles, verification and offers.
- `orders`: ordinary orders, order items and fulfilment.
- `groupbuying`: groups, commitments and cost allocation.
- `notifications`: in-app and external notification records.
- `sync`: idempotency and offline operation processing.
- `payments`: later-stage payment integration and reconciliation.
- `audit`: sensitive business-event history.

The mobile app and web portal must use the same backend business rules. Do not duplicate unit-conversion or order-pricing logic in clients as the authoritative implementation.

## 4. Authoritative data rules

- PostgreSQL is authoritative for synchronised state.
- Local SQLite is authoritative only for unsynchronised local work until the server accepts it.
- A client must show pending, accepted, rejected and conflict states distinctly.
- `ShopProduct.quantity_base` is a cached balance; the stock movement ledger is the audit source.
- All stock-changing actions must create appropriate movement records in the same database transaction as the business record.
- A stock movement is not silently edited or deleted during ordinary operations. Use reversal/correction movements.
- Supplier offer changes must not rewrite confirmed order terms.
- Payment status is determined by verified provider events or authorised manual reconciliation, not by a client-side success flag.

## 5. Inventory modes

Support two recording styles over one shared ledger.

### Simple update mode
The owner can enter a physical count or quantity change with a reason. The application records an adjustment movement and preserves the prior balance in history.

### Transaction-based mode
The owner records purchase receipts, sales, returns, damage and other supported transactions. These create corresponding stock movements.

A shop may use both approaches. A quick adjustment is not a separate inventory engine and must not bypass the ledger.

## 6. Units and conversion rules

Every tracked product has one canonical base unit. Every supported purchase or sale unit defines how many base units it represents.

Example:
- Base unit: kg.
- Unit: 50 kg sack.
- Conversion: 1 sack = 50 kg.
- Purchase: 1 sack.
- Stock movement: +50 kg.
- Sale: 1.5 kg.
- Stock movement: -1.5 kg.

Conversion factors are product-specific when packaging differs. Never assume all cartons or crates have the same contents.

Use decimal arithmetic for quantities and money. Validate allowed precision and whether fractional quantities are valid for each unit. Snapshot the unit and conversion used for a transaction so future catalogue edits do not rewrite historical quantities.

## 7. Inventory integrity and transaction boundaries

A sale/receipt operation must be atomic:
1. Validate access and request shape.
2. Validate the product and unit.
3. Resolve the conversion using the stored unit definition.
4. Lock or otherwise safely coordinate the current balance.
5. Create the transaction and its line items.
6. Create stock movement records.
7. Update the cached balance.
8. Record the idempotency result.
9. Commit.

If any required step fails, roll back the transaction. Prevent duplicate application using a unique idempotency key scoped to the correct actor/resource. Reusing a key with a different payload must return a conflict.

Do not rely only on client-side stock checks. Concurrent operations require server-side atomic validation.

## 8. Offline behaviour

The mobile client stores unsynchronised operations locally with:
- Unique operation ID.
- Operation type.
- Shop and product references.
- Original unit and quantity.
- Creation timestamp.
- Payload/schema version.
- Sync status and last error.

The server processes operations idempotently and returns a result per operation. It must not silently replace one offline operation with another.

A locally recorded sale may be shown as pending. If the server rejects it due to insufficient stock or another rule, show the reason and provide a reconciliation workflow. Do not represent pending orders or payments as confirmed.

## 9. Low-stock alert rules

A shop product has an optional reorder threshold expressed in the canonical unit. When a valid stock change crosses from above the threshold to at/below it, create a low-stock event/notification. Avoid creating a duplicate on every subsequent movement.

Re-arm the alert when stock rises sufficiently above the threshold according to a documented rule. Store notification delivery status and retries. Alert generation must be safe under concurrent stock changes.

## 10. Marketplace rules

An offer should contain:
- Wholesaler and product references.
- Offered package/unit.
- Price and currency.
- Minimum order quantity.
- Available quantity or availability state.
- Price tiers where supported.
- Delivery area and delivery terms.
- Last-updated timestamp and active status.

Before accepting an order, the supplier confirms availability and terms. Confirmed orders snapshot product name, unit, conversion, quantity, unit price, line totals and delivery terms.

A substitution requires buyer approval. Do not silently replace a brand, package size or product.

## 11. Group-buying rules

A group order defines its product/offer, target, canonical unit, deadline, supplier terms, delivery plan and status.

A participant commitment is stored separately. The aggregate committed quantity is derived from active commitments and may be cached for performance. Reconcile cached aggregates against participant records.

Define the point at which commitments become binding. Before that point, withdrawal or quantity changes may be permitted under the group's rules. Supplier confirmation and explicit final terms precede generation of confirmed per-shop orders.

Cost breakdowns must show goods, delivery, handling and other known fees. Allocations must add up to the total charge, including deterministic handling of rounding. Failed groups, partial fulfilment, cancellations, refunds and disputes require explicit states and rules.

## 12. Security and privacy

- Enforce shop-level membership permissions on every private object.
- Enforce supplier business permissions on catalogue and order operations.
- Validate permissions server-side; hiding UI controls is not security.
- Use secure session/token handling and a recovery process.
- Rate-limit sensitive authentication and public endpoints.
- Keep secrets in environment/secret management.
- Record audit events for stock changes, supplier verification, order status changes and payment reconciliation.
- Minimise collection and exposure of personal and business data.
- Do not disclose a shop's private inventory, sales or cash position to other shops.
- Provide data export and a documented account/shop closure process.

## 13. Notifications

In-app alerts are the baseline. SMS, WhatsApp or push channels may be added after validating provider cost, consent, reliability and user preference. Notifications should link to the relevant stock item, offer or order.

Avoid duplicate reminders. Allow users to configure channels and frequency. A notification delivery failure must not roll back an already valid stock movement.

## 14. Observability and operations

Track:
- API error rate and latency.
- Failed or repeated sync operations.
- Stock ledger/balance reconciliation mismatches.
- Failed notification deliveries.
- Stale supplier offers.
- Order cancellations and fulfilment delays.
- Payment callback/reconciliation exceptions if payments are later integrated.

Back up the database, test restores, document migrations and use separate credentials/environments. Do not log passwords, access tokens, payment secrets or unnecessary personal data.

## 15. API conventions

- Prefix: `/api/v1/`.
- JSON request/response bodies.
- ISO 8601 timestamps with timezone.
- Decimal quantities and monetary amounts represented as strings in JSON.
- Consistent pagination, filters and validation errors.
- Idempotency for writes that create or change stock, orders, group commitments or payments.
- Explicit state-transition endpoints for sensitive actions.
- OpenAPI schemas maintained with implementation.

## 16. Definition of done

A feature is done only when:
- Its user workflow and permissions are documented.
- Server validation and error responses exist.
- Database constraints and migrations are included.
- Unit and integration tests cover normal and failure paths.
- Idempotency/concurrency is considered for writes.
- Mobile/web loading, empty, offline and error states are implemented where applicable.
- Logs/metrics are sufficient to diagnose failures.
- Documentation and API schema are updated.
