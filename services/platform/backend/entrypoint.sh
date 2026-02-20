#!/bin/sh
set -e

echo "Running database migrations..."
python manage.py migrate --noinput

# Seed users only in DEBUG mode (seed_users command enforces this internally too)
if [ "${DJANGO_SETTINGS_MODULE}" = "sequoia.settings.dev" ]; then
    echo "Seeding development users..."
    python manage.py seed_users || true
fi

echo "Starting Daphne ASGI server on 0.0.0.0:8001..."
exec daphne -b 0.0.0.0 -p 8001 sequoia.asgi:application
