#!/usr/bin/env bash
# Database backup (run on the server). Keeps the last 14 files in ~/backups.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p "$HOME/backups"
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$HOME/backups/dukalink-$(date +%F).sql.gz"
ls -1t "$HOME"/backups/dukalink-*.sql.gz | tail -n +15 | xargs -r rm --
echo "Backup saved: $(ls -1t "$HOME"/backups/dukalink-*.sql.gz | head -1)"
