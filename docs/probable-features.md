# DukaLink — Probable Future Features

**Status:** Candidate roadmap, not a commitment to build every item  
**Purpose:** Capture plausible features that may become valuable after the MVP, so they are not forgotten while the first release stays focused.

This document is a discovery backlog. A feature should move into implementation only when shopkeeper/wholesaler feedback, pilot measurements, operational readiness and cost justify it. Keep the MVP plan as the source of truth for the initial release.

## 1. Prioritisation guide

- **P1 — Validate next:** likely to improve a core workflow; investigate during the pilot or soon after it.
- **P2 — Build after evidence:** useful once the core workflow is reliable and actively used.
- **P3 — Later / conditional:** potentially valuable, but has significant operational, financial, legal or technical implications.

These are provisional priorities, not delivery dates.

## 2. Inventory and shop operations

| Candidate feature | Priority | Why it may matter | Dependency or caution |
|---|---|---|---|
| Barcode scanning and product lookup | P1 | Speeds up product setup and stock updates | Catalogue matching must be reliable; allow manual entry when a code is unknown |
| Faster daily stock-entry modes | P1 | Reduces the burden of recording every sale individually | Distinguish estimates, daily totals and exact transaction records |
| Reorder suggestions based on recent usage | P1 | Helps owners decide what and how much to replenish | Start with transparent rules; do not imply AI accuracy or guaranteed availability |
| Price and purchase-cost history | P1 | Shows changing supplier prices and supports better buying decisions | Preserve historical prices; do not overwrite confirmed order terms |
| Expiry and batch alerts | P1/P2 | Helps reduce spoilage for goods with expiry dates | Start with selected goods; define batch allocation and stock-removal rules |
| Supplier/product alternatives | P2 | Suggests substitutes when a preferred item is unavailable | Owner must approve substitutions; package size and quality must be clear |
| Multiple storage locations within one shop | P2 | Useful for back rooms, shelves, kiosks or separate stores | More complex stock transfers and counts; build only if pilot shops need it |
| Shop-specific product categories and favourites | P2 | Makes large catalogues faster to use | Keep the setup lightweight |
| Printable/exportable stock and purchase reports | P1/P2 | Supports owners who still use notebooks, spreadsheets or paper | Exports must respect shop permissions and protect personal/business data |
| Supplier returns and damaged-goods claims | P2 | Makes discrepancies and returns traceable | Define evidence, approval and settlement workflows |

## 3. Purchasing, wholesalers and marketplace

| Candidate feature | Priority | Why it may matter | Dependency or caution |
|---|---|---|---|
| Better price comparison across wholesalers | P1 | Helps compare total cost, not just sticker price | Compare equivalent units, minimum quantities, delivery fees and freshness of offers |
| Wholesaler catalogue bulk upload | P1 | Reduces the effort needed to maintain large catalogues | Provide CSV/template validation and a review step before publishing |
| Price tiers and negotiated shop pricing | P1/P2 | Reflects real wholesale pricing by volume or customer agreement | Make eligibility and expiry dates explicit; avoid leaking private offers |
| Reorder from previous purchases | P1 | Makes repeat orders faster | Reconfirm availability, quantity, price and delivery terms every time |
| Purchase order and invoice documents | P2 | Helps shops and suppliers reconcile orders | Documents should reflect confirmed records and corrections |
| Supplier ratings and reliability indicators | P2 | Builds trust from real fulfilment history | Only allow feedback linked to genuine transactions; provide dispute and moderation controls |
| Supplier promotions and time-limited offers | P2 | Can surface worthwhile bulk deals | Show expiry, minimum order, delivery charges and relevant restrictions clearly |
| Supplier integration/API connections | P3 | Could keep stock and prices current automatically | Depends on supplier systems, contracts and support |
| Supplier subscriptions or marketplace fees | P3 | Could support platform sustainability | Validate willingness to pay and avoid disadvantaging small suppliers |

## 4. Group buying and delivery coordination

| Candidate feature | Priority | Why it may matter | Dependency or caution |
|---|---|---|---|
| Group recommendations by area and demand | P1/P2 | Helps nearby shops find compatible orders | Use coarse location and demand summaries; never reveal another shop's private inventory or sales |
| Reusable groups and scheduled buying days | P1/P2 | Supports predictable wholesale trips and recurring demand | Keep commitments and deadlines explicit for each cycle |
| Collection-point management | P1 | Makes pooled delivery practical, especially for rural shops | Confirm who operates the point, opening times, custody and handover records |
| Delivery status and proof of handover | P1/P2 | Reduces uncertainty about shared deliveries | Record discrepancies and partial fulfilment; protect recipient contact details |
| Fair allocation of delivery and handling costs | P1 | Ensures every participant can understand their share | Use a published deterministic formula; rounding must reconcile exactly to the total |
| Group cancellation, shortage and failed-target workflows | P1 | Makes failure cases predictable and fair | Rules must be agreed before commitments become binding |
| Driver/transport-provider portal | P2 | Could improve coordination as order volume grows | Requires operational support and clear responsibility for lost/damaged goods |
| Delivery route optimisation | P3 | May reduce cost for larger delivery volumes | Only worthwhile with reliable address data, route volume and real cost evidence |
| Recurring bulk-buying agreements | P3 | Could help regular buyers negotiate predictable terms | Avoid hidden lock-ins; define price changes, cancellations and fulfilment obligations |

## 5. Payments and financial workflows

| Candidate feature | Priority | Why it may matter | Dependency or caution |
|---|---|---|---|
| M-Pesa Daraja payment integration | P1/P2 | Could simplify paying suppliers or settling group orders | Confirm the correct business/payment model, credentials, callback verification, reconciliation and reversals before launch |
| Payment reference and reconciliation records | P1 | Helps match payments to orders even before automation | Manual records must be clearly labelled and auditable |
| Split settlement for group orders | P2 | Could help each shop pay its share separately | Must handle late payments, short payments, refunds and supplier settlement transparently |
| Downloadable receipts and statements | P1/P2 | Gives owners a usable record of purchases and payments | Do not describe an unverified payment as successful |
| Cash-flow and restocking budget view | P2 | Helps owners plan purchasing within a chosen budget | Show recorded facts separately from forecasts or estimates |
| Simple profit and loss summaries | P2 | May help owners understand business performance | Requires reliable costs, stock valuation and sales data; not a substitute for professional accounting |
| Supplier credit terms and payment due dates | P3 | May support established wholesaler relationships | Requires explicit agreements, permissions, reminders and careful dispute handling |
| Lending, credit scoring or buy-now-pay-later | P3 / separate product decision | Could address working-capital needs | Not part of the MVP; significant consumer-protection, regulatory, affordability, collections and reputational risks. Do not infer creditworthiness from private shop data without an explicit, lawful basis |
| Stored-value wallet or escrow | P3 / separate product decision | Could centralise group-order settlement | Not part of the MVP; requires legal, security, safeguarding and operational review. Prefer direct provider payments until a clear need is proven |

## 6. Notifications, accessibility and connectivity

| Candidate feature | Priority | Why it may matter | Dependency or caution |
|---|---|---|---|
| SMS notifications | P1/P2 | Reaches users with limited data access | Message cost, consent, delivery failures and opt-out controls |
| WhatsApp notifications or supplier communication | P2 | Uses a familiar communication channel | Provider rules, opt-in consent, template constraints and per-message cost |
| Push notifications | P2 | Useful for timely alerts on installed apps | Must not be the only channel for critical order information |
| Kiswahili and other local-language support | P1/P2 | Makes onboarding and routine use easier for more shopkeepers | Validate translations with actual users; support clear number, unit and date formats |
| Low-data mode and smaller downloads | P1 | Improves usability on constrained connections | Cache only what is needed and handle stale data honestly |
| Voice-assisted entry or read-aloud support | P3 | Could help users who prefer speech or have accessibility needs | Noisy shop environments, language accuracy and privacy need testing |
| Guided help, tutorials and support requests | P1/P2 | Reduces onboarding friction and support burden | Keep guidance aligned with the actual version and user role |
| Multi-device access for the same shop | P2 | Lets owners and authorised staff use different devices | Requires robust session management, role permissions and conflict handling |

## 7. Analytics and decision support

| Candidate feature | Priority | Why it may matter | Dependency or caution |
|---|---|---|---|
| Reorder recommendations using sales history | P1/P2 | Can reduce stockouts and over-ordering | Begin with understandable thresholds and recent usage; account for seasonality and missing records |
| Stockout and dead-stock reports | P1/P2 | Identifies unavailable or slow-moving products | Avoid treating incomplete records as complete truth |
| Delivered-cost savings report for group buying | P1 | Tests whether group buying really saves money | Compare against a documented alternative and include transport, handling and other fees |
| Supplier fulfilment and price reliability dashboard | P2 | Helps identify consistently reliable suppliers | Use fair, explainable metrics and enough transactions to avoid misleading rankings |
| Community-level demand summaries | P2/P3 | May help wholesalers plan stock and delivery days | Aggregate and anonymise; do not expose identifiable shop-level sales or inventory |
| Predictive demand forecasting | P3 | Could improve ordering once data quality is strong | Needs sufficient historical data and evaluation against simple baselines; label predictions as estimates |
| Automated anomaly or fraud detection | P3 | Could identify unusual activity or suspicious supplier behaviour | Human review, explainability and false-positive handling are essential |

## 8. Roles, administration, trust and integrations

- **Staff roles and approvals (P1/P2):** separate owner, manager and stock-entry permissions; require approval for sensitive actions where justified.
- **Supplier verification workflow (P1):** record evidence, review status, expiry/re-check dates and suspension reasons without exposing sensitive verification documents publicly.
- **Disputes and support cases (P1/P2):** track shortages, damaged goods, missed delivery, refund requests, evidence, decisions and resolution times.
- **Data export and account closure (P1):** let authorised users export their business data and understand what is retained for legitimate operational or legal reasons.
- **Audit and security administration (P1):** monitor privileged actions, suspicious login activity, sync failures, backups and restoration tests.
- **POS or receipt integration (P2/P3):** import sales from compatible point-of-sale systems if pilot users already use them.
- **Accounting integrations (P3):** export or synchronise verified records to accounting tools only after the underlying data and mappings are reliable.
- **Public product API and partner integrations (P3):** introduce only with authentication, rate limits, versioning, documentation and access scopes.
- **Multi-branch inventory (P3):** support transfers, branch-specific permissions and consolidated reports only after single-shop workflows are stable.

## 9. Recommended feature gates

Before a candidate enters the committed roadmap, answer:

1. **User evidence:** Which shopkeepers or wholesalers asked for it, and how often does the problem occur?
2. **Impact:** Which measurable problem will it improve—time, stock accuracy, fulfilment, cost or retention?
3. **Data readiness:** Are the underlying records accurate enough to support it?
4. **Operational readiness:** Who handles support, disputes, exceptions and failures?
5. **Cost:** What are the development, hosting, messaging, payment and ongoing support costs?
6. **Risk:** Does it add privacy, financial, regulatory or safety responsibilities?
7. **Scope:** Can a simpler manual workflow test the value first?

## 10. Suggested sequencing after the MVP

1. **Pilot fixes first:** usability, offline-sync reliability, stock accuracy, supplier offer freshness and failed-order handling.
2. **Make repeat work easier:** reorder from previous purchases, better catalogue imports, price history, exports and low-data/local-language improvements.
3. **Prove group-buying economics:** collection-point operations, delivery evidence, cost allocation and delivered-cost comparisons.
4. **Automate carefully:** notifications and M-Pesa integration after consent, reconciliation and support procedures are ready.
5. **Add decision support:** transparent reorder suggestions and supplier reliability metrics before advanced prediction.
6. **Consider larger business features last:** integrations, multi-branch operations, credit or escrow only after dedicated discovery and risk review.

## 11. Explicitly not promised

Including a feature here does **not** mean it is approved, funded, scheduled or guaranteed to be built. The product owner should update this document after pilot reviews, mark decisions as accepted/rejected/deferred, and move only validated work into `plan.md` and `implementation.md`.
