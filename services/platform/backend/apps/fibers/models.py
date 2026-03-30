"""
Fiber models — cable geometry and org assignment.

FiberCable stores the physical fiber data (coordinates, directional paths,
landmarks) in PostgreSQL. The authoritative sources are the JSON cable files
(geometry) and ``fibers.yaml`` (data coverage ranges); PostgreSQL is a cached
copy synced on startup via ``sync_fiber_data``.
All runtime queries (REST API, realtime loops) read from PostgreSQL.

FiberAssignment maps fibers to organizations for multi-tenant scoping.
One fiber can be assigned to multiple orgs (shared infrastructure).
"""

import uuid

from django.db import models


class FiberCable(models.Model):
    """
    Physical fiber cable with geometry data.

    Synced from JSON cable files and ``fibers.yaml`` into PostgreSQL on startup
    (see ``sync_fiber_data``).
    Simulation-specific calibration (lanes, speed limits, etc.) lives separately
    in ``apps.realtime.simulation_config``.
    """

    id = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=200)
    color = models.CharField(max_length=20, default="#000000")

    # Channel coordinates: [[lng, lat], ...] — one entry per DAS channel.
    # Null entries ([null, null]) represent dead/unmapped channels.
    coordinates = models.JSONField(
        default=list,
        help_text="Per-channel [lng, lat] coordinates.",
    )

    # Pre-computed road-snapped paths per direction: {"0": [[lng,lat],...], "1": [[lng,lat],...]}
    directional_paths = models.JSONField(
        default=dict,
        blank=True,
        help_text="Direction-specific coordinates for map rendering.",
    )

    # Per-channel landmark labels: ["", "Pont Napoléon", "", ...]
    landmark_labels = models.JSONField(
        default=list,
        blank=True,
        help_text="Landmark name per channel index (empty string = no landmark).",
    )

    # Channel ranges with active pipeline data processing.
    # Populated from fibers.yaml sections by sync_fiber_data.
    # Example: [{"start": 1200, "end": 1716}, {"start": 1716, "end": 2232}]
    data_coverage = models.JSONField(
        default=list,
        blank=True,
        help_text='Active channel ranges: [{"start": 1200, "end": 1716}, ...]',
    )

    # Denormalized count — set by sync_fiber_data from len(coordinates).
    # Avoids loading the full coordinates JSON just to count channels.
    channel_count = models.IntegerField(
        default=0,
        help_text="Number of DAS channels (= len(coordinates)).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Fiber cables"

    def __str__(self):
        return f"{self.name} ({self.id})"


class FiberAssignment(models.Model):
    """Maps a fiber_id to an organization for multi-tenant scoping."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="fiber_assignments",
    )
    fiber_id = models.CharField(
        max_length=100,
        help_text="Matches FiberCable.id.",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("organization", "fiber_id")
        ordering = ["organization", "fiber_id"]

    def __str__(self):
        return f"{self.fiber_id} → {self.organization.name}"
