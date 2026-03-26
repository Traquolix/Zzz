"""
Custom middleware for the SequoIA platform.
"""

import logging
import time
import uuid

from django.utils.deprecation import MiddlewareMixin

from apps.shared.logging_utils import set_request_id

logger = logging.getLogger("sequoia.requests")


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Middleware that logs all API requests for debugging and audit purposes.

    Logs: method, path, status, duration, user, organization, IP, request ID.
    """

    SENSITIVE_PARAMS = frozenset(
        {
            "password",
            "token",
            "key",
            "secret",
            "authorization",
            "bearer",
            "api_key",
            "refresh_token",
            "access_token",
            "credential",
            "csrf",
        }
    )

    def process_request(self, request):
        request.start_time = time.time()
        request.request_id = str(uuid.uuid4())[:16]
        set_request_id(request.request_id)

    def process_response(self, request, response):
        if request.path.startswith("/static/") or request.path.startswith("/media/"):
            return response

        duration = None
        if hasattr(request, "start_time"):
            duration = (time.time() - request.start_time) * 1000

        user_info = "anonymous"
        org_info = None
        if hasattr(request, "user") and request.user.is_authenticated:
            user_info = request.user.username
            if hasattr(request.user, "organization") and request.user.organization:
                org_info = request.user.organization.name

        request_id = getattr(request, "request_id", "-")

        log_data = {
            "request_id": request_id,
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "duration_ms": round(duration, 2) if duration else None,
            "user": user_info,
            "org": org_info,
            "ip": self._get_client_ip(request),
        }

        if request.method == "GET" and request.GET:
            safe_params = {
                k: v for k, v in request.GET.items() if k.lower() not in self.SENSITIVE_PARAMS
            }
            if safe_params:
                log_data["params"] = safe_params

        msg = f"{log_data['method']} {log_data['path']} -> {log_data['status']}"
        if response.status_code >= 500:
            logger.error(msg, extra=log_data)
        elif response.status_code >= 400:
            logger.warning(msg, extra=log_data)
        else:
            logger.info(msg, extra=log_data)

        response["X-Request-ID"] = request_id
        return response

    def _get_client_ip(self, request):
        """Get client IP using the same secure logic as audit service."""
        from apps.shared.audit import get_client_ip

        ip = get_client_ip(request)
        return ip if ip else "-"
