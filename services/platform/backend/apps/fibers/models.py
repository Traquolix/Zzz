"""
Fiber models — cable geometry, calibration, and org assignment.

FiberCable stores the physical fiber data (coordinates, calibration, directional
paths) in PostgreSQL. This is the single source of truth for fiber data, used by
both the REST API and the realtime loops.

FiberAssignment maps fibers to organizations for multi-tenant scoping.
One fiber can be assigned to multiple orgs (shared infrastructure).
"""

import uuid

from django.db import models


class FiberCable(models.Model):
    """
    Physical fiber cable with geometry and calibration data.

    Stored in PostgreSQL as the single source of truth. Previously split across
    ClickHouse (geometry), JSON files (raw coordinates), and a static Python
    file (calibration).
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

    # Calibration fields (previously in fiber_calibration.py)
    lanes = models.IntegerField(default=4)
    speed_limit = models.IntegerField(
        default=50,
        help_text="Road speed limit in km/h.",
    )
    traffic_density = models.CharField(
        max_length=20,
        default="medium",
        help_text="Traffic density: low, medium, high.",
    )
    typical_speed_min = models.FloatField(
        default=30.0,
        help_text="Typical free-flow speed range minimum (km/h).",
    )
    typical_speed_max = models.FloatField(
        default=50.0,
        help_text="Typical free-flow speed range maximum (km/h).",
    )
    max_channel_dir0 = models.IntegerField(
        null=True,
        blank=True,
        help_text="Last valid channel for direction 0 (null = full fiber).",
    )
    max_channel_dir1 = models.IntegerField(
        null=True,
        blank=True,
        help_text="Last valid channel for direction 1 (null = full fiber).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Fiber cables"

    def __str__(self):
        return f"{self.name} ({self.id})"

    @property
    def channel_count(self) -> int:
        return len(self.coordinates) if self.coordinates else 0

    @property
    def typical_speed_range(self) -> tuple[float, float]:
        return (self.typical_speed_min, self.typical_speed_max)


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
