#!/usr/bin/env bash
# SequoIA — Server Setup Script
#
# Bootstraps a fresh server for running SequoIA. Handles:
#   - Docker + Docker Compose installation
#   - NVIDIA container toolkit (if GPU present)
#   - GitHub Actions runner setup
#   - Backup cron job
#   - Directory structure
#
# Usage:
#   # Backend server (with Docker services + GPU):
#   ./scripts/server-setup.sh --role backend --gh-token <TOKEN>
#
#   # Frontend server (nginx only):
#   ./scripts/server-setup.sh --role frontend --gh-token <TOKEN>
#
#   # Skip runner install (do backups + Docker only):
#   ./scripts/server-setup.sh --role backend
#
# The --gh-token is a one-time runner registration token from:
#   GitHub repo → Settings → Actions → Runners → New self-hosted runner
#
# This script is idempotent — safe to re-run.

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
ROLE=""
GH_TOKEN=""
GH_REPO="https://github.com/Traquolix/Sequoia"
# NOTE: GitHub deprecates old runner versions — update periodically.
# Check latest at: https://github.com/actions/runner/releases
RUNNER_VERSION="2.322.0"
SEQUOIA_DIR="/opt/Sequoia"

usage() {
    echo "Usage: $0 --role <backend|frontend> [--gh-token <TOKEN>] [--sequoia-dir <path>]"
    echo ""
    echo "Options:"
    echo "  --role         Server role: 'backend' (Docker stack + GPU) or 'frontend' (nginx)"
    echo "  --gh-token     GitHub runner registration token (optional, skip runner setup if omitted)"
    echo "  --sequoia-dir  SequoIA install directory (default: /opt/Sequoia)"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --role) ROLE="$2"; shift 2 ;;
        --gh-token) GH_TOKEN="$2"; shift 2 ;;
        --sequoia-dir) SEQUOIA_DIR="$2"; shift 2 ;;
        *) usage ;;
    esac
done

[ -n "${ROLE}" ] || usage
[[ "${ROLE}" == "backend" || "${ROLE}" == "frontend" ]] || usage

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
log "=== Step 1: System packages ==="

if ! command -v docker &>/dev/null; then
    log "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$(whoami)"
    log "Docker installed. You may need to log out and back in for group changes."
else
    log "Docker already installed: $(docker --version)"
fi

if ! docker compose version &>/dev/null; then
    log "Installing Docker Compose plugin..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-compose-plugin
else
    log "Docker Compose already installed: $(docker compose version)"
fi

if [[ "${ROLE}" == "frontend" ]]; then
    if ! command -v nginx &>/dev/null; then
        log "Installing nginx..."
        sudo apt-get update -qq
        sudo apt-get install -y -qq nginx
    else
        log "nginx already installed: $(nginx -v 2>&1)"
    fi
fi

# ---------------------------------------------------------------------------
# 2. NVIDIA Container Toolkit (backend only, if GPU present)
# ---------------------------------------------------------------------------
if [[ "${ROLE}" == "backend" ]]; then
    if lspci 2>/dev/null | grep -qi nvidia; then
        if ! command -v nvidia-container-cli &>/dev/null; then
            log "=== Step 2: NVIDIA Container Toolkit ==="
            log "GPU detected but nvidia-container-toolkit not installed."
            log "Installing..."
            curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
                | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
            curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
                | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
                | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
            sudo apt-get update -qq
            sudo apt-get install -y -qq nvidia-container-toolkit
            sudo nvidia-ctk runtime configure --runtime=docker
            sudo systemctl restart docker
            log "NVIDIA Container Toolkit installed."
        else
            log "NVIDIA Container Toolkit already installed."
        fi
    else
        log "No NVIDIA GPU detected — skipping container toolkit."
    fi
fi

# ---------------------------------------------------------------------------
# 3. Directory structure
# ---------------------------------------------------------------------------
log "=== Step 3: Directory structure ==="

if [[ "${ROLE}" == "backend" ]]; then
    sudo mkdir -p "${SEQUOIA_DIR}"
    sudo chown "$(whoami):$(whoami)" "${SEQUOIA_DIR}"
    mkdir -p "${SEQUOIA_DIR}/backups"
    mkdir -p "${SEQUOIA_DIR}/data/calibration"
    mkdir -p "${SEQUOIA_DIR}/data/visualizations"
    log "Backend directories created at ${SEQUOIA_DIR}"

    if [ ! -d "${SEQUOIA_DIR}/.git" ]; then
        log "Cloning repository..."
        git clone "${GH_REPO}.git" "${SEQUOIA_DIR}"
    else
        log "Repository already present at ${SEQUOIA_DIR}"
    fi
fi

if [[ "${ROLE}" == "frontend" ]]; then
    sudo mkdir -p /var/www/sequoia
    sudo chown "$(whoami):$(whoami)" /var/www/sequoia
    log "Frontend directory created at /var/www/sequoia"
fi

# ---------------------------------------------------------------------------
# 4. Environment file (backend only)
# ---------------------------------------------------------------------------
if [[ "${ROLE}" == "backend" ]]; then
    log "=== Step 4: Environment file ==="
    if [ ! -f "${SEQUOIA_DIR}/.env" ]; then
        log "Generating .env with random passwords..."
        GEN_PASS() { openssl rand -hex 16; }  # guaranteed 32 hex chars
        cat > "${SEQUOIA_DIR}/.env" <<ENV
# SequoIA — Generated $(date -u +%Y-%m-%d)
# Edit values as needed, then run: docker compose up -d

# PostgreSQL
POSTGRES_DB=sequoia
POSTGRES_USER=sequoia
POSTGRES_PASSWORD=$(GEN_PASS)

# ClickHouse
CLICKHOUSE_PASSWORD=$(GEN_PASS)
CLICKHOUSE_GRAFANA_PASSWORD=$(GEN_PASS)

# Redis
REDIS_PASSWORD=$(GEN_PASS)

# Django
DJANGO_SECRET_KEY=$(GEN_PASS)$(GEN_PASS)

# JWT RS256 keys (auto-generated by server-setup.sh)
JWT_SIGNING_KEY_FILE=${SEQUOIA_DIR}/secrets/jwt_signing.pem
JWT_VERIFYING_KEY_FILE=${SEQUOIA_DIR}/secrets/jwt_verifying.pem

# Kafka — external host IP for DAS interrogator connections
KAFKA_EXTERNAL_HOST=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

# Frontend URL (for CORS)
FRONTEND_URL=http://localhost:3000
CORS_ALLOWED_ORIGINS=http://localhost:3000
DJANGO_ALLOWED_HOSTS=localhost

# Environment
ENVIRONMENT=production
ENV
        chmod 600 "${SEQUOIA_DIR}/.env"
        log ".env generated at ${SEQUOIA_DIR}/.env"

        # Generate JWT RS256 key pair in secrets/ subdirectory
        mkdir -p "${SEQUOIA_DIR}/secrets"
        chmod 700 "${SEQUOIA_DIR}/secrets"
        if [ ! -f "${SEQUOIA_DIR}/secrets/jwt_signing.pem" ]; then
            openssl genrsa -out "${SEQUOIA_DIR}/secrets/jwt_signing.pem" 2048 2>/dev/null
            openssl rsa -in "${SEQUOIA_DIR}/secrets/jwt_signing.pem" -pubout \
                -out "${SEQUOIA_DIR}/secrets/jwt_verifying.pem" 2>/dev/null
            chmod 600 "${SEQUOIA_DIR}/secrets/jwt_signing.pem" "${SEQUOIA_DIR}/secrets/jwt_verifying.pem"
            log "JWT RS256 key pair generated in ${SEQUOIA_DIR}/secrets/"
        fi

        log "IMPORTANT: Edit .env to set FRONTEND_URL and KAFKA_EXTERNAL_HOST"
    else
        log ".env already exists — skipping"
    fi
fi

# ---------------------------------------------------------------------------
# 5. GitHub Actions Runner
# ---------------------------------------------------------------------------
if [ -n "${GH_TOKEN}" ]; then
    log "=== Step 5: GitHub Actions Runner ==="
    RUNNER_DIR="${HOME}/actions-runner"

    if [ -f "${RUNNER_DIR}/.runner" ]; then
        log "Runner already configured at ${RUNNER_DIR}"
    else
        mkdir -p "${RUNNER_DIR}"
        cd "${RUNNER_DIR}"

        ARCH=$(dpkg --print-architecture 2>/dev/null || echo "x64")
        case "${ARCH}" in
            amd64) ARCH="x64" ;;
            arm64) ARCH="arm64" ;;
        esac

        TARBALL="actions-runner-linux-${ARCH}-${RUNNER_VERSION}.tar.gz"
        if [ ! -f "${TARBALL}" ]; then
            log "Downloading runner ${RUNNER_VERSION} (${ARCH})..."
            curl -sL -o "${TARBALL}" \
                "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${TARBALL}"
        fi

        tar xzf "${TARBALL}"

        # SECURITY: On public repos, self-hosted runners execute workflow code
        # from any PR fork. Either make the repo private, or restrict runner to
        # main-only via: GitHub → Settings → Actions → Fork PR workflows.
        log "Configuring runner with label '${ROLE}'..."
        ./config.sh --url "${GH_REPO}" --token "${GH_TOKEN}" \
            --labels "${ROLE}" --name "$(hostname)-${ROLE}" --unattended

        log "Installing runner as a system service..."
        sudo ./svc.sh install
        sudo ./svc.sh start

        log "GitHub Actions runner installed and started."
    fi
    cd "${SEQUOIA_DIR}" 2>/dev/null || cd ~
else
    log "=== Step 5: GitHub Actions Runner (skipped — no --gh-token provided) ==="
    log "To install later: $0 --role ${ROLE} --gh-token <TOKEN>"
fi

# ---------------------------------------------------------------------------
# 6. Backup cron (backend only)
# ---------------------------------------------------------------------------
if [[ "${ROLE}" == "backend" ]]; then
    log "=== Step 6: Backup cron ==="
    "${SEQUOIA_DIR}/scripts/backup.sh" --install-cron
fi

# ---------------------------------------------------------------------------
# 7. nginx config (frontend only)
# ---------------------------------------------------------------------------
if [[ "${ROLE}" == "frontend" ]]; then
    log "=== Step 7: nginx configuration ==="
    NGINX_CONF="/etc/nginx/sites-available/sequoia"
    if [ ! -f "${NGINX_CONF}" ]; then
        sudo tee "${NGINX_CONF}" > /dev/null <<'NGINX'
server {
    listen 80 default_server;
    server_name _;

    root /var/www/sequoia;
    index index.html;

    # SPA — route all non-file requests to index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # Gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
}
NGINX
        sudo ln -sf "${NGINX_CONF}" /etc/nginx/sites-enabled/sequoia
        sudo rm -f /etc/nginx/sites-enabled/default
        sudo nginx -t && sudo systemctl reload nginx
        log "nginx configured for SPA at /var/www/sequoia"
    else
        log "nginx config already exists at ${NGINX_CONF}"
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================="
echo "  SequoIA ${ROLE} server setup complete"
echo "============================================="
echo ""

if [[ "${ROLE}" == "backend" ]]; then
    cat <<SUMMARY
Next steps:
  1. Edit ${SEQUOIA_DIR}/.env
     - Set FRONTEND_URL and CORS_ALLOWED_ORIGINS to the frontend URL
     - Set KAFKA_EXTERNAL_HOST to this server's IP
     - Verify all passwords are set
     (JWT keys were auto-generated)

  2. Start the stack:
     cd ${SEQUOIA_DIR}
     docker compose up -d

  3. Verify:
     docker compose ps
     curl http://localhost:8001/api/health

Backups: daily at 03:00 → ${SEQUOIA_DIR}/backups/ (7-day retention)
Restore: ./scripts/restore.sh --latest
SUMMARY
elif [[ "${ROLE}" == "frontend" ]]; then
    cat <<SUMMARY
Next steps:
  1. Build and deploy the frontend:
     cd services/platform/frontend
     npm ci && npm run build
     cp -r dist/* /var/www/sequoia/

  2. Or deploy from your dev machine:
     DEPLOY_BACKEND_HOST=user@backend-ip \\
     DEPLOY_FRONTEND_HOST=user@frontend-ip \\
     ./tools/scripts/deploy.sh

  3. Verify:
     curl http://localhost/
SUMMARY
fi
