"""
Fiber assignment model — maps fibers to organizations for multi-tenant scoping.

Fibers exist in ClickHouse (fiber_cables table). This PostgreSQL model tracks
which organization(s) own each fiber, enabling org-scoped data isolation across
REST endpoints and WebSocket streams.

One fiber can be assigned to multiple orgs (shared infrastructure).
"""

import uuid

from django.db import models


class FiberAssignment(models.Model):
    """Maps a fiber_id (from ClickHouse) to an organization."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="fiber_assignments",
    )
    fiber_id = models.CharField(
        max_length=100,
        help_text="Matches fiber_cables.fiber_id in ClickHouse.",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("organization", "fiber_id")
        ordering = ["organization", "fiber_id"]

    def __str__(self):
        return f"{self.fiber_id} → {self.organization.name}"
