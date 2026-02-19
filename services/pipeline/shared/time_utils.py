"""
Time conversion utilities for nanosecond precision timestamps.

Centralizes timestamp conversions to eliminate magic numbers and ensure consistency.
"""

import time
from datetime import datetime, timezone

# Constants
NANOSECONDS_PER_SECOND = 1_000_000_000
NANOSECONDS_PER_MILLISECOND = 1_000_000


def datetime_to_nanoseconds(dt: datetime) -> int:
    """
    Convert datetime to nanoseconds since Unix epoch.

    Args:
        dt: Datetime object (timezone-aware or naive)

    Returns:
        Integer nanoseconds since epoch (1970-01-01 00:00:00 UTC)

    Example:
        >>> from datetime import datetime
        >>> dt = datetime(2024, 1, 1, 12, 0, 0)
        >>> ns = datetime_to_nanoseconds(dt)
        >>> ns
        1704110400000000000
    """
    return int(dt.timestamp() * NANOSECONDS_PER_SECOND)


def nanoseconds_to_datetime(ns: int) -> datetime:
    """
    Convert nanoseconds since Unix epoch to timezone-aware datetime (UTC).

    Args:
        ns: Integer nanoseconds since epoch

    Returns:
        Timezone-aware datetime in UTC

    Example:
        >>> ns = 1704110400000000000
        >>> dt = nanoseconds_to_datetime(ns)
        >>> dt
        datetime.datetime(2024, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)
    """
    return datetime.fromtimestamp(ns / NANOSECONDS_PER_SECOND, tz=timezone.utc)


def nanoseconds_to_milliseconds(ns: int) -> float:
    """
    Convert nanoseconds to milliseconds.

    Args:
        ns: Integer nanoseconds

    Returns:
        Float milliseconds

    Example:
        >>> nanoseconds_to_milliseconds(1_500_000_000)
        1500.0
    """
    return ns / NANOSECONDS_PER_MILLISECOND


def sample_duration_nanoseconds(sampling_rate_hz: float) -> int:
    """
    Calculate duration of one sample in nanoseconds for a given sampling rate.

    Args:
        sampling_rate_hz: Sampling rate in Hertz (samples per second)

    Returns:
        Integer nanoseconds per sample

    Example:
        >>> sample_duration_nanoseconds(10.0)  # 10Hz
        100000000  # 0.1 seconds = 100ms

        >>> sample_duration_nanoseconds(50.0)  # 50Hz
        20000000  # 0.02 seconds = 20ms
    """
    return int(NANOSECONDS_PER_SECOND / sampling_rate_hz)


def current_time_nanoseconds() -> int:
    """
    Get current time in nanoseconds since Unix epoch.

    Returns:
        Integer nanoseconds since epoch

    Example:
        >>> ns = current_time_nanoseconds()
        >>> isinstance(ns, int)
        True
    """
    return int(time.time() * NANOSECONDS_PER_SECOND)
