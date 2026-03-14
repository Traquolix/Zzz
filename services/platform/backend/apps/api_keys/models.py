"""
API Key model for programmatic access to the SequoIA platform.

Keys are stored as SHA-256 hashes — the raw key is only returned once
at creation time (prefixed with 'sqk_').
"""

import hashlib
import secrets
import uuid

from django.conf import settings
from django.db import models


class APIKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    name = models.CharField(max_length=200)
    key_prefix = models.CharField(max_length=8, db_index=True)
    key_hash = models.CharField(max_length=64, unique=True)
    scopes = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_api_keys",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    request_count = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.key_prefix}...)"

    @classmethod
    def generate(cls, organization, name, created_by, expires_at=None, scopes=None):
        """Create a new API key and return (instance, raw_key).

        The raw key (prefixed with 'sqk_') is only available at creation.
        """
        raw_secret = secrets.token_urlsafe(32)
        raw_key = f"sqk_{raw_secret}"
        key_hash = hashlib.sha256(raw_secret.encode()).hexdigest()
        key_prefix = raw_secret[:8]

        instance = cls.objects.create(
            organization=organization,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes=scopes or [],
            created_by=created_by,
            expires_at=expires_at,
        )
        return instance, raw_key
