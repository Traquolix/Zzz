"""
Audit logging service.

Provides a simple interface to record audit events from views and services.
"""

import ipaddress
import logging
import re

from django.conf import settings

from apps.shared.models import AuditLog

logger = logging.getLogger('sequoia.audit')

# IP address validation regex
_IP_PATTERN = re.compile(r'^[\d.:a-fA-F]+$')


def _is_valid_ip(ip_str: str) -> bool:
    """Check if a string is a valid IPv4 or IPv6 address."""
    try:
        ipaddress.ip_address(ip_str.strip())
        return True
    except ValueError:
        return False


def _is_trusted_proxy(ip_str: str) -> bool:
    """
    Check if an IP is a trusted proxy.

    Configure trusted proxies in settings.TRUSTED_PROXY_IPS (list of IPs or CIDRs).
    If not configured, only private/loopback IPs are trusted.
    """
    trusted_proxies = getattr(settings, 'TRUSTED_PROXY_IPS', None)

    try:
        ip = ipaddress.ip_address(ip_str.strip())
    except ValueError:
        return False

    # If no explicit trusted proxies configured, trust private/loopback only
    if trusted_proxies is None:
        return ip.is_private or ip.is_loopback

    # Check against configured trusted proxies
    for trusted in trusted_proxies:
        try:
            if '/' in trusted:
                # CIDR notation
                if ip in ipaddress.ip_network(trusted, strict=False):
                    return True
            else:
                # Single IP
                if ip == ipaddress.ip_address(trusted):
                    return True
        except ValueError:
            continue

    return False


def get_client_ip(request):
    """
    Extract client IP from request, safely handling proxies.

    Security considerations:
    - X-Forwarded-For can be spoofed by clients
    - Only trust X-Forwarded-For if the direct connection is from a trusted proxy
    - Use rightmost untrusted IP in chain (most recently added by our infrastructure)
    """
    remote_addr = request.META.get('REMOTE_ADDR', '')

    # If no proxy header or direct connection isn't from trusted proxy, use REMOTE_ADDR
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if not x_forwarded_for:
        return remote_addr if _is_valid_ip(remote_addr) else None

    if not _is_trusted_proxy(remote_addr):
        # Direct connection isn't from a trusted proxy - don't trust X-Forwarded-For
        logger.debug('Ignoring X-Forwarded-For from untrusted source %s', remote_addr)
        return remote_addr if _is_valid_ip(remote_addr) else None

    # Parse X-Forwarded-For from right to left, finding first non-proxy IP
    # Format: "client, proxy1, proxy2" (rightmost is most recent)
    ips = [ip.strip() for ip in x_forwarded_for.split(',')]

    # Walk from right to left, skipping trusted proxies
    for ip in reversed(ips):
        if not _is_valid_ip(ip):
            continue
        if not _is_trusted_proxy(ip):
            return ip

    # All IPs in chain are trusted proxies - use leftmost (original client)
    for ip in ips:
        if _is_valid_ip(ip):
            return ip

    return remote_addr if _is_valid_ip(remote_addr) else None


class AuditService:
    """
    Service for creating audit log entries.

    Usage:
        AuditService.log(
            request=request,
            action=AuditLog.Action.LOGIN_SUCCESS,
            object_type='User',
            object_id=str(user.id),
            changes={'username': user.username},
        )
    """

    @staticmethod
    def log(
        request,
        action,
        object_type='',
        object_id='',
        changes=None,
        organization=None,
        user=None,
    ):
        if changes is None:
            changes = {}

        acting_user = user or getattr(request, 'user', None)
        org = organization
        if org is None and acting_user and hasattr(acting_user, 'organization'):
            org = acting_user.organization

        ip = get_client_ip(request)

        try:
            entry = AuditLog.objects.create(
                organization=org,
                user=acting_user if acting_user and acting_user.is_authenticated else None,
                action=action,
                object_type=str(object_type),
                object_id=str(object_id),
                changes=changes,
                ip_address=ip,
            )
            logger.info(
                'Audit: %s by user=%s org=%s object=%s:%s',
                action,
                acting_user.id if acting_user and acting_user.is_authenticated else None,
                org.id if org else None,
                object_type,
                object_id,
            )
            return entry
        except Exception:
            logger.exception('Failed to create audit log entry for action=%s', action)
            return None

