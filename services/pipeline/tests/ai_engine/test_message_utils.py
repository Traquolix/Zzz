"""Tests for message_utils: input validation and error handling.

Input/output round-trip and Avro conformance are tested in
test_message_roundtrip.py and test_avro_conformance.py.
This file focuses on unit-level validation: metadata extraction,
sampling rate checks, and error cases.
"""

from __future__ import annotations

import pytest

from ai_engine.message_utils import (
    ProcessingContext,
    extract_channel_metadata,
    messages_to_arrays,
    validate_sampling_rate,
)
from shared.message import Message
from tests.ai_engine.conftest import SAMPLING_RATE_HZ


def _make_message(
    values: list,
    channel_start: int = 0,
    channel_step: int = 1,
    timestamp_ns: int = 1_700_000_000_000_000_000,
    sample_count: int = 1,
    channel_count: int | None = None,
    fiber_id: str = "test",
    section: str = "default",
) -> Message:
    """Helper to create a Message with a typical payload."""
    payload = {
        "fiber_id": fiber_id,
        "section": section,
        "values": values,
        "channel_start": channel_start,
        "timestamp_ns": timestamp_ns,
        "sample_count": sample_count,
        "sampling_rate_hz": SAMPLING_RATE_HZ,
        "processing_metadata": {
            "channel_selection": {"step": channel_step},
        },
    }
    if channel_count is not None:
        payload["channel_count"] = channel_count
    return Message(id="test-msg", payload=payload)


class TestExtractChannelMetadata:
    """Tests for channel metadata extraction from payload."""

    def test_default_values(self):
        start, step = extract_channel_metadata({})
        assert start == 0
        assert step == 1

    def test_explicit_values(self):
        payload = {
            "channel_start": 100,
            "processing_metadata": {"channel_selection": {"step": 3}},
        }
        start, step = extract_channel_metadata(payload)
        assert start == 100
        assert step == 3

    def test_missing_processing_metadata(self):
        payload = {"channel_start": 50}
        start, step = extract_channel_metadata(payload)
        assert start == 50
        assert step == 1


class TestValidateSamplingRate:
    """Tests for sampling rate validation."""

    def test_matching_rate_passes(self):
        payload = {"sampling_rate_hz": SAMPLING_RATE_HZ}
        validate_sampling_rate(payload, SAMPLING_RATE_HZ)  # should not raise

    def test_mismatched_rate_raises(self):
        payload = {"sampling_rate_hz": 125.0}
        with pytest.raises(ValueError, match="expects"):
            validate_sampling_rate(payload, SAMPLING_RATE_HZ)

    def test_missing_rate_passes(self):
        validate_sampling_rate({}, SAMPLING_RATE_HZ)  # should not raise

    def test_close_rate_passes(self):
        payload = {"sampling_rate_hz": SAMPLING_RATE_HZ + 0.05}
        validate_sampling_rate(payload, SAMPLING_RATE_HZ)  # within 0.1 tolerance


class TestMessagesToArrays:
    """Tests for error cases in message-to-array conversion."""

    def test_empty_messages(self):
        """Empty message list produces empty array."""
        ctx = ProcessingContext()
        data, timestamps, timestamps_ns = messages_to_arrays([], ctx, SAMPLING_RATE_HZ)
        assert data.size == 0
        assert timestamps == []
        assert timestamps_ns == []

    def test_channel_count_mismatch_raises(self):
        """Messages with different channel counts must raise ValueError."""
        msg1 = _make_message(values=list(range(50)))
        msg2 = _make_message(values=list(range(30)))
        ctx = ProcessingContext()
        with pytest.raises(ValueError, match="Channel count mismatch"):
            messages_to_arrays([msg1, msg2], ctx, SAMPLING_RATE_HZ)
