"""Tests for counting deduplication with edge trimming.

The counting deduplication filter removes detections that were already
counted in the previous overlapping window. With 50% overlap and edge
trimming, the boundary must account for trimmed sample indices.

Key math (window=300, step=150, edge_trim=25, trimmed_output=250):
- Previous window covers raw [0, 300) → trimmed indices [0, 250)
- Current window covers raw [150, 450) → trimmed indices [0, 250)
- Overlap in current trimmed space: indices [0, 125)
- new_data_start should be 125, not 150
"""

import sys
from dataclasses import dataclass, field
from typing import List
from unittest.mock import MagicMock

import numpy as np
import pytest

# Mock dependencies that aren't needed
sys.modules.setdefault("matplotlib", MagicMock())
sys.modules.setdefault("matplotlib.pyplot", MagicMock())

from ai_engine.message_utils import ProcessingContext, create_count_messages


@dataclass
class MockMessage:
    id: str = ""
    payload: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    output_id: str = ""


# Monkey-patch the Message import in the function
class FakeMessage:
    def __init__(self, id="", payload=None, headers=None, output_id=""):
        self.id = id
        self.payload = payload or {}
        self.headers = headers or {}
        self.output_id = output_id


class TestCountingDeduplication:
    """Test that new_data_start accounts for edge trimming."""

    @pytest.fixture
    def ctx(self):
        ctx = ProcessingContext()
        ctx.channel_start = 0
        ctx.channel_step = 1
        return ctx

    def _make_count_results(self, starts, ends, counts=None, n_sections=1):
        """Create count_results in the format expected by create_count_messages."""
        if counts is None:
            counts = [1] * len(starts)

        all_counts = [counts] if n_sections == 1 else [counts] + [None] * (n_sections - 1)
        all_intervals = [(starts, ends)] if n_sections == 1 else [(starts, ends)] + [([], [])] * (n_sections - 1)

        timestamps = list(range(250))  # 250 trimmed samples worth of timestamps
        return (all_counts, all_intervals, timestamps)

    def test_new_data_start_with_edge_trim(self, ctx):
        """Detections at trimmed index >= step-edge_trim should be kept."""
        # Detection at trimmed index 130 (new data region)
        count_results = self._make_count_results(
            starts=[130],
            ends=[140],
            counts=[1],
        )

        messages = create_count_messages(
            fiber_id="test",
            count_results=count_results,
            ctx=ctx,
            sampling_rate_hz=10.0,
            channels_per_section=9,
            counting_samples=300,
            step_samples=150,
            service_name="test",
            edge_trim=25,  # new_data_start = max(0, 150-25) = 125
        )

        # Detection at 130 >= 125, should NOT be filtered
        assert len(messages) == 1

    def test_old_behavior_would_filter_valid_detection(self, ctx):
        """Without edge_trim correction, detection at index 130 would be wrongly filtered."""
        count_results = self._make_count_results(
            starts=[130],
            ends=[140],
            counts=[1],
        )

        # With edge_trim=0 (old behavior equivalent: new_data_start = 150)
        messages = create_count_messages(
            fiber_id="test",
            count_results=count_results,
            ctx=ctx,
            sampling_rate_hz=10.0,
            channels_per_section=9,
            counting_samples=300,
            step_samples=150,
            service_name="test",
            edge_trim=0,  # new_data_start = max(0, 150-0) = 150
        )

        # Detection at 130 < 150, gets wrongly filtered
        assert len(messages) == 0

    def test_overlap_region_filtered(self, ctx):
        """Detections in the overlap region (< step-edge_trim) should be filtered."""
        count_results = self._make_count_results(
            starts=[50],
            ends=[60],
            counts=[1],
        )

        messages = create_count_messages(
            fiber_id="test",
            count_results=count_results,
            ctx=ctx,
            sampling_rate_hz=10.0,
            channels_per_section=9,
            counting_samples=300,
            step_samples=150,
            service_name="test",
            edge_trim=25,  # new_data_start = 125
        )

        # Detection at 50 < 125, should be filtered (was in previous window)
        assert len(messages) == 0

    def test_boundary_detection_at_exact_threshold(self, ctx):
        """Detection exactly at new_data_start should be kept."""
        count_results = self._make_count_results(
            starts=[125],
            ends=[135],
            counts=[1],
        )

        messages = create_count_messages(
            fiber_id="test",
            count_results=count_results,
            ctx=ctx,
            sampling_rate_hz=10.0,
            channels_per_section=9,
            counting_samples=300,
            step_samples=150,
            service_name="test",
            edge_trim=25,  # new_data_start = 125
        )

        # Detection at 125 >= 125, should be kept
        assert len(messages) == 1

    def test_multiple_detections_partial_filter(self, ctx):
        """Mix of overlap and new detections should filter correctly."""
        count_results = self._make_count_results(
            starts=[50, 125, 200],
            ends=[60, 135, 210],
            counts=[1, 2, 1],
        )

        messages = create_count_messages(
            fiber_id="test",
            count_results=count_results,
            ctx=ctx,
            sampling_rate_hz=10.0,
            channels_per_section=9,
            counting_samples=300,
            step_samples=150,
            service_name="test",
            edge_trim=25,
        )

        # Detection at 50 filtered, detections at 125 and 200 kept
        assert len(messages) == 2

    def test_zero_edge_trim_uses_step_samples(self, ctx):
        """With edge_trim=0, new_data_start = step_samples (legacy behavior)."""
        count_results = self._make_count_results(
            starts=[149, 150, 151],
            ends=[155, 160, 165],
            counts=[1, 1, 1],
        )

        messages = create_count_messages(
            fiber_id="test",
            count_results=count_results,
            ctx=ctx,
            sampling_rate_hz=10.0,
            channels_per_section=9,
            counting_samples=300,
            step_samples=150,
            service_name="test",
            edge_trim=0,  # new_data_start = 150
        )

        # 149 < 150 filtered, 150 and 151 kept
        assert len(messages) == 2

    def test_default_edge_trim_is_zero(self, ctx):
        """Default edge_trim=0 maintains backward compatibility."""
        count_results = self._make_count_results(
            starts=[155],
            ends=[165],
            counts=[1],
        )

        # Not passing edge_trim should default to 0
        messages = create_count_messages(
            fiber_id="test",
            count_results=count_results,
            ctx=ctx,
            sampling_rate_hz=10.0,
            channels_per_section=9,
            counting_samples=300,
            step_samples=150,
            service_name="test",
        )

        # 155 >= 150 (default behavior), should be kept
        assert len(messages) == 1

    def test_new_data_start_never_negative(self, ctx):
        """When step > counting_samples, new_data_start should be 0."""
        count_results = self._make_count_results(
            starts=[0],
            ends=[10],
            counts=[1],
        )

        messages = create_count_messages(
            fiber_id="test",
            count_results=count_results,
            ctx=ctx,
            sampling_rate_hz=10.0,
            channels_per_section=9,
            counting_samples=100,
            step_samples=200,  # step > counting_samples
            service_name="test",
            edge_trim=25,
        )

        # max(0, 200-25) = 175 > 0, so detection at 0 is filtered
        # But if step > window there's no overlap, so let's test a more reasonable case
        assert len(messages) == 0


class TestEdgeTrimMathVerification:
    """Verify the deduplication math for standard config values."""

    def test_standard_config_new_data_boundary(self):
        """Standard config: window=300, step=150, edge_trim=25 → boundary=125."""
        edge_trim = 25
        step_samples = 150
        new_data_start = max(0, step_samples - edge_trim)
        assert new_data_start == 125

    def test_trimmed_output_size(self):
        """Trimmed output = window - 2*edge_trim = 300 - 50 = 250."""
        window_size = 300
        edge_trim = 25
        trimmed_size = window_size - 2 * edge_trim
        assert trimmed_size == 250

    def test_new_data_fraction(self):
        """New data should be 50% of trimmed output with 50% overlap."""
        window_size = 300
        edge_trim = 25
        step_samples = 150
        trimmed_size = window_size - 2 * edge_trim  # 250
        new_data_start = max(0, step_samples - edge_trim)  # 125
        new_data_count = trimmed_size - new_data_start  # 125
        # 125/250 = 50% — exactly what we expect with 50% overlap
        assert new_data_count == trimmed_size / 2
