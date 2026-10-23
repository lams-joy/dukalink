# DukaLink REST API Contract (Initial)

Base path: `/api/v1/`  
Format: JSON  
Authentication: secure session or token-based authentication; final mechanism to be selected before implementation.

This is the endpoint catalogue. The OpenAPI schema is generated from the code (`/api/schema/`, browsable at `/api/docs/`); this file is the human-readable summary of behaviour and rules.

## 1. Authentication and shops

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/auth/register/` | Register |
| POST | `/auth/login/` | Authenticate |
| POST | `/auth/refresh/` | Refresh token, if JWT is selected |
| GET | `/me/` | Current user |
| POST | `/shops/` | Create shop |
| GET | `/shops/` | List accessible shops |
| GET/PATCH | `/shops/{shop_id}/` | Read/update shop |
| POST | `/shops/{shop_id}/members/` | Add/invite member |
| GET | `/catalog/products/` | Search shared catalogue |
| POST | `/shops/{shop_id}/onboarding/complete/` | Complete setup |

## 2. Inventory

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/shops/{shop_id}/inventory/` | List stock |
| POST | `/shops/{shop_id}/inventory/` | Add tracked product |
| GET | `/shops/{shop_id}/inventory/{item_id}/` | Stock detail |
| PATCH | `/shops/{shop_id}/inventory/{item_id}/settings/` | Threshold/tracking settings |
| POST | `/shops/{shop_id}/stock-adjustments/` | Record correction |
| POST | `/shops/{shop_id}/purchase-receipts/` | Record goods actually received |
| POST | `/shops/{shop_id}/sales/` | Record sale |
| GET | `/shops/{shop_id}/stock-movements/` | Movement history |
| POST | `/shops/{shop_id}/stock-counts/` | Start count |
| POST | `/shops/{shop_id}/stock-counts/{id}/submit/` | Submit count |
| POST | `/shops/{shop_id}/stock-counts/{id}/approve/` | Approve variance |
| GET | `/shops/{shop_id}/alerts/` | Low-stock/expiry alerts |
| GET | `/shops/{shop_id}/reports/summary/` | Basic summary |
| POST | `/shops/{shop_id}/sync/` | Submit offline operations |

## 3. Marketplace and orders

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/marketplace/offers/` | Search offers |
| GET | `/marketplace/offers/{offer_id}/` | Offer detail |
| GET | `/marketplace/wholesalers/` | Discover wholesalers |
| GET | `/marketplace/wholesalers/{id}/` | Supplier profile |
| POST | `/wholesaler/offers/` | Create offer |
| PATCH | `/wholesaler/offers/{id}/` | Update offer |
| GET | `/wholesaler/orders/` | Supplier orders |
| POST | `/shops/{shop_id}/orders/` | Place ordinary order |
| GET | `/shops/{shop_id}/orders/` | Shop order history |
| GET | `/orders/{order_id}/` | Order detail |
| POST | `/orders/{order_id}/cancel/` | Request cancellation |
| POST | `/wholesaler/orders/{id}/confirm/` | Confirm stock/terms |
| POST | `/wholesaler/orders/{id}/dispatch/` | Mark dispatched |
| POST | `/orders/{id}/receive/` | Record receipt and discrepancies |

## 4. Group buying

Shop side (`/shops/{shop_id}/group-orders/...`; owner/manager act, staff only view):

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/group-orders/` | Create group (the organiser commits straight away) |
| GET | `/group-orders/` | Open groups to join; `?mine=true` for groups this shop took part in |
| GET | `/group-orders/{id}/` | Group detail/progress, lifecycle status and, once confirmed, the frozen `terms` |
| POST | `/group-orders/{id}/join/` | Commit quantity (not binding) |
| PATCH | `/group-orders/{id}/my-commitment/` | Change own commitment while open |
| POST | `/group-orders/{id}/withdraw/` | Withdraw while open |
| POST | `/group-orders/{id}/cancel/` | Organiser cancels while open (`reason` required) |
| POST | `/group-orders/{id}/close/` | Organiser closes early once the target is met |
| GET | `/group-orders/{id}/cost-breakdown/` | Once confirmed: group totals plus this shop's own line (`mine`); never other shops' lines |

Wholesaler side (`/wholesalers/{wholesaler_id}/group-orders/...`; owner/manager decide, staff only view; totals only, never which shops took part):

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/group-orders/` | This wholesaler's groups; `?status=` filters |
| GET | `/group-orders/{id}/` | Group detail |
| POST | `/group-orders/{id}/confirm/` | **Binding point.** Accept the full committed quantity. Optional `unit_price` (at most the tier price for the committed total) and `delivery_fee` (at most the published estimate, default 0) |
| POST | `/group-orders/{id}/decline/` | Turn a closed group down (`reason` required). Final |
| GET | `/group-orders/{id}/cost-breakdown/` | Once confirmed: group totals plus one row per generated order |

Lifecycle: `open` -> `closed` (deadline with target met, or organiser closes) -> `confirmed` or `declined`; `open` -> `failed` (deadline, target missed) or `cancelled`. Only `confirmed` is binding. Expired groups are settled lazily on the next read or write; `python manage.py close_expired_groups` settles the rest (run it from cron, e.g. every 5 minutes).

Errors specific to groups: `group_not_open`, `invalid_transition` (409); `target_not_reached`, `price_above_cap`, `fee_above_cap`, `exceeds_availability`, `reason_required` (400).

Confirming generates one ordinary order per active participant, already `confirmed`, in the same transaction (all or nothing). They appear in the normal order lists and continue through dispatch and receipt. Each carries the same unit price and that shop's delivery share. For a collection group the order's `delivery_address` holds the collection point. The cost breakdown reads frozen figures, so later offer edits or order cancellations never rewrite what was agreed (the live `order_status` is shown alongside). Cost breakdown before confirmation returns 409 `not_confirmed`.

## 5. Notifications and administration

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/notifications/` | List notifications |
| POST | `/notifications/{id}/read/` | Mark read |
| GET | `/admin/suppliers/pending/` | Review suppliers |
| POST | `/admin/suppliers/{id}/verify/` | Verify supplier |
| POST | `/admin/suppliers/{id}/suspend/` | Suspend supplier |

Payment endpoints and provider webhooks should be added in the payment milestone, after the settlement model and provider requirements are confirmed. Do not implement a placeholder callback that trusts a client-provided success flag.

## 6. Example: receive a sack of sugar

`POST /api/v1/shops/{shop_id}/purchase-receipts/`

```json
{
  "idempotency_key": "receipt-operation-uuid",
  "supplier_name": "Example Wholesale",
  "items": [
    {
      "product_id": "product-sugar-id",
      "product_unit_id": "unit-50kg-sack-id",
      "quantity": "1",
      "unit_cost": "7000.00"
    }
  ]
}
```

The server resolves the conversion and records 50 kg of base inventory. It should generate the actual receipt identifier server-side. A retry with the same idempotency key and payload returns the original result, not a second receipt.

## 7. Example: record a sale

`POST /api/v1/shops/{shop_id}/sales/`

```json
{
  "idempotency_key": "sale-operation-uuid",
  "items": [
    {
      "shop_product_id": "shop-sugar-id",
      "product_unit_id": "unit-kg-id",
      "quantity": "1.500",
      "unit_price": "180.00"
    }
  ]
}
```

For 50 kg in stock, the successful sale leaves 48.5 kg. The sale, sale item, movement and cached balance update must commit atomically.

## 8. Example: join a group

`POST /api/v1/group-orders/{group_order_id}/join/`

```json
{
  "idempotency_key": "group-join-operation-uuid",
  "quantity": "2",
  "product_unit_id": "unit-50kg-sack-id"
}
```

The server converts the commitment to the group's canonical unit, checks deadline and status, and updates the commitment aggregate atomically. Progress is calculated server-side.

## 9. Offline sync

`POST /api/v1/shops/{shop_id}/sync/`

```json
{
  "operations": [
    {
      "operation_id": "offline-operation-uuid",
      "type": "stock_adjustment",
      "created_at": "2026-10-21T18:30:00Z",
      "payload": {
        "shop_product_id": "shop-product-id",
        "quantity_delta": "-2.000",
        "reason": "physical_count"
      }
    }
  ]
}
```

Return a result per operation with statuses such as `accepted`, `duplicate`, `conflict` or `rejected`. Preserve the original operation type. A sale must not be disguised as a stock adjustment.

## 10. Standard error and behaviour rules

- `400`: invalid payload or field validation failure.
- `401`: unauthenticated.
- `403`: authenticated but not authorised.
- `404`: resource not found or intentionally concealed by permission policy.
- `409`: idempotency payload conflict, stock conflict or invalid state transition.
- `422`: optional convention for semantically invalid operations if adopted consistently.
- `429`: rate limit.
- `5xx`: unexpected server error; return a trace/correlation ID without leaking internals.

Choose one error envelope and use it consistently. Publish pagination and filtering conventions in OpenAPI.

## 11. API security checklist

- Validate shop and supplier permissions on every resource.
- Validate all prices, units, quantities and status transitions server-side.
- Rate-limit authentication and public search endpoints.
- Require idempotency on non-idempotent writes.
- Verify provider callbacks before adding payment endpoints.
- Do not expose secrets, internal stack traces or another shop's data.
