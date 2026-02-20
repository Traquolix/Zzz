"""
Organization and settings models.
"""

import uuid
from django.db import models
from django.utils.text import slugify


class Organization(models.Model):
    """
    The top-level tenant. All data is scoped to an organization.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Organization.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class OrganizationSettings(models.Model):
    """
    Per-organization configuration. One-to-one with Organization.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name='settings',
    )
    timezone = models.CharField(max_length=50, default='Europe/Paris')

    # Alert thresholds
    speed_alert_threshold = models.FloatField(
        default=20.0,
        help_text='Speed (km/h) below which to flag slowdown alerts.',
    )
    incident_auto_resolve_minutes = models.PositiveIntegerField(
        default=30,
        help_text='Auto-resolve incidents after N minutes of no updates.',
    )

    # Feature toggles
    shm_enabled = models.BooleanField(
        default=True,
        help_text='Enable structural health monitoring widget.',
    )

    # Tenant-scoped widget/layer access (empty list = unrestricted)
    allowed_widgets = models.JSONField(
        default=list,
        blank=True,
        help_text='Widget keys this org can access. Empty = all widgets.',
    )
    allowed_layers = models.JSONField(
        default=list,
        blank=True,
        help_text='Map layer keys this org can access. Empty = all layers.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Organization settings'

    def __str__(self):
        return f"Settings for {self.organization.name}"
