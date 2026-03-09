#!/bin/sh
set -e

# Block startup if placeholder passwords are still set in production
if [ "${ENVIRONMENT}" = "production" ]; then
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

echo "Running database migrations..."
python manage.py migrate --noinput

# Apply ClickHouse migrations (idempotent — safe to re-run on every deploy)
echo "Applying ClickHouse migrations..."
python -c "
import os, glob, sys
try:
    import clickhouse_connect
    client = clickhouse_connect.get_client(
        host=os.environ.get('CLICKHOUSE_HOST', 'clickhouse'),
        port=int(os.environ.get('CLICKHOUSE_HTTP_PORT', 8123)),
        username=os.environ.get('CLICKHOUSE_USER', 'sequoia'),
        password=os.environ.get('CLICKHOUSE_PASSWORD', ''),
    )
    migration_dir = '/infrastructure/clickhouse/migrations'
    if not os.path.isdir(migration_dir):
        print(f'  No migrations directory at {migration_dir}, skipping')
        sys.exit(0)
    for sql_file in sorted(glob.glob(os.path.join(migration_dir, '*.sql'))):
        name = os.path.basename(sql_file)
        with open(sql_file) as f:
            sql = f.read()
        for stmt in sql.split(';'):
            stmt = stmt.strip()
            if stmt and not stmt.startswith('--'):
                try:
                    client.command(stmt)
                except Exception as e:
                    print(f'  Warning: {name}: {e}')
        print(f'  Applied {name}')
    client.close()
except Exception as e:
    print(f'  ClickHouse migrations skipped: {e}')
" || true

# Seed users only in DEBUG mode (seed_users command enforces this internally too)
if [ "${DJANGO_SETTINGS_MODULE}" = "sequoia.settings.dev" ]; then
    echo "Seeding development users..."
    python manage.py seed_users || true
fi

# run_realtime handles: ASGI server + Kafka bridge (or simulation fallback)
# Auto-detects data source based on REALTIME_SOURCE env var or Kafka availability
echo "Starting SequoIA backend (ASGI + realtime data)..."
exec python manage.py run_realtime --host 0.0.0.0 --port 8001
