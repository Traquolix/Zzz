"""
Management command to check and trigger due report schedules.

Intended to be run from a periodic task (cron, systemd timer, APScheduler, etc).
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Check and trigger due report schedules"

    def handle(self, *args, **options):
        from apps.reporting.task_runner import run_scheduled_reports

        count = run_scheduled_reports()
        self.stdout.write(self.style.SUCCESS(f"Triggered {count} scheduled reports"))
