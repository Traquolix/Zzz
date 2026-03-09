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

from apps.realtime.fiber_calibration import FIBER_CONFIGS
from apps.realtime.simulation import FiberConfig, run_simulation_loop


class Command(BaseCommand):
    help = "Run the traffic simulation engine (detections, incidents, SHM)."

    def handle(self, *args, **options):
        self.stdout.write("Loading fiber and infrastructure data...")

        fibers = self._load_fibers()
        infrastructure = self._load_infrastructure()

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting simulation with {len(fibers)} fibers and {len(infrastructure)} infrastructure items."
            )
        )

        asyncio.run(run_simulation_loop(fibers, infrastructure))

    def _get_data_dir(self) -> Path:
        """Get path to fiber cable data (infrastructure/clickhouse/cables/)."""
        return (
            Path(settings.BASE_DIR).resolve().parent.parent.parent
            / "infrastructure"
            / "clickhouse"
            / "cables"
        )

    def _load_fibers(self) -> list[FiberConfig]:
        """Load fiber configs from JSON data files with per-road calibration."""
        data_dir = self._get_data_dir()

        fibers = []
        for fiber_id, cfg in FIBER_CONFIGS.items():
            path = data_dir / f"{fiber_id}.json"
            if not path.exists():
                self.stderr.write(f"Warning: {path} not found, skipping")
                continue

            with open(path) as f:
                data = json.load(f)

            coords = [c for c in data["coordinates"] if c[0] is not None and c[1] is not None]

            fibers.append(
                FiberConfig(
                    id=data["id"],
                    name=data["name"],
                    color=data.get("color", "#000000"),
                    coordinates=coords,
                    channel_count=len(coords),
                    lanes=cfg["lanes"],
                    speed_limit=cfg["speed_limit"],
                    traffic_density=cfg["traffic_density"],
                    typical_speed_range=cfg["typical_speed_range"],
                    max_channel_dir0=cfg["max_channel_dir0"],
                    max_channel_dir1=cfg["max_channel_dir1"],
                )
            )
            max_ch_0 = cfg["max_channel_dir0"] or len(coords)
            max_ch_1 = cfg["max_channel_dir1"] or len(coords)
            self.stdout.write(
                f"  Loaded {data['name']} ({len(coords)} channels, "
                f"dir0≤{max_ch_0}, dir1≤{max_ch_1}, "
                f"{cfg['speed_limit']}km/h, {cfg['traffic_density']} density)"
            )

        return fibers

    def _load_infrastructure(self) -> list[dict]:
        """Load infrastructure from JSON data file."""
        path = self._get_data_dir() / "infrastructure.json"
        if not path.exists():
            self.stderr.write(f"Warning: {path} not found")
            return []

        with open(path) as f:
            data = json.load(f)

        self.stdout.write(f"  Loaded {len(data)} infrastructure items")
        return list(data)
