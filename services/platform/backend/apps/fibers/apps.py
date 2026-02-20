from django.apps import AppConfig


class FibersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.fibers'
    verbose_name = 'Fibers'

    def ready(self):
        from django.db.models.signals import post_save, post_delete
        from apps.fibers.models import FiberAssignment

        def _invalidate_caches(sender, instance, **kwargs):
            from apps.fibers.utils import invalidate_org_fiber_cache, invalidate_fiber_org_map
            invalidate_org_fiber_cache(instance.organization_id)
            invalidate_fiber_org_map()

        post_save.connect(_invalidate_caches, sender=FiberAssignment)
        post_delete.connect(_invalidate_caches, sender=FiberAssignment)
