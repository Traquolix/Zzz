from django.apps import AppConfig


class SharedConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.shared"
    verbose_name = "Shared"

    def ready(self):
        from apps.shared.signals import connect_audit_signals

        connect_audit_signals()
