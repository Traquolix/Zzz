"""
Management command to run the traffic simulation engine.

Usage:
    python manage.py run_simulation

Loads fiber configs and infrastructure from the database,
then runs the simulation loop broadcasting via Django Channels.
"""

import asyncio
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.realtime.simulation import FiberConfig, run_simulation_loop


class Command(BaseCommand):
    help = 'Run the traffic simulation engine (detections, incidents, SHM).'

    def handle(self, *args, **options):
        self.stdout.write('Loading fiber and infrastructure data...')

        fibers = self._load_fibers()
        infrastructure = self._load_infrastructure()

        self.stdout.write(self.style.SUCCESS(
            f'Starting simulation with {len(fibers)} fibers and {len(infrastructure)} infrastructure items.'
        ))

        asyncio.run(run_simulation_loop(fibers, infrastructure))

    def _get_data_dir(self) -> Path:
        """Get path to fiber cable data (infrastructure/clickhouse/cables/)."""
        return Path(settings.BASE_DIR).resolve().parent.parent.parent / 'infrastructure' / 'clickhouse' / 'cables'

    def _load_fibers(self) -> list[FiberConfig]:
        """Load fiber configs from JSON data files."""
        data_dir = self._get_data_dir()

        fiber_files = [
            ('carros.json', {'lanes': 6, 'speed_limit': 110, 'traffic_density': 'high'}),
            ('promenade.json', {'lanes': 4, 'speed_limit': 50, 'traffic_density': 'medium'}),
            ('mathis_raw.json', {'lanes': 4, 'speed_limit': 90, 'traffic_density': 'low'}),
        ]

        fibers = []
        for filename, config in fiber_files:
            path = data_dir / filename
            if not path.exists():
                self.stderr.write(f'Warning: {path} not found, skipping')
                continue

            with open(path) as f:
                data = json.load(f)

            coords = [
                c for c in data['coordinates']
                if c[0] is not None and c[1] is not None
            ]

            fibers.append(FiberConfig(
                id=data['id'],
                name=data['name'],
                color=data.get('color', '#000000'),
                coordinates=coords,
                channel_count=len(coords),
                **config,
            ))
            self.stdout.write(f'  Loaded {data["name"]} ({len(coords)} channels)')

        return fibers

    def _load_infrastructure(self) -> list[dict]:
        """Load infrastructure from JSON data file."""
        path = self._get_data_dir() / 'infrastructure.json'
        if not path.exists():
            self.stderr.write(f'Warning: {path} not found')
            return []

        with open(path) as f:
            data = json.load(f)

        self.stdout.write(f'  Loaded {len(data)} infrastructure items')
        return data
