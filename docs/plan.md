# DukaLink MVP Product Plan

**Status:** Proposed MVP baseline  
**Market:** Kenyan dukas and wholesalers  
**Clients:** Android-first mobile app + wholesaler web portal  
**Pilot:** Mixed rural and urban shops

## 1. Product vision

Help duka owners know what stock they have, what is running low, and where to replenish it. Make it easier to find reliable wholesalers and allow nearby shops to combine demand when doing so reduces the total delivered cost.

The inventory product must be useful on its own. Group buying is a differentiator built on top of trustworthy inventory and supplier-order workflows.

## 2. Problem statement

Duka owners may track stock informally, forget when to restock, struggle to compare suppliers, travel to wholesale markets, or pay high delivery costs for small orders. Rural shops may have particular difficulty assembling an economical order, while urban shops may benefit from convenient supplier comparisons and quick replenishment.

These are hypotheses to validate with shopkeepers and wholesalers, not assumptions to treat as proven facts.

## 3. Target users

### Duka owner or manager
Needs fast stock recording, simple low-stock alerts, useful purchase history and trustworthy supplier options.

### Duka staff member
May record receipts, sales and stock counts but should only have the permissions assigned by the shop owner.

### Wholesaler
Needs a practical way to publish catalogue items, prices, packaging units, minimum quantities, availability, delivery areas and order status.

### Platform administrator
Verifies suppliers, handles reports and disputes, and monitors platform integrity.

## 4. MVP goals

1. Make stock records easy enough for a shopkeeper to maintain.
2. Support both simple stock adjustments and transaction-based receipts/sales.
3. Correctly convert purchase units into stock units (e.g. a 50 kg sack into kilograms).
4. Alert users when stock reaches a configured threshold.
5. Let shops discover suppliers and submit ordinary orders.
6. Let shops coordinate group orders with clear commitments, costs and delivery terms.
7. Support inventory operations during intermittent connectivity.
8. Measure whether the product saves time, reduces stock discrepancies or lowers delivered purchasing costs.

## 5. Non-goals for the first release

- Lending, credit scoring or buy-now-pay-later.
- Stored-value wallet or escrow service.
- Full accounting, payroll or tax filing.
- AI demand forecasting.
- Automated fleet management or route optimisation.
- Multi-branch enterprise inventory.
- Mandatory per-item scanning for every sale.
- Automatic access to M-Pesa balances.
- Claims of guaranteed savings.

## 6. Core user journeys

### New shop setup
Register → create shop → set location and details → choose recording preference → select or create products → enter opening quantities and units → set optional reorder thresholds → review and save.

Unknown values such as purchase cost or reorder threshold may be skipped. Never invent opening quantities.

### Inventory update
Find product → choose simple adjustment or transaction → enter quantity and unit → preview conversion → confirm → see updated balance and movement history.

### Purchase and sale units
Example: receive one sack of sugar (50 kg) at KSh 7,000. The stock ledger adds 50 kg. A sale of 1.5 kg reduces stock by 1.5 kg. Remaining stock is 48.5 kg if there was no prior stock. Effective receipt cost is KSh 140/kg before other costs.

### Restocking
Low-stock alert → review needed quantity → compare supplier offers → choose individual or group order → confirm terms → track fulfilment → record received quantities.

### Group order
Create or join group → select quantity → view target progress and estimated costs → supplier confirms availability and terms → participants confirm binding orders → fulfilment/delivery → each shop records its own receipt.

## 7. MVP feature scope

### Inventory — release-critical
- Shared product catalogue plus shop-specific products.
- Custom products when catalogue matches are unavailable.
- Base units and product-specific unit conversions.
- Opening stock, receipts, sales, returns, damage, adjustments and reversals.
- Append-only movement history with cached current balance.
- Low-stock thresholds and de-duplicated alerts.
- Basic physical stock count and discrepancy approval.
- Basic inventory and movement summary.
- Offline local persistence and explicit sync status.

### Useful early additions
- Optional expiry/batch records for selected goods.
- Basic estimated gross-margin reporting when cost data is reliable.
- Saved replenishment lists.
- Manual restocking budget field.
- Barcode lookup/scanning where a reliable catalogue match exists.

### Marketplace
- Supplier onboarding and verification status.
- Supplier profiles and searchable offers.
- Product/package units, price tiers, minimum order quantities, availability and delivery areas.
- Ordinary order submission, confirmation, dispatch, delivery receipt and discrepancy reporting.
- Agreed price/quantity snapshots on orders.
- Supplier cancellation and fulfilment history.

### Group buying
- Create and discover open groups.
- Quantity commitments in canonical units.
- Deadline, target and minimum order validation.
- Participant changes/withdrawal before the binding cutoff.
- Supplier confirmation before final commitment.
- Per-shop order generation and transparent goods/delivery cost breakdown.
- Collection point or delivery option recorded for the group.
- Manual coordination is acceptable during the first pilot.

### Platform foundations
- Shop-scoped permissions.
- Audit trail.
- Idempotent write operations and offline sync operation IDs.
- Notification preferences.
- Data export.
- Backups and restore tests.
- Lightweight admin tools for supplier verification and dispute triage.

## 8. Product principles

- **Fast first:** routine stock actions should require few steps.
- **Honest data:** distinguish recorded transactions from estimates.
- **Offline-aware:** local saves must be clearly distinguished from server-confirmed actions.
- **Transparent cost:** show goods, delivery, handling and other known fees.
- **No hidden commitments:** joining a group is not binding until the stated confirmation point.
- **Privacy:** do not expose one shop's individual sales or inventory to other shops.
- **Human override with audit:** corrections are possible but should preserve history.
- **Low-cost operations:** favour simple, maintainable infrastructure for the pilot.

## 9. Pilot design

Initial learning cohort: approximately 15–25 shops across rural and urban settings, plus 3–5 wholesalers, subject to recruitment. This is a practical learning cohort, not a statistically representative sample.

### Urban hypotheses
Supplier discovery and comparisons save time; individual delivery may already be competitive; rapid replenishment matters.

### Rural hypotheses
Poor connectivity, travel costs and small order sizes create opportunities for pooled ordering and shared collection/delivery.

### Measure
- Weekly active shops and retention.
- Stock-count discrepancy rate.
- Percentage of alerts acted upon.
- Time to record opening stock and routine changes.
- Offer accuracy and order fulfilment rate.
- Group-order completion rate.
- Actual delivered cost versus the shop's normal alternative.
- Net savings after all transport and handling fees.
- Repeat ordering without manual intervention.

## 10. MVP success gates

Set baselines before the pilot. Review after several weeks of real use. Do not use registration count alone as success.

Suggested initial gates to agree with the pilot team:
- Shops can complete setup without developer assistance.
- Duplicate requests do not duplicate stock or orders.
- Core inventory works without internet and syncs without silent data loss.
- Supplier order terms are visible and preserved.
- Every completed group order has a recorded cost breakdown and fulfilment outcome.
- The team can explain stock discrepancies and failed synchronisations.
- At least some shops repeat the core workflow voluntarily.

Numeric targets should be set after baseline interviews and early pilot observations.

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Owners find recording too slow | Test one-tap adjustments, quick quantities and daily-total mode; label estimates honestly |
| Incorrect unit conversions | Product-specific conversion definitions, preview and validation tests |
| Stale supplier listings | Last-updated timestamp, confirmation before order acceptance, supplier performance history |
| Group order fails to reach target | Deadline rules, no premature binding commitment, clear fallback/cancellation |
| Offline conflicts | Unique operation IDs, server-side ledger, explicit conflict responses |
| Fake or unreliable suppliers | Verification, transaction-linked feedback, reporting and suspension process |
| Savings are overstated | Compare delivered cost against a documented alternative including all fees |
| Feature creep | Keep non-goals explicit and review additions against pilot evidence |

## 12. Release strategy

1. Internal inventory prototype.
2. Small usability test with a few shopkeepers.
3. Inventory pilot with offline sync and stock-count workflows.
4. Supplier catalogue and ordinary ordering with selected wholesalers.
5. Manually coordinated group-buying pilot.
6. Review evidence, then decide which automation/features deserve investment.
