"""
Monitoring models — infrastructure stored in PostgreSQL.
Incidents and stats come from ClickHouse (no Django models needed).
"""

from django.db import models

from apps.shared.constants import INFRASTRUCTURE_TYPES


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
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='infrastructure',
    )
    type = models.CharField(max_length=20, choices=INFRASTRUCTURE_TYPES)
    name = models.CharField(max_length=200)
    fiber_id = models.CharField(
        max_length=100,
        help_text='ID of the fiber cable this infrastructure is on.',
    )
    start_channel = models.IntegerField(
        help_text='First DAS channel covering this infrastructure.',
    )
    end_channel = models.IntegerField(
        help_text='Last DAS channel covering this infrastructure.',
    )
    image = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Filename of infrastructure image (stored in media/infrastructure/).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Infrastructure'

    def __str__(self):
        return f'{self.name} ({self.type})'
