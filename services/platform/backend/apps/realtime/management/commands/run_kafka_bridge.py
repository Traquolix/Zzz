"""
Management command to run the Kafka → Channels bridge.

Usage:
    python manage.py run_kafka_bridge

Consumes from Kafka topics (das.speeds, das.counts) and broadcasts
to Django Channels groups — the same groups the simulation uses.
Frontend sees identical data shapes regardless of source.

Requires:
    - KAFKA_BOOTSTRAP_SERVERS configured in settings
    - confluent-kafka installed (pip install confluent-kafka)
    - Redis running (for Channels layer)
"""

import asyncio
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.realtime.kafka_bridge import run_kafka_bridge_loop


class Command(BaseCommand):
    help = 'Run the Kafka bridge (das.speeds/counts -> Django Channels).'

    def handle(self, *args, **options):
        self.stdout.write('Loading infrastructure data for SHM generation...')

        infrastructure = self._load_infrastructure()

        self.stdout.write(self.style.SUCCESS(
            f'Starting Kafka bridge with {len(infrastructure)} infrastructure items.'
        ))

        try:
            asyncio.run(run_kafka_bridge_loop(infrastructure))
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Kafka bridge stopped.'))

    def _load_infrastructure(self) -> list[dict]:
        """Load infrastructure from JSON data file (same source as simulation)."""
        path = settings.DATA_DIR / 'clickhouse' / 'cables' / 'infrastructure.json'
        if not path.exists():
            self.stderr.write(f'Warning: {path} not found')
            return []

        with open(path) as f:
            data = json.load(f)

        self.stdout.write(f'  Loaded {len(data)} infrastructure items')
        return data
