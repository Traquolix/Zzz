"""
Management command to seed default organizations, users, and fiber assignments.

Only runs in DEBUG mode to prevent accidental creation of default
credentials in production.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.fibers.models import FiberAssignment
from apps.incidents.models import seed_default_tags
from apps.organizations.models import Organization, OrganizationSettings
from apps.shared.constants import ALL_LAYERS, ALL_WIDGETS, VIEWER_LAYERS, VIEWER_WIDGETS

# All fiber IDs from fibers.yaml
ALL_FIBER_IDS = ["carros", "mathis", "promenade"]

# Traffic-only widgets and layers for the restricted demo org
TRAFFIC_WIDGETS = ["map", "traffic_monitor", "incidents"]
TRAFFIC_LAYERS = [
    "cables",
    "fibers",
    "vehicles",
    "heatmap",
    "landmarks",
    "sections",
    "detections",
    "incidents",
]


class Command(BaseCommand):
    help = "Create organizations, seed users, and assign fibers. Only works in DEBUG mode."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            self.stderr.write(
                self.style.ERROR(
                    "seed_users is disabled in production (DEBUG=False). "
                    "Create users via Django admin or manage.py createsuperuser."
                )
            )
            return

        # ---- Default organization (all fibers, all access) ----
        org, created = Organization.objects.get_or_create(
            slug="sequoia",
            defaults={"name": "SequoIA"},
        )
        if created:
            OrganizationSettings.objects.create(organization=org)
            self.stdout.write(self.style.SUCCESS(f"Created organization: {org.name}"))
        else:
            self.stdout.write(f"Organization already exists: {org.name}")

        seed_default_tags(org)

        # Assign all fibers to default org
        for fid in ALL_FIBER_IDS:
            _, fa_created = FiberAssignment.objects.get_or_create(
                organization=org,
                fiber_id=fid,
            )
            if fa_created:
                self.stdout.write(self.style.SUCCESS(f"  Assigned fiber {fid} to {org.name}"))

        # Create admin user
        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@sequoia.local",
                "organization": org,
                "role": "admin",
                "is_staff": True,
                "allowed_widgets": list(ALL_WIDGETS),
                "allowed_layers": list(ALL_LAYERS),
            },
        )
        if created:
            admin.set_password("admin")
            admin.save()
            self.stdout.write(self.style.SUCCESS("Created admin user (password: admin)"))
        else:
            # Always sync permissions to latest ALL_WIDGETS / ALL_LAYERS
            updated = False
            if set(admin.allowed_widgets) != set(ALL_WIDGETS):
                admin.allowed_widgets = list(ALL_WIDGETS)
                updated = True
            if set(admin.allowed_layers) != set(ALL_LAYERS):
                admin.allowed_layers = list(ALL_LAYERS)
                updated = True
            if updated:
                admin.save()
                self.stdout.write(self.style.SUCCESS("Updated admin permissions to latest"))
            else:
                self.stdout.write("Admin user already exists (permissions up to date)")

        # Create demo viewer user
        demo, created = User.objects.get_or_create(
            username="demo",
            defaults={
                "email": "demo@sequoia.local",
                "organization": org,
                "role": "viewer",
                "allowed_widgets": list(VIEWER_WIDGETS),
                "allowed_layers": list(VIEWER_LAYERS),
            },
        )
        if created:
            demo.set_password("demo")
            demo.save()
            self.stdout.write(self.style.SUCCESS("Created demo user (password: demo)"))
        else:
            self.stdout.write("Demo user already exists")

        # ---- Second demo organization (traffic-only, single fiber) ----
        acme, created = Organization.objects.get_or_create(
            slug="acme-traffic",
            defaults={"name": "ACME Traffic"},
        )
        if created:
            OrganizationSettings.objects.create(
                organization=acme,
                allowed_widgets=TRAFFIC_WIDGETS,
                allowed_layers=TRAFFIC_LAYERS,
            )
            self.stdout.write(self.style.SUCCESS(f"Created organization: {acme.name}"))
        else:
            self.stdout.write(f"Organization already exists: {acme.name}")

        seed_default_tags(acme)

        # Assign only carros fiber to ACME
        _, fa_created = FiberAssignment.objects.get_or_create(
            organization=acme,
            fiber_id="carros",
        )
        if fa_created:
            self.stdout.write(self.style.SUCCESS(f"  Assigned fiber carros to {acme.name}"))

        # Create ACME user
        acme_user, created = User.objects.get_or_create(
            username="acme",
            defaults={
                "email": "user@acme-traffic.local",
                "organization": acme,
                "role": "operator",
                "allowed_widgets": TRAFFIC_WIDGETS,
                "allowed_layers": TRAFFIC_LAYERS,
            },
        )
        if created:
            acme_user.set_password("acme")
            acme_user.save()
            self.stdout.write(self.style.SUCCESS("Created ACME user (password: acme)"))
        else:
            self.stdout.write("ACME user already exists")

        self.stdout.write(self.style.SUCCESS("Seed complete."))
