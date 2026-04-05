#!/usr/bin/env bash
# SequoIA — Nginx Proxy Manager setup on the frontend server.
#
# Run this from your LOCAL machine (not the frontend server).
# It copies the needed files via scp, then starts the containers remotely.
#
# Prerequisites (on the frontend server):
#   1. DNS: app.sequoia-analytics.tech + test.sequoia-analytics.tech → 134.59.98.100
#   2. Docker + Docker Compose installed
#   3. Host nginx stopped:
#        sudo systemctl stop nginx && sudo systemctl disable nginx
#   4. Frontend directories created:
#        sudo mkdir -p /var/www/sequoia /var/www/sequoia-preprod
#        sudo chown frontend:frontend /var/www/sequoia /var/www/sequoia-preprod
#
# Usage: ./scripts/setup-proxy.sh

set -euo pipefail

FRONTEND_HOST="frontend@134.59.98.100"
REMOTE_DIR="/home/frontend/sequoia-proxy"
BACKEND_IP="192.168.99.113"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ---------------------------------------------------------------------------
# Pre-flight checks (remote)
# ---------------------------------------------------------------------------
log "Running pre-flight checks on frontend server..."

ssh "$FRONTEND_HOST" bash -s << 'CHECKS'
set -e
if systemctl is-active nginx &>/dev/null; then
    echo "ERROR: Host nginx is still running. Stop it first:"
    echo "  sudo systemctl stop nginx && sudo systemctl disable nginx"
    exit 1
fi
if [ ! -d /var/www/sequoia ]; then
    echo "ERROR: /var/www/sequoia does not exist. Create it first:"
    echo "  sudo mkdir -p /var/www/sequoia /var/www/sequoia-preprod"
    echo "  sudo chown frontend:frontend /var/www/sequoia /var/www/sequoia-preprod"
    exit 1
fi
docker --version > /dev/null 2>&1 || { echo "ERROR: Docker not installed"; exit 1; }
echo "OK"
CHECKS

log "Pre-flight checks passed."

# ---------------------------------------------------------------------------
# Copy files to frontend server
# ---------------------------------------------------------------------------
log "Copying files to frontend server..."

ssh "$FRONTEND_HOST" "mkdir -p $REMOTE_DIR/infrastructure/nginx"

scp "$SCRIPT_DIR/docker-compose.proxy.yml" "$FRONTEND_HOST:$REMOTE_DIR/docker-compose.proxy.yml"
scp "$SCRIPT_DIR/infrastructure/nginx/frontend-spa.conf" "$FRONTEND_HOST:$REMOTE_DIR/infrastructure/nginx/frontend-spa.conf"

# Copy prod frontend to preprod as initial content (so preprod has something to show)
ssh "$FRONTEND_HOST" bash -s << 'COPY'
if [ -f /var/www/sequoia/index.html ] && [ ! -f /var/www/sequoia-preprod/index.html ]; then
    echo "Copying prod frontend to preprod as initial content..."
    cp -r /var/www/sequoia/* /var/www/sequoia-preprod/
fi
COPY

# ---------------------------------------------------------------------------
# Start NPM + frontend containers
# ---------------------------------------------------------------------------
log "Starting Nginx Proxy Manager + frontend containers..."

ssh "$FRONTEND_HOST" "cd $REMOTE_DIR && docker compose -f docker-compose.proxy.yml up -d"

log "Waiting for NPM to start..."
sleep 10

# ---------------------------------------------------------------------------
# Print configuration instructions
# ---------------------------------------------------------------------------
cat << INSTRUCTIONS

========================================================================
NPM is running on the frontend server. Complete the setup:
========================================================================

1. Open the NPM admin UI:
   ssh -L 8181:localhost:81 $FRONTEND_HOST
   Then visit http://localhost:8181 in your browser.

   Default login: admin@example.com / changeme
   (Change the password immediately)

2. Add proxy host for PROD:
   Domain:          app.sequoia-analytics.tech
   Scheme:          http
   Forward Host:    frontend-prod
   Forward Port:    80
   [x] Block common exploits
   [x] Websocket support
   SSL tab: Request new certificate, enable Force SSL, HTTP/2

   Then add Custom Locations:
     Location: /api
       Scheme: http  |  Forward Host: $BACKEND_IP  |  Forward Port: 8001
       Custom config:
         proxy_set_header Upgrade \$http_upgrade;
         proxy_set_header Connection "upgrade";
         proxy_read_timeout 86400;

     Location: /ws
       Scheme: http  |  Forward Host: $BACKEND_IP  |  Forward Port: 8001
       Custom config:
         proxy_http_version 1.1;
         proxy_set_header Upgrade \$http_upgrade;
         proxy_set_header Connection "upgrade";
         proxy_read_timeout 86400;

     Location: /media
       Scheme: http  |  Forward Host: $BACKEND_IP  |  Forward Port: 8001

3. Add proxy host for PREPROD:
   Domain:          test.sequoia-analytics.tech
   Scheme:          http
   Forward Host:    frontend-preprod
   Forward Port:    80
   [x] Block common exploits
   [x] Websocket support
   SSL tab: Request new certificate, enable Force SSL, HTTP/2

   Then add Custom Locations:
     Location: /api
       Scheme: http  |  Forward Host: $BACKEND_IP  |  Forward Port: 8002
       Custom config:
         proxy_set_header Upgrade \$http_upgrade;
         proxy_set_header Connection "upgrade";
         proxy_read_timeout 86400;

     Location: /ws
       Scheme: http  |  Forward Host: $BACKEND_IP  |  Forward Port: 8002
       Custom config:
         proxy_http_version 1.1;
         proxy_set_header Upgrade \$http_upgrade;
         proxy_set_header Connection "upgrade";
         proxy_read_timeout 86400;

     Location: /media
       Scheme: http  |  Forward Host: $BACKEND_IP  |  Forward Port: 8002

4. Update backend .env (on $BACKEND_IP):
   DJANGO_ALLOWED_HOSTS=app.sequoia-analytics.tech,test.sequoia-analytics.tech,localhost
   CORS_ALLOWED_ORIGINS=https://app.sequoia-analytics.tech,https://test.sequoia-analytics.tech
   FRONTEND_URL=https://app.sequoia-analytics.tech

5. Keep the old university domain working:
   Add another proxy host for dashboardsequoia.univ-cotedazur.fr
   pointing to frontend-prod with the same API/WS locations.
   Use the existing SSL cert (/etc/nginx/ssl/cert.pem + key.pem)
   via NPM's "Custom SSL" option.

========================================================================
INSTRUCTIONS
