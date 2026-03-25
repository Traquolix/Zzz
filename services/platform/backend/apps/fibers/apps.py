import logging

from django.apps import AppConfig

logger = logging.getLogger("sequoia.fibers")


def _get_channel_layer():
    """Import and return the default channel layer (lazy to avoid circular imports)."""
    from channels.layers import get_channel_layer as _get_layer

    return _get_layer()


def _broadcast_config_update(config_type: str) -> None:
    """Broadcast a config_updated event to all connected WebSocket clients."""
    try:
        from asgiref.sync import async_to_sync

        from apps.realtime.broadcast import broadcast_config_updated, load_fiber_org_map

        layer = _get_channel_layer()
        fiber_org_map = async_to_sync(load_fiber_org_map)()
        async_to_sync(broadcast_config_updated)(layer, config_type, fiber_org_map)
    except Exception:
        # Non-critical — frontend will pick up changes on next poll/refresh
        logger.debug("Could not broadcast %s config update (non-critical)", config_type)


def _on_fiber_assignment_change(sender, instance, **kwargs):
    from apps.fibers.utils import invalidate_fiber_org_map, invalidate_org_fiber_cache

    invalidate_org_fiber_cache(instance.organization_id)
    invalidate_fiber_org_map()

    # Notify the Kafka bridge to reload its fiber_org_map immediately
    try:
        from asgiref.sync import async_to_sync

        layer = _get_channel_layer()
        async_to_sync(layer.group_send)(
            "bridge_control",
            {"type": "refresh_fiber_map"},
        )
    except Exception:
        logger.debug("Could not send bridge refresh signal (non-critical)")

    _broadcast_config_update("fibers")


def _on_fiber_cable_change(sender, instance, **kwargs):
    _broadcast_config_update("fibers")


def _on_infrastructure_change(sender, instance, **kwargs):
    _broadcast_config_update("infrastructure")


class FibersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.fibers"
    verbose_name = "Fibers"

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from apps.fibers.models import FiberAssignment, FiberCable
        from apps.monitoring.models import Infrastructure

        post_save.connect(_on_fiber_assignment_change, sender=FiberAssignment)
        post_delete.connect(_on_fiber_assignment_change, sender=FiberAssignment)
        post_save.connect(_on_fiber_cable_change, sender=FiberCable)
        post_delete.connect(_on_fiber_cable_change, sender=FiberCable)
        post_save.connect(_on_infrastructure_change, sender=Infrastructure)
        post_delete.connect(_on_infrastructure_change, sender=Infrastructure)
