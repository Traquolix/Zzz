"""
DRF permission classes for org-scoping.

Usage:
    permission_classes = [IsActiveUser]   # authenticated + active org
"""

from rest_framework.permissions import BasePermission


class IsActiveUser(BasePermission):
    """
    Allows access only to authenticated users whose account is active
    and whose organization (if any) is also active.

    Superusers bypass the organization check.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if not user.is_active:
            return False
        # Superusers bypass org check
        if user.is_superuser:
            return True
        # Non-superusers must belong to an active organization
        org = getattr(user, 'organization', None)
        if org is None:
            return False
        if not org.is_active:
            return False
        return True


class IsNotViewer(BasePermission):
    """
    Rejects users with viewer role (including API key service users).
    Use on write endpoints that should not be accessible via API keys.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return getattr(user, 'role', None) != 'viewer'
