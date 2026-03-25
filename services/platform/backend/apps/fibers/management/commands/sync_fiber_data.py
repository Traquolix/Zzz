"""
Sync fiber and infrastructure data from JSON files into PostgreSQL.

JSON files are the source of truth. This command upserts (add/update/delete)
PostgreSQL rows to match. Safe to run on every startup.

Usage:
    python manage.py sync_fiber_data
    python manage.py sync_fiber_data --dry-run
"""

import json
import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger("sequoia.fibers")

# Calibration defaults per fiber — merged with JSON geometry data.
# These match the physical road characteristics of each fiber deployment.
FIBER_CALIBRATION: dict[str, dict] = {
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


def _get_cables_dir() -> Path:
    return Path(settings.DATA_DIR) / "clickhouse" / "cables"


def sync_fibers(dry_run: bool = False) -> dict[str, int]:
    """Sync FiberCable rows from JSON cable files. Returns {added, updated, deleted}."""
    from apps.fibers.models import FiberCable

    cables_dir = _get_cables_dir()
    stats = {"added": 0, "updated": 0, "deleted": 0}

    # Build desired state from JSON files
    desired: dict[str, dict] = {}
    for fiber_id, cal in FIBER_CALIBRATION.items():
        path = cables_dir / f"{fiber_id}.json"
        if not path.exists():
            logger.warning("Cable file not found: %s", path)
            continue

        with open(path) as f:
            data = json.load(f)

        desired[fiber_id] = {
            "name": data.get("name", fiber_id),
            "color": data.get("color", "#000000"),
            "coordinates": data.get("coordinates", []),
            "directional_paths": data.get("directional_paths", {}),
            "landmark_labels": data.get("landmark_labels", []),
            **cal,
        }

    if dry_run:
        existing_ids = set(FiberCable.objects.values_list("id", flat=True))
        desired_ids = set(desired.keys())
        stats["added"] = len(desired_ids - existing_ids)
        stats["deleted"] = len(existing_ids - desired_ids)
        stats["updated"] = len(desired_ids & existing_ids)
        return stats

    # Upsert
    for fiber_id, fields in desired.items():
        _, created = FiberCable.objects.update_or_create(id=fiber_id, defaults=fields)
        stats["added" if created else "updated"] += 1

    # Delete rows not in JSON
    deleted_count, _ = FiberCable.objects.exclude(id__in=desired.keys()).delete()
    stats["deleted"] = deleted_count

    return stats


def sync_infrastructure(dry_run: bool = False, org_slug: str = "sequoia") -> dict[str, int]:
    """Sync Infrastructure rows from infrastructure.json. Returns {added, updated, deleted}."""
    from apps.monitoring.models import Infrastructure
    from apps.organizations.models import Organization

    path = _get_cables_dir() / "infrastructure.json"
    stats = {"added": 0, "updated": 0, "deleted": 0}

    if not path.exists():
        logger.warning("Infrastructure file not found: %s", path)
        return stats

    with open(path) as f:
        items = json.load(f)

    if not isinstance(items, list):
        logger.error("infrastructure.json must be a list")
        return stats

    try:
        org = Organization.objects.get(slug=org_slug)
    except Organization.DoesNotExist:
        logger.warning("Organization '%s' not found, skipping infrastructure sync", org_slug)
        return stats

    desired_ids = set()
    for item in items:
        iid = item.get("id")
        if not iid:
            continue
        desired_ids.add(iid)

        if dry_run:
            continue

        _, created = Infrastructure.objects.update_or_create(
            id=iid,
            defaults={
                "organization": org,
                "type": item["type"],
                "name": item["name"],
                "fiber_id": item["fiberId"],
                "start_channel": item["startChannel"],
                "end_channel": item["endChannel"],
                "image": item.get("image", ""),
            },
        )
        stats["added" if created else "updated"] += 1

    if dry_run:
        existing_ids = set(Infrastructure.objects.values_list("id", flat=True))
        stats["added"] = len(desired_ids - existing_ids)
        stats["deleted"] = len(existing_ids - desired_ids)
        stats["updated"] = len(desired_ids & existing_ids)
        return stats

    # Delete rows not in JSON
    deleted_count, _ = Infrastructure.objects.exclude(id__in=desired_ids).delete()
    stats["deleted"] = deleted_count

    return stats


class Command(BaseCommand):
    help = "Sync fiber and infrastructure data from JSON files into PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would change.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        prefix = "[DRY RUN] " if dry_run else ""

        fiber_stats = sync_fibers(dry_run=dry_run)
        self.stdout.write(
            f"{prefix}Fibers: {fiber_stats['added']} added, "
            f"{fiber_stats['updated']} updated, {fiber_stats['deleted']} deleted"
        )

        infra_stats = sync_infrastructure(dry_run=dry_run)
        self.stdout.write(
            f"{prefix}Infrastructure: {infra_stats['added']} added, "
            f"{infra_stats['updated']} updated, {infra_stats['deleted']} deleted"
        )
