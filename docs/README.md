# DukaLink

DukaLink is a mobile-first inventory and wholesale-ordering platform for Kenyan duka owners. It combines practical stock tracking and restocking reminders with a wholesaler marketplace and coordinated group buying.

## Start here (handover documentation)

- [Getting started](getting-started.md) — run the whole system locally, smoke test, tests, troubleshooting.
- [Configuration and files](configuration.md) — every environment variable, which files are needed, what is not in Git.
- [Implemented features](features.md) — what works today, by role and module.
- [Next steps](next-steps.md) — hardening, known limitations, prioritised feature backlog, how to add a feature.
- [Deployment and operations](deployment.md) — server setup, HTTPS front door, updates, backups, problems already met.

## Planning and design documentation

- [Product plan](plan.md) — goals, scope, user journeys, rollout and success metrics.
- [Product and technical documentation](documentation.md) — requirements, architecture, business rules and API conventions.
- [Repository structure](structure.md) — recommended monorepo layout and module responsibilities.
- [Database model](database.md) — entities, relationships, constraints and inventory-ledger rules.
- [API specification](api.md) — initial REST endpoint catalogue and example payloads.
- [Implementation roadmap](implementation.md) — phased delivery, work items and exit criteria.
- [Testing strategy](testing.md) — unit, integration, security, offline and pilot testing.
- [Decisions and assumptions](decisions.md) — agreed decisions, explicit assumptions and items to validate.
- [Probable future features](probable-features.md) — candidate post-MVP ideas, provisional priorities, risks and feature gates.
- [Glossary](glossary.md) — shared domain terminology.

## MVP at a glance

**Clients**
- Android-first duka owner app (React Native + Expo).
- Wholesaler web portal.
- Lightweight administrative interface.

**Backend**
- Django + Django REST Framework.
- PostgreSQL as the authoritative data store.
- Versioned REST API under `/api/v1/`.
- Local SQLite persistence and an operation queue in the mobile app.

**MVP capabilities**
1. Shop setup and guided product/opening-stock setup.
2. Product catalogue, flexible units and product-specific conversions.
3. Stock updates and transaction-based receipts/sales, sharing one ledger.
4. Low-stock reminders, movement history and basic reports.
5. Offline inventory recording and later synchronisation.
6. Verified wholesaler listings and ordinary orders.
7. Group buying, transparent cost breakdowns and delivery coordination.
8. Basic expiry/batch support for selected goods, stock counts and gross-margin estimates, prioritised after the core inventory path.

## Scope discipline

Do not build lending, an in-app wallet/escrow, advanced accounting, AI forecasting, automatic route optimisation or multi-branch management in the initial MVP. Validate real workflows with a small mixed rural/urban pilot before expanding scope.

## Status

The probable-features document is a discovery backlog, not a commitment to implement every listed feature.

The planning documents (`plan.md`, `documentation.md`, `structure.md`, `database.md`, `api.md`, `testing.md`) began as the baseline before any code existed. The product is now built against them, so where a document and the code disagree, **the code, `decisions.md` and `features.md` win**; fix the document. Known drift: `structure.md` shows a proposed layout (for example `packages/`, `admin-web/`, per-feature mobile folders) that was not adopted; the real layout is in the root `README.md`. See `implementation.md` for phase progress.
