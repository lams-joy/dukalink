# DukaLink Decisions and Assumptions

This file separates agreed product decisions from assumptions that must be tested. Add a dated entry whenever a material decision changes.

## Agreed baseline

1. Product: inventory and restocking platform for local duka owners, with a wholesaler discovery and group-buying marketplace.
2. Inventory supports both simple stock updates and transaction-based recording.
3. Client strategy: mobile-first duka app and wholesaler web portal.
4. Units are flexible and support conversions, such as buying sacks and selling kilograms.
5. Onboarding includes guided product setup and opening-stock entry.
6. Pilot includes both rural and urban shops.
7. MVP includes inventory, low-stock reminders, supplier listings, ordinary orders, group buying, offline inventory support, and basic operational safeguards.
8. Additions such as expiry/batch support, physical stock counts and basic gross-margin reporting should be prioritised without letting advanced accounting delay the core MVP.
9. Initial architecture: Django/DRF modular monolith, PostgreSQL, React Native/Expo mobile app, React/TypeScript wholesaler web portal.
10. Payments may initially be recorded manually; live M-Pesa integration is a later milestone once the order/settlement process is validated.

## Assumptions to validate

- Shopkeepers are willing to record enough stock events to make alerts useful.
- Offline operation is important for the pilot cohort.
- Wholesalers will maintain prices and availability or confirm them promptly.
- Group buying can reduce total delivered costs after all transport and handling fees.
- Shopkeepers will accept a clearly defined point at which group commitments become binding.
- A shared product catalogue can cover common goods while still allowing custom products.
- SMS/WhatsApp reminders justify their cost and have appropriate user consent.

## Decisions still required before production

- Exact authentication and phone verification provider.
- Supported currencies and whether any multi-currency case is required.
- Initial canonical units and allowed quantity precision.
- Whether negative stock is blocked, allowed, or shown as a provisional offline state. *(decided 2026-10-23, see Phase 5 decisions)*
- Exact stock valuation method for gross-margin estimates.
- Product and batch expiry allocation rules.
- Group-order cancellation, refund and shortage policy. *(decided 2026-10-23, see Phase 5 decisions)*
- Delivery cost allocation formula and rounding rule. *(decided 2026-10-23, see Phase 5 decisions)*
- Supplier verification evidence and dispute escalation.
- Data retention, export and account-closure rules.
- Deployment host, backup retention and recovery objectives.
- Whether live M-Pesa payments are in the pilot or later.

## Phase 5 (group buying) decisions

Chosen to keep the first pilot simple, transparent and safe. Each can be revisited with pilot evidence.

### 2026-10-23 — Group shape: one offer, one unit
- **Status:** Accepted
- **Decision:** A group order is for exactly one wholesaler offer (one product, one purchase unit). Commitments are quantities in that offer's unit, converted to base units on the server. The group has a target quantity, a deadline, a collection/delivery method, a collection point or delivery address, and an estimated delivery fee.
- **Consequences:** Simple aggregation and a single price tier per group. Multi-product groups are out of scope.

### 2026-10-23 — Who may create and join
- **Status:** Accepted
- **Decision:** Owners and managers of a shop may create, join, change or withdraw. Staff may only view. A shop has at most one active commitment per group. A person cannot join a group for their own wholesaler (same rule as ordinary orders). Only verified wholesalers with an active offer can be grouped.

### 2026-10-23 — When commitments become binding
- **Status:** Accepted
- **Decision:** Joining is NOT binding. Lifecycle: `open` (join, change and withdraw freely) -> deadline or organiser closes -> `closed` (quantities frozen, no withdrawal) -> wholesaler confirms or declines -> `confirmed` (per-shop orders generated; this is the binding point).
- **Protection against hidden commitments:** the confirmed unit price can never exceed the offer's list price (the tier for the total committed quantity applies) and the confirmed delivery fee can never exceed the group's published estimate. Participants therefore cannot be surprised upwards.
- **Consequences:** Withdrawal is not allowed once a group is closed. This is stated in the API and in the app.

### 2026-10-23 — Failed, declined and cancelled groups
- **Status:** Accepted
- **Decision:** If committed quantity is below target at the deadline the group becomes `failed`. If the wholesaler declines it becomes `declined`. The organiser may cancel while `open` (`cancelled`). All three are final, create no orders and bind nobody. The organiser can start a new group.
- **No partial confirmation in the MVP:** the wholesaler confirms the full committed quantity or declines. Shortages at delivery use the existing per-shop partial-receipt flow on each generated order.

### 2026-10-23 — Price and delivery-fee allocation
- **Status:** Accepted
- **Decision:** Every shop pays the same tier unit price, chosen by the group's total committed quantity at confirmation (this is the benefit of grouping). The delivery fee is split in proportion to each shop's committed quantity in base units, rounded to 2 decimal places using the largest-remainder method. Ties are broken by earliest `joined_at`, then shop id, so the result is deterministic. Shares always sum exactly to the delivery fee.

### 2026-10-23 — Collection or delivery
- **Status:** Accepted
- **Decision:** One method and one point per group, set by the organiser and confirmed by the wholesaler. Each generated order copies it. Per-shop delivery is not supported in groups for the MVP.

### 2026-10-23 — Deadlines without a scheduler
- **Status:** Accepted
- **Decision:** No background worker yet. A group past its deadline is closed (or failed) lazily the next time it is read or written, and a management command `close_expired_groups` closes the rest. Run it from cron (for example every 5 minutes) in the pilot.

### 2026-10-23 — Negative stock
- **Status:** Accepted
- **Decision:** Blocked (`ALLOW_NEGATIVE_STOCK=false`). Offline sales that would go negative come back as a `conflict` that the shopkeeper must resolve.

### 2026-10-23 — 5b lifecycle details
- **Status:** Accepted
- **Decision:** (1) The organiser may close early only once the target is met; otherwise they wait or cancel. (2) At confirmation the wholesaler may choose a unit price at or below a cap, where the cap is the tier price for the total committed quantity, never above the list price shown when the group was created (a later price rise cannot reach the shops). The default is the cap. (3) The delivery fee defaults to 0 and may not exceed the published estimate. (4) If the live offer no longer has the committed quantity available, confirming is refused and the wholesaler must decline. (5) A suspended wholesaler cannot confirm but can still decline. (6) A person who belongs to a shop with an active commitment cannot confirm or decline as the supplier. (7) The wholesaler sees totals, never which shops took part. (8) Lazy settlement commits before the requested action runs, so a refused write after the deadline still closes or fails the group.
- **Consequences:** Confirm and decline are guarded by the group's state under a row lock, so they need no idempotency key: a repeat is a 409.

### 2026-10-23 — 5c orders and costs details
- **Status:** Accepted
- **Decision:** (1) Generated orders start `confirmed` (the terms were agreed at confirmation) and then follow the ordinary order flow. (2) The group's goods total is the SUM of the shops' individually rounded line totals, so shares, orders and totals reconcile to the cent. (3) The delivery fee is split by base-unit quantity, largest remainder, ties by earliest `joined_at` then shop id. (4) A shop sees the group totals and its own line only; the wholesaler sees one row per order, as it already sees those shops through the orders it must fulfil. (5) Cost figures are frozen on the participant rows; the live order status is shown beside them. (6) Delivery fees are not added to stock unit cost on receipt (same as ordinary orders).
- **Open question:** generated orders currently follow the ordinary order rules, so a shop or the wholesaler can still cancel a confirmed order before dispatch. If a confirmed group commitment should be harder to walk away from, that needs its own rule (for example wholesaler-only cancellation, or a recorded reason shown to the group).

## Decision record template

### YYYY-MM-DD — Short decision title
- **Status:** Proposed / Accepted / Superseded
- **Context:** What problem prompted this decision?
- **Decision:** What did we choose?
- **Alternatives:** What else was considered?
- **Consequences:** What becomes easier/harder?
- **Follow-up:** Tests, migrations or documentation required.
