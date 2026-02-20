#!/bin/sh
set -e

echo "Running database migrations..."
python manage.py migrate --noinput

# Seed users only in DEBUG mode (seed_users command enforces this internally too)
if [ "${DJANGO_SETTINGS_MODULE}" = "sequoia.settings.dev" ]; then
    echo "Seeding development users..."
    python manage.py seed_users || true
fi

# run_realtime handles: ASGI server + Kafka bridge (or simulation fallback)
# Auto-detects data source based on REALTIME_SOURCE env var or Kafka availability
echo "Starting SequoIA backend (ASGI + realtime data)..."
exec python manage.py run_realtime --host 0.0.0.0 --port 8001
