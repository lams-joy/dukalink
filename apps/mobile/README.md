# DukaLink app (Expo)

One codebase for the browser and for Expo Go on a phone. Styled with a "liquid glass" theme:
shared building blocks are in `src/ui.tsx` and the colours/spacing in `src/theme.ts`. Change those first,
then individual screens.

## Run it
```bash
# backend (another terminal, from dukalink/backend): python manage.py runserver   -> http://localhost:8000
cp .env.example .env        # optional; default API is http://localhost:8000/api/v1
npm install
npm run web                 # http://localhost:8081 in the browser
npm start                   # press w for browser, or scan the QR with Expo Go
npm run typecheck
```
If Expo complains about a version mismatch, run `npx expo install --fix`.

## Phone (Expo Go) at home
1. `python manage.py runserver 0.0.0.0:8000` and add the PC's address to `DJANGO_ALLOWED_HOSTS`
   (for example `localhost,127.0.0.1,192.168.1.20`).
2. `EXPO_PUBLIC_API_URL=http://192.168.1.20:8000/api/v1 npx expo start`

The browser build calls the API from another origin, so the backend must allow it via `CORS_ALLOWED_ORIGINS` (already the default in DEBUG).

## Screens (Expo Router, `app/`)
| Route | What it does |
|---|---|
| `/login`, `/register` | Sign in / create account (JWT, silent refresh) |
| `/shops`, `/shops/new` | Your shops, create a shop |
| `/shops/[id]` | Shop home: summary numbers and links to everything below |
| `inventory`, `inventory/[item]`, `inventory/add` | Stock list + search, correct stock / reorder level, track a catalogue product with opening stock |
| `sell`, `receive` | Record a sale, record goods received (unit conversion done by the server) |
| `alerts`, `movements` | Low-stock alerts, stock history |
| `market`, `market/[offer]` | Browse offers, get a price quote, place an order |
| `orders` | Order history, cancel, mark received in full |
| `orders/[order]` | Order detail, confirm delivery with per-item quantities (shortages), cancel with reason |
| `groups`, `groups/new`, `groups/[group]` | Open / my group buys, start one, join, change or withdraw, organiser close/cancel, cost breakdown |
| `counts`, `counts/[count]` | Stock counts: start, enter counted quantities, submit, manager approve/cancel |
| `inventory/new-product` | Add your own product with custom units |
| `movements` | History, manager reversal of mistakes (with reason) |
| `market/wholesalers` | Verified wholesaler directory |
| `queue` | Records saved offline: sync now, review failures, discard |
| `settings` | Edit shop, tracking mode, add team members, finish setup, activity log |

## Code map
- `src/api.ts`: fetch client (bearer token, one refresh retry, error envelope, pagination, idempotency keys)
- `src/auth.tsx`: sign-in state; `app/_layout.tsx` redirects signed-out users to `/login`
- `src/ui.tsx`: unstyled Screen/Field/Btn/useLoad/useAction used everywhere
- `src/units.ts`: finds a product's units for sale/receipt forms

## Offline
Sales, goods received and stock corrections are sent normally when online. If the network is down they are
saved on the device (AsyncStorage) and replayed through `/shops/{id}/sync/` when the shop home opens or
"Sync now" is pressed. Each record's id is its idempotency key, so replays never double-apply.
Stock counts, orders and group buys need a connection.

## Not built yet
Notifications (no backend endpoint yet), adding units to an existing product, product search by barcode scan,
an offline read cache (lists need a connection), wholesaler/admin screens (see `apps/wholesaler-web`).

## Make a test user and shop
```bash
curl -s -X POST localhost:8000/api/v1/auth/register/ -H 'Content-Type: application/json' \
  -d '{"phone_number":"0712345678","full_name":"Test Owner","password":"a-long-test-password-1"}'
```
(or just use the Register screen).
