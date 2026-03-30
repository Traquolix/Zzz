"""
Signal-based audit logging.

Auto-tracks create/update/delete on key models (User, Infrastructure,
Organization, OrganizationSettings) without requiring explicit
AuditService.log() calls in every view.

Signals are connected with explicit sender= in connect_audit_signals(),
called from SharedConfig.ready(), so handlers only fire for tracked models.

LIMITATION: Signal-based audit does not capture the *user who performed*
the action because Django signals don't have access to the request context.
For user-attributed audit entries, use AuditService.log() in the view layer.
"""

import logging

from django.db.models.signals import post_delete, post_save

from apps.shared.models import AuditLog

logger = logging.getLogger("sequoia.shared.signals")


def _get_org(instance):
    """Extract organization from instance if available."""
    if hasattr(instance, "organization"):
        return instance.organization
    # OrganizationSettings -> organization is the FK
    if hasattr(instance, "organization_id"):
        return getattr(instance, "organization", None)
    # Organization itself
    if instance.__class__.__name__ == "Organization":
        return instance
    return None


def _build_changes(instance, created):
    """Build a changes dict from the instance fields."""
    changes = {}
    for field in instance._meta.concrete_fields:
        name = field.name
        if name in ("password", "id", "pk"):
            continue
        value = getattr(instance, name, None)
        if value is not None:
            # Convert non-serializable types
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            elif hasattr(value, "pk"):
                value = str(value.pk)
            else:
                value = (
                    str(value)
                    if not isinstance(value, str | int | float | bool | list | dict)
                    else value
                )
            changes[name] = value
    return changes


def audit_post_save(sender, instance, created, **kwargs):
    """Log create/update for tracked models."""
    model_name = sender.__name__
    action = _action_for_save(model_name, created)
    if action is None:
        return

    try:
        AuditLog.objects.create(
            organization=_get_org(instance),
            action=action,
            object_type=model_name,
            object_id=str(instance.pk),
            changes=_build_changes(instance, created),
        )
    except Exception:
        logger.exception("Signal audit failed for %s %s", model_name, instance.pk)


def audit_post_delete(sender, instance, **kwargs):
    """Log delete for tracked models."""
    model_name = sender.__name__
    action = _action_for_delete(model_name)
    if action is None:
        return

    try:
        AuditLog.objects.create(
            organization=_get_org(instance),
            action=action,
            object_type=model_name,
            object_id=str(instance.pk),
            changes={"deleted": True},
        )
    except Exception:
        logger.exception("Signal audit failed for delete %s %s", model_name, instance.pk)


def connect_audit_signals():
    """Connect audit signals to specific tracked models only.

    Called from SharedConfig.ready() to avoid circular imports and ensure
    signals only fire for models we actually track.
    """
    from apps.accounts.models import User
    from apps.monitoring.models import Infrastructure
    from apps.organizations.models import Organization, OrganizationSettings

    for model in (User, Infrastructure, Organization, OrganizationSettings):
        post_save.connect(audit_post_save, sender=model)
        post_delete.connect(audit_post_delete, sender=model)


def _action_for_save(model_name, created):
    """Map model + created flag to an AuditLog.Action value."""
    if model_name == "User":
        return AuditLog.Action.USER_CREATED if created else AuditLog.Action.USER_UPDATED
    if model_name == "Infrastructure":
        return AuditLog.Action.INFRASTRUCTURE_UPDATED
    if model_name == "Organization" or model_name == "OrganizationSettings":
        return AuditLog.Action.ORG_SETTINGS_UPDATED
    return None


def _action_for_delete(model_name):
    """Map model to a delete AuditLog.Action value."""
    if model_name == "User":
        return AuditLog.Action.USER_DELETED
    if model_name == "Infrastructure":
        return AuditLog.Action.INFRASTRUCTURE_UPDATED
    return None
