"""
Data migration: populate FiberCable from JSON cable files + calibration config.

Reads from infrastructure/clickhouse/cables/*.json and merges with the
calibration constants that were previously in fiber_calibration.py.
"""

import json
from pathlib import Path

from django.conf import settings
from django.db import migrations

# Calibration data (previously in apps/realtime/fiber_calibration.py)
FIBER_CONFIGS = {
    "carros": {
        "lanes": 6,
        "speed_limit": 110,
        "traffic_density": "high",
        "typical_speed_min": 80.0,
        "typical_speed_max": 110.0,
        "max_channel_dir0": None,
        "max_channel_dir1": None,
    },
    "promenade": {
        "lanes": 4,
        "speed_limit": 50,
        "traffic_density": "medium",
        "typical_speed_min": 30.0,
        "typical_speed_max": 50.0,
        "max_channel_dir0": 4177,
        "max_channel_dir1": 4178,
    },
    "mathis": {
        "lanes": 4,
        "speed_limit": 50,
        "traffic_density": "low",
        "typical_speed_min": 35.0,
        "typical_speed_max": 50.0,
        "max_channel_dir0": 687,
        "max_channel_dir1": 687,
    },
}


def seed_fiber_cables(apps, schema_editor):
    FiberCable = apps.get_model("fibers", "FiberCable")
    cables_dir = Path(settings.DATA_DIR) / "clickhouse" / "cables"

    for fiber_id, cfg in FIBER_CONFIGS.items():
        path = cables_dir / f"{fiber_id}.json"
        if not path.exists():
            continue

        with open(path) as f:
            data = json.load(f)

        FiberCable.objects.update_or_create(
            id=fiber_id,
            defaults={
                "name": data.get("name", fiber_id),
                "color": data.get("color", "#000000"),
                "coordinates": data.get("coordinates", []),
                "directional_paths": data.get("directional_paths", {}),
                "landmark_labels": data.get("landmark_labels", []),
                "lanes": cfg["lanes"],
                "speed_limit": cfg["speed_limit"],
                "traffic_density": cfg["traffic_density"],
                "typical_speed_min": cfg["typical_speed_min"],
                "typical_speed_max": cfg["typical_speed_max"],
                "max_channel_dir0": cfg["max_channel_dir0"],
                "max_channel_dir1": cfg["max_channel_dir1"],
            },
        )


def reverse_seed(apps, schema_editor):
    FiberCable = apps.get_model("fibers", "FiberCable")
    FiberCable.objects.filter(id__in=list(FIBER_CONFIGS.keys())).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("fibers", "0002_add_fiber_cable_model"),
    ]

    operations = [
        migrations.RunPython(seed_fiber_cables, reverse_seed),
    ]
