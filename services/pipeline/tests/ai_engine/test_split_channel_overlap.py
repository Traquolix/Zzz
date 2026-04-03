"""Tests for DTANInference.split_channel_overlap.

Validates spatial windowing: correct number of windows, shapes, boundary
handling, and that windows contain the expected data slices.
"""

from __future__ import annotations

import numpy as np
import pytest

from ai_engine.model_vehicle.dtan_inference import DTANInference
from tests.ai_engine.conftest import CHANNELS_PER_SECTION, OVERLAP_SPACE, SAMPLES_PER_WINDOW


class TestSplitChannelOverlap:
    """Tests for the spatial window splitting function."""

    @pytest.fixture
    def dtan(self, estimator) -> DTANInference:
        return estimator._dtan

    def test_output_shape(self, dtan, synthetic_section_data):
        """Each window must be (Nch, time_samples)."""
        result = dtan.split_channel_overlap(synthetic_section_data)
        assert result.ndim == 3
        assert result.shape[1] == CHANNELS_PER_SECTION
        assert result.shape[2] == SAMPLES_PER_WINDOW

    def test_window_count_step1(self, dtan, synthetic_section_data):
        """With step=1 (Nch=9, overlap=8), n_windows = channels - Nch + 1."""
        n_channels = synthetic_section_data.shape[0]
        result = dtan.split_channel_overlap(synthetic_section_data)
        step = CHANNELS_PER_SECTION - OVERLAP_SPACE  # 1
        expected_windows = (n_channels - CHANNELS_PER_SECTION) // step + 1
        assert result.shape[0] == expected_windows

    def test_window_count_50ch(self, dtan, synthetic_section_data):
        """50 channels, Nch=9, step=1 → 42 windows."""
        result = dtan.split_channel_overlap(synthetic_section_data)
        assert result.shape[0] == 42

    def test_window_count_100ch(self, dtan, synthetic_wide_data):
        """100 channels, Nch=9, step=1 → 92 windows."""
        result = dtan.split_channel_overlap(synthetic_wide_data)
        assert result.shape[0] == 92

    def test_first_window_is_first_channels(self, dtan, synthetic_section_data):
        """First window must be channels [0:Nch]."""
        result = dtan.split_channel_overlap(synthetic_section_data)
        np.testing.assert_array_equal(result[0], synthetic_section_data[:CHANNELS_PER_SECTION, :])

    def test_second_window_offset_by_step(self, dtan, synthetic_section_data):
        """Second window starts at channel `step` (=1 for overlap=Nch-1)."""
        result = dtan.split_channel_overlap(synthetic_section_data)
        step = CHANNELS_PER_SECTION - OVERLAP_SPACE
        np.testing.assert_array_equal(
            result[1], synthetic_section_data[step : step + CHANNELS_PER_SECTION, :]
        )

    def test_last_window_boundary(self, dtan, synthetic_section_data):
        """Last window must end within the channel range, no out-of-bounds."""
        result = dtan.split_channel_overlap(synthetic_section_data)
        n_channels = synthetic_section_data.shape[0]
        step = CHANNELS_PER_SECTION - OVERLAP_SPACE
        last_start = (result.shape[0] - 1) * step
        assert last_start + CHANNELS_PER_SECTION <= n_channels

    def test_adjacent_windows_overlap(self, dtan, synthetic_section_data):
        """Adjacent windows must share (Nch - step) channels."""
        result = dtan.split_channel_overlap(synthetic_section_data)
        step = CHANNELS_PER_SECTION - OVERLAP_SPACE
        overlap = CHANNELS_PER_SECTION - step
        # Window 0 channels [step:Nch] == Window 1 channels [0:overlap]
        np.testing.assert_array_equal(result[0, step:, :], result[1, :overlap, :])

    def test_dtype_preserved(self, dtan, synthetic_section_data):
        """Output dtype must match input dtype."""
        result = dtan.split_channel_overlap(synthetic_section_data)
        assert result.dtype == synthetic_section_data.dtype

    def test_minimum_channels(self, dtan):
        """With exactly Nch channels, should produce exactly 1 window."""
        data = np.random.default_rng(0).standard_normal((CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW))
        result = dtan.split_channel_overlap(data)
        assert result.shape[0] == 1

    def test_fewer_than_nch_channels(self, dtan):
        """With fewer than Nch channels, should produce 0 windows."""
        data = np.random.default_rng(0).standard_normal(
            (CHANNELS_PER_SECTION - 1, SAMPLES_PER_WINDOW)
        )
        result = dtan.split_channel_overlap(data)
        assert result.shape[0] == 0

    def test_deterministic(self, dtan, synthetic_section_data):
        """Same input must produce identical output."""
        r1 = dtan.split_channel_overlap(synthetic_section_data)
        r2 = dtan.split_channel_overlap(synthetic_section_data)
        np.testing.assert_array_equal(r1, r2)
