"""
Domain exceptions for the SequoIA platform.
"""


class SequoiaServiceError(Exception):
    """Base exception for SequoIA service errors."""
    pass


class ClickHouseUnavailableError(SequoiaServiceError):
    """Raised when ClickHouse is unreachable or returns an error."""
    pass
