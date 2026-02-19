"""Tests for time utility functions."""

import time
from datetime import datetime, timezone

from shared.time_utils import (
    NANOSECONDS_PER_SECOND,
    current_time_nanoseconds,
    datetime_to_nanoseconds,
    nanoseconds_to_datetime,
    nanoseconds_to_milliseconds,
    sample_duration_nanoseconds,
)


class TestDatetimeConversions:
    """Test datetime <-> nanoseconds conversions."""

    def test_datetime_to_nanoseconds(self):
        """Should convert datetime to nanoseconds."""
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ns = datetime_to_nanoseconds(dt)

        assert isinstance(ns, int)
        assert ns == 1704110400000000000

    def test_nanoseconds_to_datetime(self):
        """Should convert nanoseconds to datetime."""
        ns = 1704110400000000000
        dt = nanoseconds_to_datetime(ns)

        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 1
        assert dt.hour == 12
        assert dt.tzinfo == timezone.utc

    def test_roundtrip_conversion(self):
        """Datetime -> ns -> datetime should preserve value."""
        original = datetime(2024, 6, 15, 14, 30, 45, tzinfo=timezone.utc)
        ns = datetime_to_nanoseconds(original)
        recovered = nanoseconds_to_datetime(ns)

        assert recovered.year == original.year
        assert recovered.month == original.month
        assert recovered.day == original.day
        assert recovered.hour == original.hour
        assert recovered.minute == original.minute
        assert recovered.second == original.second


class TestMillisecondConversion:
    """Test nanoseconds to milliseconds conversion."""

    def test_nanoseconds_to_milliseconds(self):
        """Should convert nanoseconds to milliseconds."""
        assert nanoseconds_to_milliseconds(1_000_000) == 1.0
        assert nanoseconds_to_milliseconds(1_500_000_000) == 1500.0
        assert nanoseconds_to_milliseconds(0) == 0.0

    def test_fractional_milliseconds(self):
        """Should handle fractional milliseconds."""
        result = nanoseconds_to_milliseconds(1_500_000)
        assert result == 1.5


class TestSampleDuration:
    """Test sample duration calculation."""

    def test_sample_duration_10hz(self):
        """10Hz = 100ms per sample."""
        ns = sample_duration_nanoseconds(10.0)
        assert ns == 100_000_000  # 100ms

    def test_sample_duration_50hz(self):
        """50Hz = 20ms per sample."""
        ns = sample_duration_nanoseconds(50.0)
        assert ns == 20_000_000  # 20ms

    def test_sample_duration_1hz(self):
        """1Hz = 1 second per sample."""
        ns = sample_duration_nanoseconds(1.0)
        assert ns == NANOSECONDS_PER_SECOND


class TestCurrentTime:
    """Test current time retrieval."""

    def test_current_time_is_reasonable(self):
        """Should return a reasonable current timestamp."""
        ns = current_time_nanoseconds()

        # Should be after 2024-01-01
        min_ns = 1704067200000000000
        assert ns > min_ns

        # Should be close to time.time()
        expected_ns = int(time.time() * NANOSECONDS_PER_SECOND)
        diff = abs(ns - expected_ns)
        assert diff < NANOSECONDS_PER_SECOND  # Within 1 second
