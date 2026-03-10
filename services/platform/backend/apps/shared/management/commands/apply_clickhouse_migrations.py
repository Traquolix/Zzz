"""
Management command to apply ClickHouse SQL migrations.

Reads .sql files from infrastructure/clickhouse/migrations/ in sorted order,
strips comments, splits on ';', and executes each statement via the shared
ClickHouse client (with circuit breaker and proper error handling).

All migrations are idempotent (IF NOT EXISTS / IF EXISTS) so this is safe
to re-run on every deploy.
"""

import re

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.shared.clickhouse import command as ch_command
from apps.shared.exceptions import ClickHouseUnavailableError


def _strip_comments(sql: str) -> str:
    """Remove SQL line comments (-- ...) so they don't interfere with splitting."""
    return re.sub(r"--[^\n]*", "", sql)


class Command(BaseCommand):
    help = "Apply ClickHouse SQL migrations from infrastructure/clickhouse/migrations/."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print statements without executing them.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        migration_dir = settings.DATA_DIR / "clickhouse" / "migrations"

        if not migration_dir.is_dir():
            self.stdout.write(f"  No migrations directory at {migration_dir}, skipping.")
            return

        sql_files = sorted(migration_dir.glob("*.sql"))
        if not sql_files:
            self.stdout.write("  No .sql files found, skipping.")
            return

        failed = False
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
                    failed = True
                    break  # Skip remaining statements in this file

            if not dry_run and not failed:
                self.stdout.write(self.style.SUCCESS(f"  Applied {name}"))

        if failed:
            raise SystemExit(1)
