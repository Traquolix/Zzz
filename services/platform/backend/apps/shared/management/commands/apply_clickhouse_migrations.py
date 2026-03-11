"""
Management command to apply ClickHouse SQL migrations and load fiber cable data.

1. Reads .sql files from infrastructure/clickhouse/migrations/ in sorted order,
   strips comments, splits on ';', and executes each statement.
2. Loads fiber cable JSON files from infrastructure/clickhouse/cables/ and
   upserts them into the fiber_cables table (ReplacingMergeTree deduplicates).

All operations are idempotent — safe to re-run on every deploy.
"""

import argparse
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.shared.clickhouse import command as ch_command
from apps.shared.exceptions import ClickHouseUnavailableError


def _strip_comments(sql: str) -> str:
    """Remove SQL line comments (-- ...) and block comments (/* ... */)."""
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", "", sql)
    return sql


def _format_coord(coord: list) -> str:
    """Format a [lng, lat] pair as a ClickHouse tuple literal."""
    lng, lat = coord
    if lng is not None and lat is not None:
        return f"({float(lng)}, {float(lat)})"
    return "(NULL, NULL)"


def _build_cable_insert(data: dict) -> str:
    """Build an INSERT statement for a fiber cable JSON file."""
    fiber_id = data["id"]
    fiber_name = data.get("name", f"Cable {fiber_id.title()}")
    color = data.get("color", "#3b82f6")
    coordinates = data.get("coordinates", [])
    landmark_labels = data.get("landmark_labels")

    coord_str = ", ".join(_format_coord(c) for c in coordinates)

    if landmark_labels and len(landmark_labels) == len(coordinates):
        labels_str = ", ".join(f"'{label}'" if label else "NULL" for label in landmark_labels)
    else:
        labels_str = ", ".join("NULL" for _ in coordinates)

    return (
        "INSERT INTO sequoia.fiber_cables"
        " (fiber_id, fiber_name, channel_coordinates, landmark_labels, color)"
        f" VALUES ('{fiber_id}', '{fiber_name}', [{coord_str}], [{labels_str}], '{color}')"
    )


class Command(BaseCommand):
    help = "Apply ClickHouse SQL migrations and load fiber cable data."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print statements without executing them.",
        )

    def handle(self, *args: object, **options: object) -> None:
        dry_run = options["dry_run"]
        ch_dir: Path = settings.DATA_DIR / "clickhouse"

        self._apply_sql_migrations(ch_dir / "migrations", dry_run)
        self._load_cable_data(ch_dir / "cables", dry_run)

    def _apply_sql_migrations(self, migration_dir: Path, dry_run: bool) -> None:
        """Apply all .sql migration files in sorted order."""
        if not migration_dir.is_dir():
            self.stdout.write(f"  No migrations directory at {migration_dir}, skipping.")
            return

        sql_files = sorted(migration_dir.glob("*.sql"))
        if not sql_files:
            self.stdout.write("  No .sql files found, skipping.")
            return

        for sql_file in sql_files:
            name = sql_file.name
            raw_sql = sql_file.read_text()
            clean_sql = _strip_comments(raw_sql)

            statements = [s.strip() for s in clean_sql.split(";") if s.strip()]
            if not statements:
                self.stdout.write(f"  {name}: no statements, skipping.")
                continue

            for i, stmt in enumerate(statements, 1):
                if dry_run:
                    self.stdout.write(f"  [DRY RUN] {name} stmt {i}: {stmt[:200]}")
                    continue

                try:
                    ch_command(stmt)
                except ClickHouseUnavailableError as e:
                    sql_preview = stmt[:200]
                    self.stderr.write(
                        self.style.ERROR(f"  {name} stmt {i} FAILED: {e}\n    SQL: {sql_preview}")
                    )
                    raise SystemExit(1)

            if not dry_run:
                self.stdout.write(self.style.SUCCESS(f"  Applied {name}"))

    def _load_cable_data(self, cables_dir: Path, dry_run: bool) -> None:
        """Load fiber cable JSON files into ClickHouse."""
        if not cables_dir.is_dir():
            self.stdout.write(f"  No cables directory at {cables_dir}, skipping.")
            return

        json_files = sorted(cables_dir.glob("*.json"))
        for json_file in json_files:
            # Skip non-fiber files (e.g. infrastructure.json)
            try:
                data = json.loads(json_file.read_text())
            except (json.JSONDecodeError, OSError) as e:
                self.stderr.write(self.style.WARNING(f"  {json_file.name}: skipped ({e})"))
                continue

            if not isinstance(data, dict) or "coordinates" not in data:
                continue

            fiber_id = data.get("id", json_file.stem)

            if dry_run:
                coord_count = len(data.get("coordinates", []))
                self.stdout.write(
                    f"  [DRY RUN] {json_file.name}: INSERT {fiber_id} ({coord_count} channels)"
                )
                continue

            try:
                stmt = _build_cable_insert(data)
                ch_command(stmt)
                self.stdout.write(self.style.SUCCESS(f"  Loaded cable data: {fiber_id}"))
            except ClickHouseUnavailableError as e:
                self.stderr.write(self.style.ERROR(f"  {json_file.name} FAILED: {e}"))
                raise SystemExit(1)
