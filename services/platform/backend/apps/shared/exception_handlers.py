"""
Custom DRF exception handler.

Catches domain exceptions and converts them to proper HTTP responses
instead of letting them bubble as 500s.
"""

import logging

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Handle DRF exceptions, plus domain-specific exceptions."""
    response = exception_handler(exc, context)
    if response is not None:
        return response

    from apps.shared.exceptions import (
        SequoiaServiceError,
        ClickHouseUnavailableError,
    )

    if isinstance(exc, ClickHouseUnavailableError):
        return Response(
            {'detail': 'Analytics service temporarily unavailable.', 'code': 'analytics_unavailable'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if isinstance(exc, SequoiaServiceError):
        return Response(
            {'detail': str(exc), 'code': 'service_error'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Catch-all: log the real exception, return a generic JSON 500
    logger.exception("Unhandled exception in %s", context.get('view'))
    return Response(
        {'detail': 'Internal server error.', 'code': 'internal_error'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
