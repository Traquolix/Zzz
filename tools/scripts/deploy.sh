#!/usr/bin/env bash
# SequoIA deployment script
# Usage: ./tools/scripts/deploy.sh [--skip-frontend]
#
# Deploys backend services to the IMREDD server and optionally
# builds + deploys the frontend to the frontend server.
#
# Prerequisites:
#   - SSH access to backend server (DEPLOY_BACKEND_HOST)
#   - SSH access to frontend server (DEPLOY_FRONTEND_HOST) unless --skip-frontend
#   - Git repo is clean (no uncommitted changes)

set -euo pipefail

# ---------------------------------------------------------------------------
# Config — override via environment variables
# ---------------------------------------------------------------------------
DEPLOY_BACKEND_HOST="${DEPLOY_BACKEND_HOST:?Set DEPLOY_BACKEND_HOST (e.g. user@backend-ip)}"
DEPLOY_BACKEND_PATH="${DEPLOY_BACKEND_PATH:-/opt/Sequoia}"
DEPLOY_FRONTEND_HOST="${DEPLOY_FRONTEND_HOST:?Set DEPLOY_FRONTEND_HOST (e.g. user@frontend-ip)}"
DEPLOY_FRONTEND_PATH="${DEPLOY_FRONTEND_PATH:-/var/www/sequoia}"

SKIP_FRONTEND=false
if [[ "${1:-}" == "--skip-frontend" ]]; then
    SKIP_FRONTEND=true
fi

GIT_SHA=$(git rev-parse --short HEAD)
GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
TIMESTAMP=$(date -u +%Y%m%d-%H%M%S)

echo "=== SequoIA Deploy ==="
echo "Commit: ${GIT_SHA} (${GIT_BRANCH})"
echo "Time:   ${TIMESTAMP}"
echo ""

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: Working directory is not clean. Commit or stash changes first."
    exit 1
fi

if [[ "${GIT_BRANCH}" != "main" ]]; then
    echo "WARNING: Deploying from branch '${GIT_BRANCH}' (not main)"
    read -p "Continue? [y/N] " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] || exit 1
fi

# ---------------------------------------------------------------------------
# Backend deployment
# ---------------------------------------------------------------------------
echo "--- Deploying backend to ${DEPLOY_BACKEND_HOST} ---"

ssh "${DEPLOY_BACKEND_HOST}" bash <<REMOTE
    set -euo pipefail
    cd "${DEPLOY_BACKEND_PATH}"

    echo "Pulling latest code..."
    git fetch origin main
    git checkout main
    git reset --hard origin/main

    echo "Rebuilding services..."
    docker compose build --parallel
    docker compose up -d

    echo "Waiting for health checks..."
    sleep 10

    # Check all services are healthy
    UNHEALTHY=\$(docker compose ps --format json | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
for line in lines:
    svc = json.loads(line)
    if svc.get('Health', '') not in ('healthy', '', 'N/A') and svc.get('State') == 'running':
        print(svc['Service'])
" 2>/dev/null || true)

    if [[ -n "\${UNHEALTHY}" ]]; then
        echo "WARNING: Unhealthy services detected: \${UNHEALTHY}"
        echo "Check logs with: docker compose logs <service>"
    else
        echo "All services healthy."
    fi

    echo "Backend deployed: ${GIT_SHA}"
REMOTE

# ---------------------------------------------------------------------------
# Frontend deployment
# ---------------------------------------------------------------------------
if [[ "${SKIP_FRONTEND}" == "false" ]]; then
    echo ""
    echo "--- Building and deploying frontend ---"

    cd services/platform/frontend
    npm ci
    npm run build

    echo "Uploading build to ${DEPLOY_FRONTEND_HOST}..."
    scp -r dist/* "${DEPLOY_FRONTEND_HOST}:${DEPLOY_FRONTEND_PATH}/"

    echo "Frontend deployed."
    cd ../../..
fi

echo ""
echo "=== Deploy complete: ${GIT_SHA} at ${TIMESTAMP} ==="
