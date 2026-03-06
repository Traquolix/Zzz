"""
Permission classes for admin endpoints.

- IsAdminOrSuperuser: admin role in their org, or superuser
- IsSuperuser: superuser only
"""

from rest_framework.permissions import BasePermission


class IsAdminOrSuperuser(BasePermission):
    """
    Allows access to org admins (for their own org) and superusers.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        if user.is_superuser:
            return True
        return getattr(user, "role", None) == "admin"


class IsSuperuser(BasePermission):
    """Superuser-only access."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.is_superuser
