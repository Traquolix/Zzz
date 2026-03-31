from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.organizations"
    verbose_name = "Organizations"

    def ready(self) -> None:
        from django.db.models.signals import post_delete, post_save

        from apps.organizations.models import Organization, OrganizationSettings
        from apps.shared.signals import audit_post_delete, audit_post_save

        for model in (Organization, OrganizationSettings):
            uid = f"audit_{model.__name__.lower()}"
            post_save.connect(audit_post_save, sender=model, dispatch_uid=f"{uid}_save")
            post_delete.connect(audit_post_delete, sender=model, dispatch_uid=f"{uid}_delete")
