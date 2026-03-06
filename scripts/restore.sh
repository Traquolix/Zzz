#!/usr/bin/env bash
# SequoIA — Database Restore Script
#
# Restores a backup created by backup.sh.
#
# Usage:
#   ./scripts/restore.sh <backup-dir>
#   ./scripts/restore.sh backups/2026-03-06_0300
#   ./scripts/restore.sh --latest                  # restore most recent backup
#   ./scripts/restore.sh --list                     # list available backups
#
# WARNING: This overwrites the current database contents.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEQUOIA_DIR="${SEQUOIA_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-${SEQUOIA_DIR}/backups}"

# ---------------------------------------------------------------------------
# Load credentials
# ---------------------------------------------------------------------------
if [ -f "${SEQUOIA_DIR}/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "${SEQUOIA_DIR}/.env"
    set +a
fi

POSTGRES_USER="${POSTGRES_USER:-sequoia}"
POSTGRES_DB="${POSTGRES_DB:-sequoia}"
CLICKHOUSE_USER="${CLICKHOUSE_USER:-sequoia}"
CLICKHOUSE_PASSWORD="${CLICKHOUSE_PASSWORD:-}"
CLICKHOUSE_DB="${CLICKHOUSE_DATABASE:-sequoia}"

COMPOSE="docker compose -f ${SEQUOIA_DIR}/docker-compose.yml"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

die() {
    log "ERROR: $*"
    exit 1
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup-dir|--latest|--list>"
    echo ""
    echo "Options:"
    echo "  <backup-dir>   Path to a backup directory (e.g., backups/2026-03-06_0300)"
    echo "  --latest       Restore the most recent backup"
    echo "  --list         List available backups"
    exit 1
fi

if [ "$1" = "--list" ]; then
    echo "Available backups in ${BACKUP_DIR}:"
    echo ""
    for dir in "${BACKUP_DIR}"/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_*; do
        [ -d "${dir}" ] || continue
        size=$(du -sh "${dir}" | cut -f1)
        has_pg="no"
        has_ch="no"
        [ -f "${dir}/postgres.sql.gz" ] && has_pg="yes"
        [ -f "${dir}/clickhouse.tar.gz" ] && has_ch="yes"
        echo "  $(basename "${dir}")  ${size}  (pg: ${has_pg}, ch: ${has_ch})"
    done
    exit 0
fi

if [ "$1" = "--latest" ]; then
    # Find the most recent backup directory
    RESTORE_DIR=$(find "${BACKUP_DIR}" -maxdepth 1 -type d -name '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_*' | sort -r | head -1)
    [ -n "${RESTORE_DIR}" ] || die "No backups found in ${BACKUP_DIR}"
else
    RESTORE_DIR="$1"
    # Allow relative path from SEQUOIA_DIR
    if [ ! -d "${RESTORE_DIR}" ] && [ -d "${SEQUOIA_DIR}/${RESTORE_DIR}" ]; then
        RESTORE_DIR="${SEQUOIA_DIR}/${RESTORE_DIR}"
    fi
fi

[ -d "${RESTORE_DIR}" ] || die "Backup directory not found: ${RESTORE_DIR}"

log "Restoring from: ${RESTORE_DIR}"

if [ -f "${RESTORE_DIR}/metadata.txt" ]; then
    echo ""
    cat "${RESTORE_DIR}/metadata.txt"
    echo ""
fi

# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------
echo "WARNING: This will overwrite the current ${POSTGRES_DB} and ${CLICKHOUSE_DB} databases."
echo ""
read -r -p "Continue? [y/N] " confirm
if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# ---------------------------------------------------------------------------
# Restore PostgreSQL
# ---------------------------------------------------------------------------
if [ -f "${RESTORE_DIR}/postgres.sql.gz" ]; then
    log "Restoring PostgreSQL..."

    # Stop the backend to prevent writes during restore
    ${COMPOSE} stop platform-backend 2>/dev/null || true

    gunzip -c "${RESTORE_DIR}/postgres.sql.gz" \
        | ${COMPOSE} exec -T postgres \
            psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --single-transaction -q

    log "PostgreSQL restore complete"
else
    log "SKIP: No postgres.sql.gz found in backup"
fi

# ---------------------------------------------------------------------------
# Restore ClickHouse
# ---------------------------------------------------------------------------
if [ -f "${RESTORE_DIR}/clickhouse.tar.gz" ]; then
    log "Restoring ClickHouse..."

    # Extract backup archive into the ClickHouse backups volume
    BACKUP_NAME=$(tar tzf "${RESTORE_DIR}/clickhouse.tar.gz" | head -1 | cut -d/ -f1)
    [ -n "${BACKUP_NAME}" ] || die "Could not determine backup name from archive"

    # Clean up any existing backup with the same name
    ${COMPOSE} exec -T clickhouse rm -rf "/backups/${BACKUP_NAME}" 2>/dev/null || true

    # Extract into the backups volume
    ${COMPOSE} exec -T clickhouse tar xzf - -C /backups < "${RESTORE_DIR}/clickhouse.tar.gz"

    # Restore using ClickHouse's native RESTORE command
    if ! ${COMPOSE} exec -T clickhouse \
        clickhouse-client \
        --user "${CLICKHOUSE_USER}" \
        --password "${CLICKHOUSE_PASSWORD}" \
        --query "RESTORE DATABASE ${CLICKHOUSE_DB} FROM Disk('backups', '${BACKUP_NAME}') SETTINGS allow_non_empty_tables=true"; then
        # Clean up extracted backup even on failure
        ${COMPOSE} exec -T clickhouse rm -rf "/backups/${BACKUP_NAME}" 2>/dev/null || true
        die "ClickHouse RESTORE command failed"
    fi

    # Clean up
    ${COMPOSE} exec -T clickhouse rm -rf "/backups/${BACKUP_NAME}"

    log "ClickHouse restore complete"
else
    log "SKIP: No clickhouse.tar.gz found in backup"
fi

# ---------------------------------------------------------------------------
# Restart services
# ---------------------------------------------------------------------------
log "Restarting platform-backend..."
${COMPOSE} start platform-backend

log "Restore complete. Verify the application is working correctly."
