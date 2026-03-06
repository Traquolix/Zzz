"""
User dashboard and map preferences.
"""

from django.conf import settings
from django.db import models


class UserPreferences(models.Model):
    """
    Per-user dashboard and map configuration.

    Stores layout choices, widget visibility, map center/zoom,
    and any other persistent UI state.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="preferences",
    )
    dashboard = models.JSONField(
        default=dict,
        blank=True,
        help_text="Dashboard layout and widget configuration.",
    )
    map_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Map center, zoom, visible layers, etc.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "User preferences"

    def __str__(self):
        return f"Preferences for {self.user}"
