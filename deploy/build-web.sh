#!/usr/bin/env bash
# Builds the shop app and the wholesaler portal against PUBLIC_API_URL from .env.
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "Run ./make-env.sh yourdomain.com first."; exit 1; }
API="$(grep -E '^PUBLIC_API_URL=' .env | cut -d= -f2-)"
ROOT="$(cd .. && pwd)"
echo "Building both web apps for $API"

cd "$ROOT/apps/mobile"
[ -d node_modules ] || npm install --no-audit --no-fund
rm -rf dist
EXPO_PUBLIC_API_URL="$API" npx expo export --platform web
rm -rf "$ROOT/deploy/www/app" && mkdir -p "$ROOT/deploy/www" && cp -r dist "$ROOT/deploy/www/app"
rm -rf dist .expo

cd "$ROOT/apps/wholesaler-web"
[ -d node_modules ] || npm install --no-audit --no-fund
VITE_API_URL="$API" npm run build
rm -rf "$ROOT/deploy/www/wholesale" && cp -r dist "$ROOT/deploy/www/wholesale"
rm -rf dist
echo "Done. Built files are in deploy/www/"
