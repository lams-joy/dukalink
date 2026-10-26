#!/usr/bin/env bash
# Usage: ./make-env.sh yourdomain.com [lan]
#   (no 2nd arg)  public mode: https://api.D  https://app.D  https://wholesale.D   (your front door adds HTTPS)
#   lan           test mode on your home network: http://api.D:3007 etc (add the names to /etc/hosts)
# Safe to re-run: existing secrets are kept, so the database password never changes under you.
set -euo pipefail
cd "$(dirname "$0")"
D="${1:?usage: ./make-env.sh yourdomain.com [lan]}"
MODE="${2:-public}"
if [ "$MODE" = "lan" ]; then S=http; P=:3007; else S=https; P=""; fi
old() { [ -f .env ] && grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
SECRET="$(old DJANGO_SECRET_KEY)"; [ -n "$SECRET" ] || SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
PGPASS="$(old POSTGRES_PASSWORD)"; [ -n "$PGPASS" ] || PGPASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
cat > .env <<EOT
PUBLIC_API_URL=$S://api.$D$P/api/v1
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=$SECRET
DJANGO_ALLOWED_HOSTS=api.$D
CORS_ALLOWED_ORIGINS=$S://app.$D$P,$S://wholesale.$D$P
DJANGO_CSRF_TRUSTED_ORIGINS=$S://api.$D$P
POSTGRES_DB=dukalink
POSTGRES_USER=dukalink
POSTGRES_PASSWORD=$PGPASS
EOT
chmod 600 .env
cat > nginx.conf <<EOT
# One container serves all three DukaLink hostnames (chosen by the Host header).
map \$http_x_forwarded_proto \$fproto { default \$http_x_forwarded_proto; "" \$scheme; }

server {
    listen 80;
    server_name api.$D;
    client_max_body_size 10m;
    location /static/ { alias /srv/static/; expires 7d; }
    location / {
        proxy_pass http://backend:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$fproto;
        proxy_read_timeout 60s;
    }
}
server {
    listen 80;
    server_name app.$D;
    root /srv/www/app;
    location = /index.html { add_header Cache-Control "no-cache"; }
    location / { try_files \$uri /index.html; }
}
server {
    listen 80;
    server_name wholesale.$D;
    root /srv/www/wholesale;
    location = /index.html { add_header Cache-Control "no-cache"; }
    location / { try_files \$uri /index.html; }
}
server { listen 80 default_server; return 444; }
EOT
echo "Wrote deploy/.env and deploy/nginx.conf ($MODE mode, domain $D). Secrets are private."
echo "API address baked into the apps: $(old PUBLIC_API_URL)"
