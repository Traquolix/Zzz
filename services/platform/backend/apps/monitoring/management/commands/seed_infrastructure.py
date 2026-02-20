"""
Management command to seed infrastructure data from JSON.
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.organizations.models import Organization
from apps.monitoring.models import Infrastructure


class Command(BaseCommand):
    help = 'Seed infrastructure data (bridges, tunnels) from JSON file.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default=None,
            help='Path to infrastructure JSON file. Defaults to server/data/infrastructure.json.',
        )
        parser.add_argument(
            '--org-slug',
            type=str,
            default='sequoia',
            help='Organization slug to assign infrastructure to.',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all existing infrastructure before seeding.',
        )

    def handle(self, *args, **options):
        # Resolve JSON file path
        if options['file']:
            json_path = Path(options['file'])
        else:
            # Default: look in infrastructure/clickhouse/cables/ from repo root
            data_dir = Path(settings.BASE_DIR).resolve().parent.parent.parent / 'infrastructure' / 'clickhouse' / 'cables'
            json_path = data_dir / 'infrastructure.json'

        if not json_path.exists():
            self.stderr.write(self.style.ERROR(f'File not found: {json_path}'))
            return

        # Get organization
        try:
            org = Organization.objects.get(slug=options['org_slug'])
        except Organization.DoesNotExist:
            self.stderr.write(self.style.ERROR(
                f'Organization "{options["org_slug"]}" not found. Run seed_users first.'
            ))
            return

        # Load infrastructure data from JSON
        with open(json_path) as f:
            data = json.load(f)

        # Clear existing if requested
        if options['clear']:
            deleted_count = Infrastructure.objects.filter(organization=org).delete()[0]
            self.stdout.write(f'Cleared {deleted_count} existing infrastructure records.')

        # Track IDs from JSON for cleanup
        json_ids = set(item['id'] for item in data)

        # Create/update infrastructure
        created_count = 0
        updated_count = 0
        for item in data:
            _, created = Infrastructure.objects.update_or_create(
                id=item['id'],
                defaults={
                    'organization': org,
                    'type': item['type'],
                    'name': item['name'],
                    'fiber_id': item['fiberId'],
                    'start_channel': item['startChannel'],
                    'end_channel': item['endChannel'],
                    'image': item.get('image', ''),
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        # Remove records not in JSON (unless --clear was used, which already cleared)
        if not options['clear']:
            orphans = Infrastructure.objects.filter(organization=org).exclude(id__in=json_ids)
            orphan_count = orphans.count()
            if orphan_count > 0:
                orphans.delete()
                self.stdout.write(f'Removed {orphan_count} orphaned records.')

        self.stdout.write(self.style.SUCCESS(
            f'Infrastructure seeded: {created_count} created, {updated_count} updated.'
        ))
