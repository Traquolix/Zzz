#!/usr/bin/env bash
# SequoIA — Database Backup Script
#
# Backs up PostgreSQL and ClickHouse to $SEQUOIA_DIR/backups/.
# Designed to run as a daily cron job on the backend server.
#
# Setup (run once on any new server):
#   ./scripts/backup.sh --install-cron
#
# Manual run:
#   ./scripts/backup.sh
#
# Restore:
#   ./scripts/restore.sh <backup-dir>
#
# Retention: 7 daily backups (configurable via RETENTION_DAYS).

set -euo pipefail

# ---------------------------------------------------------------------------
# Config — all overridable via environment
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEQUOIA_DIR="${SEQUOIA_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-${SEQUOIA_DIR}/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
DATE=$(date +%Y-%m-%d_%H%M)

# ---------------------------------------------------------------------------
# Cron installer
# ---------------------------------------------------------------------------
if [ "${1:-}" = "--install-cron" ]; then
    CRON_CMD="0 3 * * * cd ${SEQUOIA_DIR} && ${SEQUOIA_DIR}/scripts/backup.sh >> ${BACKUP_DIR}/backup.log 2>&1"
    mkdir -p "${BACKUP_DIR}"

    if crontab -l 2>/dev/null | grep -qF "scripts/backup.sh"; then
        echo "Cron job already installed:"
        crontab -l | grep "backup.sh"
    else
        (crontab -l 2>/dev/null; echo "${CRON_CMD}") | crontab -
        echo "Cron job installed: daily at 03:00"
        echo "  ${CRON_CMD}"
    fi
    echo ""
    echo "Backups will be stored in: ${BACKUP_DIR}"
    echo "Log file: ${BACKUP_DIR}/backup.log"
    echo "Retention: ${RETENTION_DAYS} days"
    exit 0
fi

# ---------------------------------------------------------------------------
# Load credentials from .env
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
BACKUP_SUBDIR="${BACKUP_DIR}/${DATE}"
mkdir -p "${BACKUP_SUBDIR}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

die() {
    log "ERROR: $*"
    exit 1
}

COMPOSE="docker compose -f ${SEQUOIA_DIR}/docker-compose.yml"

# Verify containers are running
${COMPOSE} ps --status running --format '{{.Name}}' | grep -q postgres \
    || die "PostgreSQL container is not running"
${COMPOSE} ps --status running --format '{{.Name}}' | grep -q clickhouse \
    || die "ClickHouse container is not running"

# ---------------------------------------------------------------------------
# PostgreSQL Backup
# ---------------------------------------------------------------------------
log "Starting PostgreSQL backup..."

PG_FILE="${BACKUP_SUBDIR}/postgres.sql.gz"

${COMPOSE} exec -T postgres \
    pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    --no-owner --no-privileges --clean --if-exists \
    | gzip > "${PG_FILE}"

PG_SIZE=$(du -h "${PG_FILE}" | cut -f1)
log "PostgreSQL backup complete: ${PG_FILE} (${PG_SIZE})"

# ---------------------------------------------------------------------------
# ClickHouse Backup
# ---------------------------------------------------------------------------
log "Starting ClickHouse backup..."

CH_BACKUP_NAME="backup_${DATE}"

# Use ClickHouse's native BACKUP command → writes to the 'backups' disk
${COMPOSE} exec -T clickhouse \
    clickhouse-client \
    --user "${CLICKHOUSE_USER}" \
    --password "${CLICKHOUSE_PASSWORD}" \
    --query "BACKUP DATABASE ${CLICKHOUSE_DB} TO Disk('backups', '${CH_BACKUP_NAME}')" \
    || die "ClickHouse BACKUP command failed. Is backup_disk.xml mounted?"

# Copy backup out of the Docker volume to the host backup directory
${COMPOSE} exec -T clickhouse \
    tar czf - -C /backups "${CH_BACKUP_NAME}" > "${BACKUP_SUBDIR}/clickhouse.tar.gz"

# Clean up in-container backup to save volume space
${COMPOSE} exec -T clickhouse \
    rm -rf "/backups/${CH_BACKUP_NAME}"

CH_SIZE=$(du -h "${BACKUP_SUBDIR}/clickhouse.tar.gz" | cut -f1)
log "ClickHouse backup complete: ${BACKUP_SUBDIR}/clickhouse.tar.gz (${CH_SIZE})"

# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------
cat > "${BACKUP_SUBDIR}/metadata.txt" <<METADATA
backup_date: ${DATE}
postgres_db: ${POSTGRES_DB}
clickhouse_db: ${CLICKHOUSE_DB}
postgres_version: $(${COMPOSE} exec -T postgres pg_dump --version | head -1)
clickhouse_version: $(${COMPOSE} exec -T clickhouse clickhouse-client --version | head -1)
METADATA

log "Metadata written to ${BACKUP_SUBDIR}/metadata.txt"

# ---------------------------------------------------------------------------
# Retention — delete backups older than N days
# ---------------------------------------------------------------------------
log "Cleaning up backups older than ${RETENTION_DAYS} days..."

DELETED=0
for dir in "${BACKUP_DIR}"/20*; do
    [ -d "${dir}" ] || continue
    if [ "$(find "${dir}" -maxdepth 0 -mtime +${RETENTION_DAYS})" ]; then
        rm -rf "${dir}"
        DELETED=$((DELETED + 1))
        log "  Deleted: $(basename "${dir}")"
    fi
done

log "Deleted ${DELETED} old backup(s)"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
TOTAL_SIZE=$(du -sh "${BACKUP_SUBDIR}" | cut -f1)
log "Backup complete: ${BACKUP_SUBDIR} (${TOTAL_SIZE} total)"
log "Current backups:"
for dir in "${BACKUP_DIR}"/20*; do
    [ -d "${dir}" ] || continue
    size=$(du -sh "${dir}" | cut -f1)
    echo "  $(basename "${dir}")  ${size}"
done
