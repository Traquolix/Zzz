import uuid

from django.db import models

DEFAULT_TAGS = [
    ("critical", "#ef4444"),
    ("high", "#f97316"),
    ("medium", "#f59e0b"),
    ("low", "#22c55e"),
]


class Tag(models.Model):
    """Org-scoped incident tag with a display color.

    Four default tags (critical/high/medium/low) are seeded per org
    and marked is_locked=True — they cannot be deleted or renamed.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="tags",
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7, default="#6b7280")
    is_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("organization", "name")]

    def __str__(self) -> str:
        return f"{self.name} ({self.organization})"


class IncidentTags(models.Model):
    """Per-incident tag assignment stored in PostgreSQL.

    Tags are human-assigned classifications. ClickHouse stores immutable
    detection data; PostgreSQL owns mutable state (tags, workflow actions).
    """

    incident_id = models.CharField(max_length=100, unique=True, db_index=True)
    tags = models.JSONField(default=list)
    updated_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "incident tags"


def seed_default_tags(organization) -> None:
    """Create the 4 locked default tags for an organization (idempotent)."""
    for name, color in DEFAULT_TAGS:
        Tag.objects.get_or_create(
            organization=organization,
            name=name,
            defaults={"color": color, "is_locked": True},
        )
