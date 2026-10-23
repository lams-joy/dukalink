# DukaLink Repository Structure

This is the recommended starting monorepo layout. It is a proposal; adapt it to an existing repository if one is already established rather than moving or overwriting working code blindly.

```text
dukalink/
├── README.md
├── plan.md
├── documentation.md
├── structure.md
├── database.md
├── api.md
├── implementation.md
├── testing.md
├── decisions.md
├── glossary.md
├── .gitignore
├── .editorconfig
├── .env.example
├── compose.yaml
├── docs/
│   ├── product/
│   ├── architecture/
│   ├── api/
│   ├── operations/
│   └── research/
├── apps/
│   ├── mobile/                   # React Native + Expo + TypeScript
│   │   ├── app/                  # Expo Router routes/layouts
│   │   ├── src/
│   │   │   ├── api/              # Typed API client
│   │   │   ├── db/               # SQLite schema/repositories
│   │   │   ├── sync/             # Offline queue and reconciliation
│   │   │   ├── features/
│   │   │   │   ├── onboarding/
│   │   │   │   ├── inventory/
│   │   │   │   ├── sales/
│   │   │   │   ├── restocking/
│   │   │   │   ├── marketplace/
│   │   │   │   ├── group-buying/
│   │   │   │   └── notifications/
│   │   │   ├── components/
│   │   │   ├── theme/
│   │   │   └── types/
│   │   ├── assets/
│   │   ├── tests/
│   │   └── package.json
│   ├── wholesaler-web/            # React + TypeScript
│   │   ├── src/
│   │   │   ├── api/
│   │   │   ├── features/
│   │   │   │   ├── onboarding/
│   │   │   │   ├── catalogue/
│   │   │   │   ├── orders/
│   │   │   │   └── fulfilment/
│   │   │   ├── components/
│   │   │   └── routes/
│   │   └── package.json
│   └── admin-web/                 # Small internal admin interface
│       ├── src/
│       └── package.json
├── backend/
│   ├── manage.py
│   ├── pyproject.toml
│   ├── config/                    # Django settings/URLs/ASGI/WSGI
│   ├── apps/
│   │   ├── accounts/
│   │   ├── shops/
│   │   ├── catalog/
│   │   ├── inventory/
│   │   ├── suppliers/
│   │   ├── orders/
│   │   ├── groupbuying/
│   │   ├── notifications/
│   │   ├── sync/
│   │   ├── audit/
│   │   └── payments/              # Add provider integration when scheduled
│   └── tests/
├── packages/
│   └── api-types/                 # Generated/shared API types if useful
├── scripts/
│   ├── dev-setup.sh
│   └── seed_demo_data.py
└── infra/
    ├── docker/
    ├── deployment/
    └── monitoring/
```

## Backend app responsibilities

### `accounts`
Custom user model, authentication, recovery and account status.

### `shops`
Shop profiles, shop memberships, roles, settings and location.

### `catalog`
Shared product identity, categories, base units and supported product units/conversions.

### `inventory`
Shop-specific products, movements, receipts, sales, adjustments, stock counts, batches and low-stock rules.

### `suppliers`
Wholesaler profile, verification, offers, availability, minimum order sizes and pricing tiers.

### `orders`
Ordinary orders, order item snapshots, confirmation, delivery, receipts and discrepancies.

### `groupbuying`
Group orders, participant commitments, deadlines, supplier confirmation and cost allocation.

### `notifications`
Notification records, preferences, delivery attempts and retries.

### `sync`
Idempotency keys, offline operation processing and conflict responses. Keep stock business rules in the relevant domain; sync should route operations to those services.

### `audit`
Structured records of sensitive actions. Avoid treating general application logs as the only audit trail.

### `payments`
Provider integrations, callbacks, payment state and reconciliation. Add when the pilot's order/settlement workflow is ready; manual payment recording can precede live integration.

## Dependency direction

- `catalog` defines product and unit concepts.
- `inventory` depends on catalog and shop access.
- `suppliers` depends on catalog and supplier identity.
- `orders` depends on shops, supplier offers and catalog snapshots.
- `groupbuying` coordinates offers, participants and orders.
- `notifications` can receive events from other domains but should not own their business rules.
- `sync` delegates to domain services rather than duplicating domain logic.

Avoid circular app dependencies. Keep business operations in service functions or domain-specific modules, and keep API views/controllers thin.

## Naming conventions

- Django apps and Python modules: `snake_case`.
- Database tables: Django defaults unless a deliberate naming standard is adopted.
- REST resources: plural nouns.
- API version: `/api/v1/`.
- Tests: close to the domain or in a clear `tests/` package.
- Environment variables: uppercase with underscores.
- Do not commit `.env`, signing keys, database dumps or real customer data.

## Start smaller if needed

For a small team, `admin-web` can initially use Django Admin with strict permissions. Do not build a custom admin frontend until actual operations show that Django Admin is insufficient.
