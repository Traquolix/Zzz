"""
Data migration: populate FiberCable from JSON cable files.

Reads from infrastructure/clickhouse/cables/*.json and seeds geometry data.
Simulation calibration (lanes, speed limits, etc.) is NOT stored in the DB —
it lives in apps.realtime.simulation_config.
"""

import json
from pathlib import Path

from django.conf import settings
from django.db import migrations

FIBER_IDS = ["carros", "promenade", "mathis"]


def seed_fiber_cables(apps, schema_editor):
    FiberCable = apps.get_model("fibers", "FiberCable")
    cables_dir = Path(settings.DATA_DIR) / "clickhouse" / "cables"

    for fiber_id in FIBER_IDS:
        path = cables_dir / f"{fiber_id}.json"
        if not path.exists():
            continue

        with open(path) as f:
            data = json.load(f)

        coordinates = data.get("coordinates", [])
        FiberCable.objects.update_or_create(
            id=fiber_id,
            defaults={
                "name": data.get("name", fiber_id),
                "color": data.get("color", "#000000"),
                "coordinates": coordinates,
                "channel_count": len(coordinates),
                "directional_paths": data.get("directional_paths", {}),
                "landmark_labels": data.get("landmark_labels", []),
            },
        )


def reverse_seed(apps, schema_editor):
    FiberCable = apps.get_model("fibers", "FiberCable")
    FiberCable.objects.filter(id__in=FIBER_IDS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("fibers", "0002_add_fiber_cable_model"),
    ]

    operations = [
        migrations.RunPython(seed_fiber_cables, reverse_seed),
    ]
