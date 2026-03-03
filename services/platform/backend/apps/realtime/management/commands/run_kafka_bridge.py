"""
Management command to run the Kafka -> Channels bridge with auto-restart.

Usage:
    python manage.py run_kafka_bridge

Consumes from Kafka topics (das.speeds, das.counts) and broadcasts
to Django Channels groups — the same groups the simulation uses.
Frontend sees identical data shapes regardless of source.

Watchdog: if the bridge loop crashes, it auto-restarts with exponential
backoff (5s base, 120s max). Gives up after 10 consecutive failures.

Requires:
    - KAFKA_BOOTSTRAP_SERVERS configured in settings
    - confluent-kafka installed (pip install confluent-kafka)
    - Redis running (for Channels layer)
"""

import asyncio
import json
import logging
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.realtime.kafka_bridge import run_kafka_bridge_loop

logger = logging.getLogger('sequoia.kafka_bridge')

MAX_RETRIES = 10
BASE_DELAY = 5    # seconds
MAX_DELAY = 120   # seconds


class Command(BaseCommand):
    help = 'Run the Kafka bridge (das.speeds/counts -> Django Channels).'

    def handle(self, *args, **options):
        self.stdout.write('Loading infrastructure data for SHM generation...')

        infrastructure = self._load_infrastructure()

        self.stdout.write(self.style.SUCCESS(
            f'Starting Kafka bridge with {len(infrastructure)} infrastructure items.'
        ))

        attempt = 0
        while attempt < MAX_RETRIES:
            try:
                asyncio.run(run_kafka_bridge_loop(infrastructure))
                break  # Clean exit
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('Kafka bridge stopped.'))
                break
            except Exception as e:
                attempt += 1
                delay = min(BASE_DELAY * (2 ** (attempt - 1)), MAX_DELAY)

                self.stderr.write(self.style.ERROR(
                    f'Kafka bridge crashed (attempt {attempt}/{MAX_RETRIES}): {e}'
                ))
                logger.error('Kafka bridge crash #%d: %s', attempt, e, exc_info=True)

                try:
                    import sentry_sdk
                    sentry_sdk.capture_exception(e)
                except Exception:
                    pass

                if attempt >= MAX_RETRIES:
                    self.stderr.write(self.style.ERROR(
                        f'Kafka bridge gave up after {MAX_RETRIES} consecutive failures.'
                    ))
                    break

                self.stdout.write(f'Restarting in {delay}s...')
                time.sleep(delay)

                # Reload infrastructure on retry (may have changed)
                infrastructure = self._load_infrastructure()

    def _load_infrastructure(self) -> list[dict]:
        """Load infrastructure from PostgreSQL (includes organization_id for org-scoped SHM).

        Falls back to JSON data file if the database is empty.
        """
        from apps.monitoring.models import Infrastructure

        items = []
        for infra in Infrastructure.objects.select_related('organization').all():
            items.append({
                'id': infra.id,
                'type': infra.type,
                'name': infra.name,
                'fiber_id': infra.fiber_id,
                'start_channel': infra.start_channel,
                'end_channel': infra.end_channel,
                'organization_id': str(infra.organization_id),
            })

        if items:
            self.stdout.write(f'  Loaded {len(items)} infrastructure items from DB')
            return items

        # Fallback to JSON file if DB is empty
        path = settings.DATA_DIR / 'clickhouse' / 'cables' / 'infrastructure.json'
        if path.exists():
            with open(path) as f:
                items = json.load(f)
            self.stdout.write(f'  Loaded {len(items)} infrastructure items from JSON (no org_id)')
        else:
            self.stderr.write(f'Warning: no infrastructure in DB and {path} not found')

        return items
