"""
Request-scoped logging utilities using ContextVar for correlation IDs.

The RequestIdFilter attaches a `request_id` attribute to every log record,
enabling distributed tracing across Django request lifecycle and ClickHouse queries.
"""

import logging
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Inject request_id into every log record from the current context."""

    def filter(self, record):
        record.request_id = _request_id.get()
        return True


def set_request_id(rid: str) -> None:
    """Set the request ID for the current async/thread context."""
    _request_id.set(rid)


def get_request_id() -> str:
    """Get the request ID for the current context."""
    return _request_id.get()
