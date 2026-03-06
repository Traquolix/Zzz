"""
Monitoring models — infrastructure and incident workflow stored in PostgreSQL.
Raw incident detections come from ClickHouse; workflow state lives here.
"""

import uuid

from django.conf import settings
from django.db import models

from apps.shared.constants import INFRASTRUCTURE_TYPES

INCIDENT_STATUSES = [
    ("active", "Active"),
    ("acknowledged", "Acknowledged"),
    ("investigating", "Investigating"),
    ("resolved", "Resolved"),
]


class Infrastructure(models.Model):
    """
    Physical infrastructure (bridges, tunnels) monitored via DAS fibers.

    Stored in PostgreSQL because it's relatively static reference data
    that benefits from org-scoped tenant filtering.
    """

    # CharField PK: infrastructure IDs are human-readable slugs (e.g., "pont-napoleon-III")
    # assigned by operators during fiber deployment. Using CharField avoids an extra
    # lookup column and keeps ClickHouse cross-references straightforward.
    id = models.CharField(max_length=100, primary_key=True)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="infrastructure",
    )
    type = models.CharField(max_length=20, choices=INFRASTRUCTURE_TYPES)
    name = models.CharField(max_length=200)
    fiber_id = models.CharField(
        max_length=100,
        help_text="ID of the fiber cable this infrastructure is on.",
    )
    start_channel = models.IntegerField(
        help_text="First DAS channel covering this infrastructure.",
    )
    end_channel = models.IntegerField(
        help_text="Last DAS channel covering this infrastructure.",
    )
    image = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Filename of infrastructure image (stored in media/infrastructure/).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Infrastructure"

    def __str__(self):
        return f"{self.name} ({self.type})"


class IncidentAction(models.Model):
    """
    Workflow state transition for a ClickHouse incident.

    Each row records one operator action (acknowledge, investigate, resolve)
    plus an optional note. The incident_id is a string matching
    ClickHouse's fiber_incidents.incident_id — no FK because the source
    of truth for incident creation is ClickHouse.

    Current workflow status = to_status of the most recent action,
    or 'active' if no actions exist.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text="ClickHouse incident_id this action belongs to.",
    )
    from_status = models.CharField(max_length=20, choices=INCIDENT_STATUSES)
    to_status = models.CharField(max_length=20, choices=INCIDENT_STATUSES)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="incident_actions",
    )
    note = models.TextField(blank=True, default="")
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-performed_at"]
        indexes = [
            models.Index(fields=["incident_id", "-performed_at"]),
        ]

    def __str__(self):
        return f"{self.incident_id}: {self.from_status} → {self.to_status}"
