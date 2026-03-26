"""
Management command to apply ClickHouse SQL migrations.

Reads .sql files from infrastructure/clickhouse/migrations/ in sorted order,
strips comments, splits on ';', and executes each statement.

All operations are idempotent — safe to re-run on every deploy.
"""

import argparse
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


class Command(BaseCommand):
    help = "Apply ClickHouse SQL migrations."

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
                    raise SystemExit(1) from e

            if not dry_run:
                self.stdout.write(self.style.SUCCESS(f"  Applied {name}"))
