import logging

from django.apps import AppConfig

logger = logging.getLogger("sequoia.fibers")


def get_channel_layer():
    """Import and return the default channel layer (lazy to avoid circular imports)."""
    from channels.layers import get_channel_layer as _get_layer

    return _get_layer()


def _invalidate_caches(sender, instance, **kwargs):
    from apps.fibers.utils import invalidate_fiber_org_map, invalidate_org_fiber_cache

    invalidate_org_fiber_cache(instance.organization_id)
    invalidate_fiber_org_map()

    # Notify the Kafka bridge to reload its fiber_org_map immediately
    try:
        from asgiref.sync import async_to_sync

        layer = get_channel_layer()
        async_to_sync(layer.group_send)(
            "bridge_control",
            {"type": "refresh_fiber_map"},
        )
    except Exception:
        # Non-critical — the bridge will refresh via its periodic timer anyway
        logger.debug("Could not send bridge refresh signal (non-critical)")


class FibersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.fibers"
    verbose_name = "Fibers"

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from apps.fibers.models import FiberAssignment

        post_save.connect(_invalidate_caches, sender=FiberAssignment)
        post_delete.connect(_invalidate_caches, sender=FiberAssignment)
