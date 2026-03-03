"""
Management command to mark stale 'generating' reports as 'failed'.

Reports can get stuck in 'generating' if the worker process crashes mid-generation.
This command cleans them up so they don't appear as perpetually loading in the UI.

Usage:
    python manage.py cleanup_stale_reports [--max-age-minutes 30]
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.reporting.models import Report


class Command(BaseCommand):
    help = 'Mark stale generating reports as failed.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-age-minutes',
            type=int,
            default=30,
            dest='max_age_minutes',
            help='Reports generating for longer than this (minutes) are marked failed. Default: 30',
        )

    def handle(self, *args, **options):
        max_age = options['max_age_minutes']
        cutoff = timezone.now() - timedelta(minutes=max_age)

        count = Report.objects.filter(
            status='generating',
            created_at__lt=cutoff,
        ).update(status='failed')

        if count:
            self.stdout.write(self.style.WARNING(
                f'Marked {count} stale report(s) as failed (older than {max_age} min).'
            ))
        else:
            self.stdout.write('No stale reports found.')
