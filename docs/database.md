# DukaLink Database Model

This document describes the proposed relational model. Exact fields, constraints and deletion policies should be finalised in Django models and migrations.

## 1. Core entities

### Identity and shops

**User**
- `id` (UUID recommended)
- `phone_number` (normalised, unique where required)
- `full_name`
- `is_active`
- `created_at`, `updated_at`

Use a custom Django user model before the first migration.

**Shop**
- `id`
- `name`
- `location_text`
- `latitude`, `longitude` (optional)
- `timezone`
- `created_at`, `updated_at`

**ShopMembership**
- `id`, `shop_id`, `user_id`
- `role` (owner, manager, staff)
- `status`
- `created_at`
- Unique constraint appropriate to shop/user membership.

A user can belong to multiple shops. Permissions are scoped to membership, not merely a global user role.

**Wholesaler**
- `id`, `business_name`, `contact_phone`
- `location_text`, optional coordinates
- `verification_status`
- `created_at`, `updated_at`

If wholesaler staff accounts are needed, use supplier membership records with roles rather than sharing one login.

## 2. Catalogue and units

**Product**
- `id`, `name`, optional brand/barcode/category
- `base_unit`
- `is_active`
- timestamps

**ProductUnit**
- `id`, `product_id`
- `unit_name` (e.g. kg, 50 kg sack, carton)
- `base_quantity` (decimal conversion factor)
- `is_purchase_unit`, `is_sale_unit`
- `is_active`

The canonical base unit belongs to the product. Each supported package/unit maps to a base quantity. Enforce positive conversion factors and validate supported decimal precision. Historical transactions must snapshot the conversion and unit labels used.

**ShopProduct**
- `id`, `shop_id`, `product_id`
- `quantity_base` (cached balance)
- `reorder_level_base` (nullable)
- `tracking_mode` (simple, transaction, or a setting that supports both)
- `is_active`
- timestamps

Define a uniqueness rule for the intended shop/product combination. Custom product identity and matching to shared catalogue entries should not cause accidental duplicate stock records.

## 3. Inventory ledger

**StockMovement**
- `id`
- `shop_product_id`
- `movement_type` (opening stock, purchase receipt, sale, return, damage, adjustment, reversal)
- `quantity_base_delta` (signed decimal)
- `unit_cost_base` (nullable decimal)
- `reference_type`, `reference_id`
- `idempotency_key` or reference to an operation record
- `created_by`
- `created_at`
- optional note/reason

Treat movements as append-only in normal application operations. A correction should produce a reversal or compensating movement. Use constraints and service-layer rules to prevent unsupported movement types or malformed references.

**PurchaseReceipt**
- `id`, `shop_id`, optional supplier/order reference
- `status`, `received_at`, `created_by`
- currency and total cost where known

**PurchaseItem**
- `id`, `receipt_id`, `product_id`, `product_unit_id`
- `quantity`, `quantity_base`
- `unit_cost`, `line_total`
- snapshot of unit name/conversion and product name as needed

A purchase order that has not arrived is not a stock receipt. Only actual accepted quantities should change available inventory.

**Sale**
- `id`, `shop_id`, `status`, `sold_at`, `recording_source`
- `total_amount`, `created_by`
- optional payment/settlement details if in scope

**SaleItem**
- `id`, `sale_id`, `shop_product_id`, `product_unit_id`
- `quantity`, `quantity_base`
- `unit_price`, `line_total`
- unit/conversion snapshots

**StockCount**
- `id`, `shop_id`, `status`, `started_at`, `completed_at`, `created_by`
- optional notes

**StockCountItem**
- `id`, `stock_count_id`, `shop_product_id`
- `expected_quantity_base`, `counted_quantity_base`, `variance_base`
- status and approval fields

Only an approved count should generate an adjustment movement. Preserve the expected quantity and counted quantity for audit.

**InventoryBatch** (optional MVP support for selected goods)
- `id`, `shop_product_id`, `batch_code` (optional)
- `quantity_base` or a defined batch-allocation mechanism
- `received_at`, `expiry_date`
- source receipt reference and status

If batch-level expiry is enabled, stock allocation and movement logic must account for batch quantities. Do not add a superficial expiry date field that cannot be reconciled with stock.

## 4. Supplier offers

**SupplierOffer**
- `id`, `wholesaler_id`, `product_id`, `product_unit_id`
- `price_per_unit`, `currency`
- `minimum_order_quantity`
- `available_quantity` or availability status
- delivery area/terms
- `is_active`, `updated_at`

**SupplierPriceTier** (when needed)
- `id`, `supplier_offer_id`
- `minimum_quantity`, `unit_price`
- optional validity dates

Use database constraints and server validation for positive prices, valid units and sensible minimums. A listing must show when it was last updated. Supplier availability should be reconfirmed before order acceptance.

## 5. Orders and fulfilment

**CustomerOrder**
- `id`, `shop_id`, `wholesaler_id`
- optional `group_order_id`
- `status`, `subtotal`, `delivery_fee`, `other_fees`, `total_amount`, `currency`
- destination/collection details or linked Delivery record
- `submitted_at`, `confirmed_at`, `delivered_at`
- timestamps

**OrderItem**
- `id`, `order_id`, `supplier_offer_id`
- product and unit references where appropriate
- `quantity`, `quantity_base`
- `unit_price_snapshot`, `line_total`
- product name, unit label and conversion snapshot

**Delivery**
- `id`, `order_id`, `status`, `delivery_method`
- destination/collection point
- optional route/delivery-group reference
- `delivered_at`, proof reference and discrepancy notes

A delivery can be partial. Represent received quantities and shortages explicitly rather than assuming the full order arrived.

## 6. Group buying

**GroupOrder**
- `id`, `created_by_shop_id`, `supplier_offer_id`
- `target_quantity_base`
- cached `committed_quantity_base` if needed
- `deadline`, `status`
- `estimated_delivery_fee`
- confirmed unit price and terms snapshot
- `supplier_confirmed_at`

**GroupParticipant**
- `id`, `group_order_id`, `shop_id`
- `quantity_base`, `status`
- `joined_at`, `confirmed_at`
- optional generated customer-order reference

Enforce one active commitment per shop per group using an appropriate uniqueness strategy. Updates must be validated and aggregate totals updated atomically. Cached committed quantity must be reconcilable to active participant commitments.

Group confirmation should generate individual per-shop orders so that quantities, delivery obligations and settlement can be tracked separately.

## 7. Payments and notifications

**Payment**
- `id`, `order_id`, `amount`, `currency`, `method`, `status`
- `provider_reference`, `idempotency_key`
- timestamps and reconciliation fields

For early pilots, a manual payment record may be sufficient. Live payment integration must verify provider callbacks and handle duplicate or delayed events.

**Notification**
- `id`, `user_id`, `type`, `payload`
- `channel`, `status`, `attempt_count`
- `created_at`, `sent_at`, `read_at`

**NotificationPreference**
- user/shop scope, channel preferences, reminder settings

## 8. Offline sync and idempotency

**SyncOperation** (or equivalent idempotency record)
- `id` / unique `operation_id`
- `user_id`, `shop_id`, `operation_type`
- canonical payload hash
- processing status and result reference
- received/processed timestamps

Enforce uniqueness in the database. The same key and same payload returns the original result; the same key with a different payload returns a conflict.

## 9. Audit and deletion

Keep an audit record for important changes, including actor, action, object, timestamp and relevant before/after values where appropriate. Avoid storing secrets or unnecessary personal data in audit payloads.

Prefer deactivation/soft deletion for products and suppliers referenced by historical transactions. Establish retention and account-closure rules before production.

## 10. Essential invariants

1. Stock-changing operations create movements and update cached balances in one database transaction.
2. Cached stock balances reconcile to the movement ledger.
3. Historical orders retain agreed price, unit and quantity snapshots.
4. Conversion factors must be positive and product-specific where packaging varies.
5. All writes enforce shop/supplier permissions server-side.
6. Duplicate requests cannot create duplicate movements, orders or payments.
7. A confirmed order cannot be silently edited; changes follow a documented amendment/cancellation process.
8. Group totals must reconcile to active commitments.
9. Payment success must come from verified provider evidence or authorised reconciliation.
10. Quantities and money use decimal arithmetic, not floating-point values.
