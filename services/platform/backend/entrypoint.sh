#!/bin/sh
set -e

# Block startup if placeholder passwords are still set in production
if [ "${ENVIRONMENT}" = "prod" ]; then
    FAIL=0
    for VAR_NAME in POSTGRES_PASSWORD CLICKHOUSE_PASSWORD REDIS_PASSWORD DJANGO_SECRET_KEY; do
        VAL=$(eval echo "\$$VAR_NAME")
        case "$VAL" in
            ""|CHANGE_ME*|changeme)
                echo "FATAL: $VAR_NAME is not set or still contains a placeholder value." >&2
                FAIL=1
                ;;
        esac
    done
    if [ "$FAIL" -eq 1 ]; then
        echo "FATAL: Refusing to start with default credentials in production." >&2
        echo "       Generate real secrets — see .env.example for instructions." >&2
        exit 1
    fi
fi

echo "Collecting static files..."
python manage.py collectstatic --noinput 2>/dev/null || true

echo "Running database migrations..."
python manage.py migrate --noinput

# Apply ClickHouse migrations (idempotent — safe to re-run on every deploy)
echo "Applying ClickHouse migrations..."
python manage.py apply_clickhouse_migrations || {
    echo "WARNING: ClickHouse migrations failed or ClickHouse is unavailable." >&2
    echo "         The backend will start, but schema may be outdated." >&2
}

# Seed users only in DEBUG mode (seed_users command enforces this internally too)
if [ "${DJANGO_SETTINGS_MODULE}" = "sequoia.settings.dev" ]; then
    echo "Seeding development users..."
    python manage.py seed_users || true
fi

# run_realtime handles: ASGI server + Kafka bridge (or simulation fallback)
# Auto-detects data source based on REALTIME_SOURCE env var or Kafka availability
echo "Starting SequoIA backend (ASGI + realtime data)..."
exec python manage.py run_realtime --host 0.0.0.0 --port 8001
