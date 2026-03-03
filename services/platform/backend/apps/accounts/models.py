"""
User authentication models.
"""

import logging
import uuid

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.contrib.auth.models import AbstractUser

from apps.shared.constants import ALL_WIDGETS, ALL_LAYERS, USER_ROLES

logger = logging.getLogger('sequoia.accounts')


class User(AbstractUser):
    """
    Custom user model with organization tenancy and widget/layer permissions.

    Uses username-based auth (matching the existing frontend).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.PROTECT,
        related_name='users',
        null=True, blank=True,
        help_text='Required for non-superuser accounts.',
    )
    role = models.CharField(
        max_length=50,
        choices=USER_ROLES,
        default='viewer',
    )

    # Widget and layer access
    allowed_widgets = models.JSONField(
        default=list,
        blank=True,
        help_text='List of widget keys this user can access.',
    )
    allowed_layers = models.JSONField(
        default=list,
        blank=True,
        help_text='List of map layer keys this user can access.',
    )

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        ordering = ['username']

    def __str__(self):
        return self.username

    def clean(self):
        super().clean()
        if not self.is_superuser and self.organization is None:
            raise ValidationError(
                {'organization': 'Non-superuser accounts must belong to an organization.'}
            )

    def save(self, *args, **kwargs):
        # Enforce org validation at save time (not just in forms)
        self.full_clean(exclude=['password'])
        # Inheritance chain for widgets/layers:
        #   1. Per-user explicit value (non-empty) → keep it
        #   2. Organization settings (if org has non-empty list) → inherit
        #   3. Role-based defaults → fallback
        if not self.allowed_widgets:
            self.allowed_widgets = self._inherit_or_default_widgets()
        if not self.allowed_layers:
            self.allowed_layers = self._inherit_or_default_layers()
        super().save(*args, **kwargs)

    def _inherit_or_default_widgets(self):
        """Try org settings, then fall back to role defaults."""
        if self.organization_id:
            try:
                org_widgets = self.organization.settings.allowed_widgets
                if org_widgets:
                    return list(org_widgets)
            except ObjectDoesNotExist:
                # Org has no settings record — fall through to defaults
                pass
            except AttributeError:
                # Organization relation not loaded — fall through to defaults
                logger.warning('Could not load org settings for user %s', self.pk)
        if self.role in ('admin', 'operator'):
            return list(ALL_WIDGETS)
        from apps.shared.constants import VIEWER_WIDGETS
        return list(VIEWER_WIDGETS)

    def _inherit_or_default_layers(self):
        """Try org settings, then fall back to role defaults."""
        if self.organization_id:
            try:
                org_layers = self.organization.settings.allowed_layers
                if org_layers:
                    return list(org_layers)
            except ObjectDoesNotExist:
                # Org has no settings record — fall through to defaults
                pass
            except AttributeError:
                # Organization relation not loaded — fall through to defaults
                logger.warning('Could not load org settings for user %s', self.pk)
        if self.role in ('admin', 'operator'):
            return list(ALL_LAYERS)
        from apps.shared.constants import VIEWER_LAYERS
        return list(VIEWER_LAYERS)
