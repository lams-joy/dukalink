# DukaLink app (Expo)

One codebase for the browser and for Expo Go on a phone. Slice 3a: sign in and list your shops.

## Run it
```bash
# backend (another terminal): python manage.py runserver   -> http://localhost:8000
npm install
npm run web          # opens http://localhost:8081 in the browser
```
`npx expo start` shows both options: press `w` for the browser, or scan the QR code with Expo Go
(the phone must be on the same network as the PC, which is not possible at the lab).

## Phone (Expo Go) at home
1. Start Django so the network can reach it: `python manage.py runserver 0.0.0.0:8000`, and add the
   PC's address to `DJANGO_ALLOWED_HOSTS` (for example `localhost,127.0.0.1,192.168.1.20`).
2. `EXPO_PUBLIC_API_URL=http://192.168.1.20:8000/api/v1 npx expo start`

## Make a test user and shop
```bash
curl -s -X POST localhost:8000/api/v1/auth/register/ -H 'Content-Type: application/json' \
  -d '{"phone_number":"0712345678","full_name":"Test Owner","password":"a-long-test-password-1"}'
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login/ -H 'Content-Type: application/json' \
  -d '{"phone_number":"0712345678","password":"a-long-test-password-1"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access"])')
curl -s -X POST localhost:8000/api/v1/shops/ -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"name":"Amina Duka","location_text":"Kisumu"}'
```
