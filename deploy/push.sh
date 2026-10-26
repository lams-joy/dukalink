#!/usr/bin/env bash
# Usage: ./push.sh user@SERVER [/srv/dukalink]   (uploads and (re)starts DukaLink; touches nothing else)
set -euo pipefail
HOST="${1:?usage: ./push.sh user@SERVER [remote_dir]}"
DIR="${2:-/srv/dukalink}"
cd "$(dirname "$0")/.."
[ -d deploy/www/app ] && [ -d deploy/www/wholesale ] || { echo "Run deploy/build-web.sh first."; exit 1; }
[ -f deploy/.env ] || { echo "Run deploy/make-env.sh yourdomain.com first."; exit 1; }
ssh "$HOST" "test -w '$DIR' || { echo 'Cannot write to $DIR. Run once: sudo mkdir -p $DIR && sudo chown \$USER $DIR'; exit 1; }; mkdir -p '$DIR/backend' '$DIR/deploy/www'"
rsync -az --delete --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' --exclude 'db.sqlite3' \
  --exclude 'staticfiles' --exclude '.pytest_cache' --exclude '.ruff_cache' backend/ "$HOST:$DIR/backend/"
rsync -az --exclude www deploy/ "$HOST:$DIR/deploy/"
rsync -az --delete deploy/www/ "$HOST:$DIR/deploy/www/"
ssh "$HOST" "cd '$DIR/deploy' && docker compose up -d --build && docker compose ps"
