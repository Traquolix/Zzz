"""
Shared models used across the application.
"""

import uuid

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """
    Immutable audit trail for sensitive actions.

    Records authentication events, preference changes, user management,
    and other security-relevant operations.
    """

    class Action(models.TextChoices):
        # Authentication
        LOGIN_SUCCESS = "auth.login", "Login success"
        LOGIN_FAILED = "auth.login_failed", "Login failed"
        PASSWORD_CHANGED = "auth.password_changed", "Password changed"

        # User management
        USER_CREATED = "user.created", "User created"
        USER_UPDATED = "user.updated", "User updated"
        USER_DELETED = "user.deleted", "User deleted"
        ROLE_ASSIGNED = "role.assigned", "Role assigned"

        # Organization
        ORG_SETTINGS_UPDATED = "org.settings_updated", "Organization settings updated"

        # Preferences
        PREFERENCES_UPDATED = "preferences.updated", "Preferences updated"

        # Incidents
        INCIDENT_UPDATED = "incident.updated", "Incident updated"
        INCIDENT_RESOLVED = "incident.resolved", "Incident resolved"

        # Infrastructure
        INFRASTRUCTURE_UPDATED = "infrastructure.updated", "Infrastructure updated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        help_text="The user who performed the action.",
    )
    action = models.CharField(max_length=50, choices=Action.choices, db_index=True)
    object_type = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text='The type of object affected (e.g. "User", "Infrastructure").',
    )
    object_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="The ID of the affected object.",
    )
    changes = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON describing what changed.",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self):
        return f"{self.action} by {self.user_id} at {self.created_at}"
