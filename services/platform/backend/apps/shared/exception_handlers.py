"""
Custom DRF exception handler.

Normalizes all error responses to a consistent format:
  {
    "error": "error_code",
    "detail": "Human readable message",
    "status": 400
  }

Catches domain exceptions and converts them to proper HTTP responses
instead of letting them bubble as 500s.
"""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def _normalize_error_response(exc, http_status, error_code, detail_msg):
    """Create a normalized error response."""
    return Response(
        {
            "error": error_code,
            "detail": detail_msg,
            "status": http_status,
        },
        status=http_status,
    )


def custom_exception_handler(exc, context):
    """
    Handle DRF exceptions plus domain-specific exceptions.

    All error responses are normalized to the format:
      {
        "error": "error_code",
        "detail": "Human readable message",
        "status": <http_status_code>
      }
    """
    # Let DRF handle the exception first
    response = exception_handler(exc, context)

    if response is not None:
        # DRF already handled it — normalize the response
        http_status = response.status_code
        error_data = response.data

        # Extract error code and detail from DRF response
        # DRF's default format varies by exception type
        if isinstance(error_data, dict):
            # For validation errors, use field-level details or a generic code
            if "detail" in error_data:
                detail_msg = error_data["detail"]
            elif isinstance(error_data, dict) and any(k != "detail" for k in error_data):
                # Validation error with field details
                detail_msg = "Validation error. See response for details."
                normalized = _normalize_error_response(
                    exc, http_status, "validation_error", detail_msg
                )
                # Preserve field-level validation details
                normalized.data["fields"] = error_data
                return normalized
            else:
                detail_msg = str(error_data)
        else:
            detail_msg = str(error_data)

        # Map HTTP status to error code
        error_code_map = {
            status.HTTP_400_BAD_REQUEST: "bad_request",
            status.HTTP_401_UNAUTHORIZED: "unauthorized",
            status.HTTP_403_FORBIDDEN: "forbidden",
            status.HTTP_404_NOT_FOUND: "not_found",
            status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
            status.HTTP_409_CONFLICT: "conflict",
            status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
        }
        error_code = error_code_map.get(http_status, "api_error")

        return _normalize_error_response(exc, http_status, error_code, detail_msg)

    # Handle domain-specific exceptions
    from apps.shared.exceptions import (
        ClickHouseUnavailableError,
        SequoiaServiceError,
    )

    if isinstance(exc, ClickHouseUnavailableError):
        return _normalize_error_response(
            exc,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "analytics_unavailable",
            "Analytics service temporarily unavailable.",
        )

    if isinstance(exc, SequoiaServiceError):
        return _normalize_error_response(
            exc,
            status.HTTP_400_BAD_REQUEST,
            "service_error",
            str(exc),
        )

    # Catch-all: log the real exception, return a generic JSON 500
    logger.exception("Unhandled exception in %s", context.get("view"))
    return _normalize_error_response(
        exc,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "Internal server error.",
    )
