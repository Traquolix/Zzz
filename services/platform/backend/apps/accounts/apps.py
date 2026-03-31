from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Accounts"

    def ready(self) -> None:
        from django.db.models.signals import post_delete, post_save

        from apps.accounts.models import User
        from apps.shared.signals import audit_post_delete, audit_post_save

        post_save.connect(audit_post_save, sender=User, dispatch_uid="audit_user_save")
        post_delete.connect(audit_post_delete, sender=User, dispatch_uid="audit_user_delete")
