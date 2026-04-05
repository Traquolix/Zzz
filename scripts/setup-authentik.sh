#!/usr/bin/env bash
# SequoIA — Authentik setup on the backend server.
#
# Prerequisites:
#   1. docker-compose.infra.yml running (PostgreSQL must be healthy)
#   2. .env with POSTGRES_USER and POSTGRES_PASSWORD set
#
# This script:
#   1. Creates the 'authentik' database in PostgreSQL
#   2. Generates .env.authentik with a random secret key (if not exists)
#   3. Starts Authentik containers
#   4. Prints setup instructions
#
# Usage: ./scripts/setup-authentik.sh

set -euo pipefail

SEQUOIA_DIR="${SEQUOIA_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if ! docker exec postgres pg_isready -U sequoia &>/dev/null; then
    echo "ERROR: PostgreSQL is not running. Start infra first:"
    echo "  docker compose -f docker-compose.infra.yml up -d"
    exit 1
fi

# ---------------------------------------------------------------------------
# 1. Create authentik database
# ---------------------------------------------------------------------------
log "Creating authentik database (if not exists)..."
docker exec postgres psql -U sequoia -tc \
    "SELECT 1 FROM pg_database WHERE datname = 'authentik'" | grep -q 1 \
    || docker exec postgres psql -U sequoia -c "CREATE DATABASE authentik;"
log "Database ready."

# ---------------------------------------------------------------------------
# 2. Generate .env.authentik
# ---------------------------------------------------------------------------
cd "$SEQUOIA_DIR"

if grep -q "CHANGE_ME" .env.authentik 2>/dev/null; then
    log "Generating secret key in .env.authentik..."
    SECRET_KEY=$(openssl rand -hex 50)
    sed -i "s/CHANGE_ME_GENERATE_WITH_openssl_rand_hex_50/$SECRET_KEY/" .env.authentik
    log "Secret key generated."
else
    log ".env.authentik already configured, skipping."
fi

# ---------------------------------------------------------------------------
# 3. Start Authentik
# ---------------------------------------------------------------------------
log "Starting Authentik..."
docker compose -f docker-compose.authentik.yml \
    --env-file .env --env-file .env.authentik up -d

log "Waiting for Authentik to start..."
sleep 15

# ---------------------------------------------------------------------------
# 4. Print instructions
# ---------------------------------------------------------------------------
cat << 'INSTRUCTIONS'

========================================================================
Authentik is running.
========================================================================

1. Complete initial setup:
   http://localhost:9090/if/flow/initial-setup/
   (or via SSH tunnel: ssh -L 9090:localhost:9090 beaujoin@192.168.99.113)

   This creates the admin account. Do this immediately.

2. Create an OAuth2/OIDC provider for Sequoia:
   Admin → Applications → Providers → Create
   - Name: sequoia
   - Authorization flow: default-provider-authorization-implicit-consent
   - Client type: Confidential
   - Redirect URI: https://app.sequoia-analytics.tech/api/auth/oidc/callback
   - Note the Client ID and Client Secret

3. Create an Application:
   Admin → Applications → Applications → Create
   - Name: Sequoia
   - Slug: sequoia
   - Provider: sequoia (the one you just created)

4. When NPM is live, add proxy host:
   Domain: auth.sequoia-analytics.tech
   Forward Host: 192.168.99.113
   Forward Port: 9090
   Force SSL, Websocket support

========================================================================
INSTRUCTIONS
