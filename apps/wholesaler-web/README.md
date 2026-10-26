# DukaLink wholesaler portal (React + Vite)

Styled with the same "liquid glass" look as the mobile app (`src/styles.css`; shared components in
`src/ui.tsx`). Talks to the same Django API as the mobile app.

## Run it
```bash
# backend: python manage.py runserver   -> http://localhost:8000   (CORS must allow http://localhost:5173)
cp .env.example .env          # optional
npm install
npm run dev                   # http://localhost:5173
npm run build                 # typecheck + production build
```

## Pages
| Route | What it does |
|---|---|
| `/login`, `/register` | Account |
| `/` , `/new` | Your wholesale businesses, register one (needs platform verification before shops see offers) |
| `/w/:id` | Dashboard: verification status, open orders, groups waiting for a decision |
| `/w/:id/offers`, `/new`, `/:offer` | List offers; create from the catalogue; edit price, availability, visibility, volume tiers |
| `/w/:id/orders` | Incoming orders: confirm (with delivery fee), reject, dispatch, cancel |
| `/w/:id/settings` | Edit business, add team members, activity log |
| `/admin` | Platform staff: verify or suspend pending suppliers (403 for everyone else) |
| `/admin/catalogue`, `/new`, `/:id` | Platform staff: maintain the shared product catalogue and its units |
| `/w/:id/groups`, `/:group` | Group buys: confirm (binding) or decline, view agreed terms |

## Not built yet
Separate order detail page (the list already shows full order details), reports, notifications.
