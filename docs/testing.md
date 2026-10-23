# DukaLink Testing Strategy

## 1. Testing goals

Prove that stock quantities, unit conversions, supplier terms, group commitments and sync behaviour remain correct under retries, poor connectivity and concurrent operations.

## 2. Unit tests

### Unit conversions
- One 50 kg sack converts to 50 kg.
- A sale of 1.5 kg leaves 48.5 kg from 50 kg.
- A carton conversion is product-specific.
- Zero/negative conversion factors are rejected.
- Unsupported fractional quantities are rejected.
- Historical transactions remain stable after a unit definition changes.

### Inventory
- Opening stock produces a positive movement.
- Receipt and sale create the correct movements.
- Adjustment requires a reason where policy requires one.
- Reversal restores the correct balance without deleting history.
- Low-stock alerts trigger on threshold crossing and are not duplicated on every subsequent movement.
- A stock count does not change stock until approved.

### Money
- Decimal arithmetic is used.
- Line totals and order totals reconcile.
- Delivery allocation sums exactly to the delivery fee.
- Rounding is deterministic.
- Price changes do not rewrite confirmed orders.

## 3. Integration tests

- Sale record, line items, movement and balance update are atomic.
- Failed operations roll back all required records.
- Repeated idempotency key plus same payload returns original result.
- Repeated key plus different payload returns conflict.
- Concurrent sales cannot silently overwrite one another.
- Permissions are checked on every resource.
- A supplier cannot access unrelated suppliers' orders.
- An ordinary order can be confirmed, dispatched, received and reconciled.
- A group order produces one order per participating shop.
- Partial delivery records actual received quantities and discrepancies.

## 4. Offline and sync tests

- Local changes survive app restart.
- Retry after network loss does not duplicate an operation.
- Sync returns a result per operation.
- Duplicate operation IDs are safe.
- A conflicting payload using the same operation ID is rejected.
- Out-of-order operations are handled according to a documented policy.
- A pending sale is not presented as server-confirmed.
- Server rejection appears in the UI with a recovery path.
- Two devices changing the same stock do not silently overwrite data.

## 5. Security tests

- Shop A cannot read or alter Shop B's inventory.
- Shop staff cannot perform owner-only operations.
- Unverified wholesalers cannot publish active offers if verification is required.
- A supplier cannot change another supplier's offer.
- A shop cannot confirm its own supplier fulfilment unless explicitly allowed by the workflow.
- Invalid state transitions are rejected.
- Secrets and personal data do not appear in application logs.
- Rate limits and account recovery protections are tested.

## 6. Group buying tests

- Joining a closed/expired group fails.
- Duplicate join requests do not double-count quantities.
- Changing a commitment recalculates totals atomically.
- A group cannot confirm if the target or supplier conditions are not satisfied.
- Participant cancellation follows the commitment cutoff.
- Supplier rejection/shortage follows the documented fallback.
- Per-shop quantities sum to the group quantity.
- Cost allocation sums to the actual group delivery cost.
- Collection/delivery choices are preserved on resulting orders.

## 7. End-to-end acceptance scenarios

### Scenario A: setup and sale
Create a shop, add sugar, enter 50 kg opening stock, record a 1.5 kg sale and verify 48.5 kg remains.

### Scenario B: low stock
Set a reorder threshold, reduce stock across it, verify one alert is created and check re-arming after replenishment.

### Scenario C: offline operation
Record a stock change offline, restart the app, reconnect, sync, retry and verify only one movement exists.

### Scenario D: supplier order
Compare offers, place an order, confirm supplier terms, receive a partial delivery and record a discrepancy.

### Scenario E: group order
Create a group, add multiple shops, reach the target, confirm supplier terms, generate per-shop orders, allocate costs and record delivery.

## 8. Manual pilot checks

Observe real shopkeepers using their own vocabulary and normal routines. Record:
- Time to add common products.
- Time to record a sale or adjustment.
- Errors during unit selection.
- How often they work offline.
- Whether reminders are useful or noisy.
- Whether supplier listings are accurate.
- Whether group buying truly reduces delivered costs.
- Reasons for abandoned orders.

## 9. Release gate

Do not release a pilot build with known data-loss issues, duplicate stock application, cross-shop data leakage, unverified payment status, or group commitments whose financial consequences are unclear.
