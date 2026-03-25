"""
Sync fiber and infrastructure data from JSON files into PostgreSQL and ClickHouse.

JSON files are the authoritative source. This command upserts PostgreSQL rows
to match and mirrors fiber geometry into the ClickHouse ``fiber_cables`` table
(used by the detection materialized view for coordinate enrichment).

Fibers are add/update only (no deletes); infrastructure deletes are org-scoped.
Safe to run on every startup.

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


def _get_cables_dir() -> Path:
    return Path(settings.DATA_DIR) / "clickhouse" / "cables"


def _ch_escape(value: str) -> str:
    """Escape a string for ClickHouse SQL literals (single-quote escaping)."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _format_coord(coord: list) -> str:
    """Format a [lng, lat] pair as a ClickHouse tuple literal."""
    lng, lat = coord
    if lng is not None and lat is not None:
        return f"({float(lng)}, {float(lat)})"
    return "(NULL, NULL)"


def _sync_fiber_to_clickhouse(fiber_id: str, fields: dict) -> None:
    """Upsert a single fiber into the ClickHouse fiber_cables table.

    The detection_kafka_mv materialized view JOINs on this table to enrich
    each detection with lat/lng coordinates.  ReplacingMergeTree deduplicates
    by fiber_id so a plain INSERT acts as an upsert.
    """
    from apps.shared.clickhouse import command as ch_command
    from apps.shared.exceptions import ClickHouseUnavailableError

    coordinates = fields.get("coordinates", [])
    landmark_labels = fields.get("landmark_labels", [])
    name = _ch_escape(fields.get("name", fiber_id))
    color = _ch_escape(fields.get("color", "#000000"))

    coord_str = ", ".join(_format_coord(c) for c in coordinates)

    if landmark_labels and len(landmark_labels) == len(coordinates):
        labels_str = ", ".join(
            f"'{_ch_escape(label)}'" if label else "NULL" for label in landmark_labels
        )
    else:
        labels_str = ", ".join("NULL" for _ in coordinates)

    stmt = (
        "INSERT INTO sequoia.fiber_cables"
        " (fiber_id, fiber_name, channel_coordinates, landmark_labels, color)"
        f" VALUES ('{_ch_escape(fiber_id)}', '{name}', [{coord_str}],"
        f" [{labels_str}], '{color}')"
    )

    try:
        ch_command(stmt)
    except ClickHouseUnavailableError:
        logger.warning("ClickHouse unavailable — skipped fiber_cables sync for %s", fiber_id)


def _discover_fiber_files(cables_dir: Path) -> dict[str, dict]:
    """Discover fiber JSON files and return {fiber_id: parsed_data}."""
    fibers: dict[str, dict] = {}
    for path in sorted(cables_dir.glob("*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Skipping %s: %s", path.name, e)
            continue

        # Only files with coordinates are fiber cables (skip infrastructure.json etc.)
        if not isinstance(data, dict) or "coordinates" not in data:
            continue

        fiber_id = data.get("id", path.stem)
        fibers[fiber_id] = data

    return fibers


def sync_fibers(dry_run: bool = False) -> dict[str, int]:
    """Sync FiberCable rows from JSON cable files. Returns {added, updated}."""
    from apps.fibers.models import FiberCable

    cables_dir = _get_cables_dir()
    stats = {"added": 0, "updated": 0}

    fiber_files = _discover_fiber_files(cables_dir)
    if not fiber_files:
        logger.warning("No fiber cable JSON files found in %s", cables_dir)
        return stats

    # Build desired state
    desired: dict[str, dict] = {}
    for fiber_id, data in fiber_files.items():
        coordinates = data.get("coordinates", [])
        desired[fiber_id] = {
            "name": data.get("name", fiber_id),
            "color": data.get("color", "#000000"),
            "coordinates": coordinates,
            "channel_count": len(coordinates),
            "directional_paths": data.get("directional_paths", {}),
            "landmark_labels": data.get("landmark_labels", []),
        }

    if dry_run:
        existing_ids = set(FiberCable.objects.values_list("id", flat=True))
        desired_ids = set(desired.keys())
        stats["added"] = len(desired_ids - existing_ids)
        stats["updated"] = len(desired_ids & existing_ids)
        return stats

    # Upsert only — never delete FiberCable rows that may have been created
    # manually or by another deployment. Orphan cleanup is an admin-only action.
    for fiber_id, fields in desired.items():
        _, created = FiberCable.objects.update_or_create(id=fiber_id, defaults=fields)
        stats["added" if created else "updated"] += 1
        _sync_fiber_to_clickhouse(fiber_id, fields)

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

    # Validate all items before any DB writes to avoid partial updates.
    required_fields = ("type", "name", "fiberId", "startChannel", "endChannel")
    valid_items: list[tuple[str, dict]] = []
    for item in items:
        iid = item.get("id")
        if not iid:
            continue
        missing = [f for f in required_fields if f not in item]
        if missing:
            raise ValueError(f"Infrastructure item '{iid}' is missing required fields: {missing}")
        valid_items.append((iid, item))

    desired_ids = {iid for iid, _ in valid_items}

    if not dry_run:
        for iid, item in valid_items:
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
        existing_ids = set(
            Infrastructure.objects.filter(organization=org).values_list("id", flat=True)
        )
        stats["added"] = len(desired_ids - existing_ids)
        stats["deleted"] = len(existing_ids - desired_ids)
        stats["updated"] = len(desired_ids & existing_ids)
        return stats

    # Delete rows not in JSON (scoped to this org only)
    deleted_count, _ = (
        Infrastructure.objects.filter(organization=org).exclude(id__in=desired_ids).delete()
    )
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
            f"{prefix}Fibers: {fiber_stats['added']} added, {fiber_stats['updated']} updated"
        )

        infra_stats = sync_infrastructure(dry_run=dry_run)
        self.stdout.write(
            f"{prefix}Infrastructure: {infra_stats['added']} added, "
            f"{infra_stats['updated']} updated, {infra_stats['deleted']} deleted"
        )
