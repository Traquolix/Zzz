"""Tests for GLRTDetector.

Validates GLRT computation (F.conv1d sliding window) and detection extraction.
Peak counting and interval finding are tested in test_production_params.py.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from ai_engine.model_vehicle.glrt_detector import GLRTDetector
from ai_engine.model_vehicle.utils import correlation_threshold
from tests.ai_engine.conftest import (
    CHANNELS_PER_SECTION,
    CORR_THRESHOLD,
    GLRT_WINDOW,
    MAX_SPEED,
    MIN_SPEED,
    SAMPLES_PER_WINDOW,
    SAMPLING_RATE_HZ,
)


class TestApplyGLRT:
    """Tests for the GLRT sliding-window correlation."""

    @pytest.fixture
    def detector(self) -> GLRTDetector:
        return GLRTDetector(
            glrt_win=GLRT_WINDOW,
            Nch=CHANNELS_PER_SECTION,
            fs=SAMPLING_RATE_HZ,
            corr_threshold=CORR_THRESHOLD,
            min_speed=MIN_SPEED,
            max_speed=MAX_SPEED,
        )

    def test_output_shape(self, detector):
        """GLRT output must be (N, Nch-1, T) matching input dimensions."""
        n_sections, n_channels, n_time = 5, CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW
        aligned = torch.randn(n_sections, n_channels, n_time)
        result = detector.apply_glrt(aligned)
        assert result.shape == (n_sections, n_channels - 1, n_time)

    def test_edge_safety_zeros(self, detector):
        """First and last `safety` samples must be zero (edge artifact suppression)."""
        aligned = torch.randn(3, CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW)
        result = detector.apply_glrt(aligned, safety=15)
        result_np = result.numpy()

        assert np.all(result_np[:, :, :15] == 0), "Left edge should be zero"
        assert np.all(result_np[:, :, -15:] == 0), "Right edge should be zero"

    def test_positive_correlation_for_identical_channels(self, detector):
        """If adjacent channels are identical, their GLRT should be positive."""
        signal = torch.randn(1, 1, SAMPLES_PER_WINDOW)
        aligned = signal.expand(1, CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW).contiguous()

        result = detector.apply_glrt(aligned)
        interior = result.numpy()[:, :, 30:-30]
        assert np.all(interior >= 0), "Identical channels should produce non-negative GLRT"

    def test_deterministic(self, detector):
        """Same input must produce identical output."""
        aligned = torch.randn(3, CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW)
        r1 = detector.apply_glrt(aligned)
        r2 = detector.apply_glrt(aligned)
        torch.testing.assert_close(r1, r2)


class TestExtractDetections:
    """Tests for vehicle detection extraction from GLRT output."""

    @pytest.fixture
    def detector(self) -> GLRTDetector:
        return GLRTDetector(
            glrt_win=GLRT_WINDOW,
            Nch=CHANNELS_PER_SECTION,
            fs=SAMPLING_RATE_HZ,
            corr_threshold=CORR_THRESHOLD,
            min_speed=MIN_SPEED,
            max_speed=MAX_SPEED,
        )

    def test_detection_with_strong_signal(self, detector):
        """A strong coherent signal should produce at least one detection."""
        n_sections, n_pairs, trimmed_time = 1, CHANNELS_PER_SECTION - 1, 234

        glrt_summed = np.zeros((n_sections, trimmed_time))
        glrt_summed[0, 80:130] = 5000.0
        aligned_speed = np.full((n_sections, n_pairs, trimmed_time), 60.0)
        timestamps_ns = np.arange(trimmed_time, dtype=np.int64) * int(1e9 / SAMPLING_RATE_HZ)

        detections = detector.extract_detections(
            glrt_summed=glrt_summed,
            aligned_speed_pairs=aligned_speed,
            direction=0,
            timestamps_ns=timestamps_ns,
        )
        assert len(detections) >= 1, "Strong signal should produce detection"

    def test_speed_filtering(self, detector):
        """Detections with speed outside [min, max] must be rejected."""
        n_sections, n_pairs, trimmed_time = 1, 8, 234
        glrt_summed = np.zeros((n_sections, trimmed_time))
        glrt_summed[0, 80:130] = 5000.0

        aligned_speed = np.full((n_sections, n_pairs, trimmed_time), 200.0)
        timestamps_ns = np.arange(trimmed_time, dtype=np.int64) * int(1e9 / SAMPLING_RATE_HZ)

        detections = detector.extract_detections(
            glrt_summed=glrt_summed,
            aligned_speed_pairs=aligned_speed,
            direction=0,
            timestamps_ns=timestamps_ns,
        )
        assert len(detections) == 0, "Speed outside range should be rejected"

    def test_min_duration_filter(self, detector):
        """Intervals shorter than min_vehicle_duration_s must be rejected."""
        n_sections, n_pairs, trimmed_time = 1, 8, 234
        glrt_summed = np.zeros((n_sections, trimmed_time))
        glrt_summed[0, 100:102] = 5000.0
        aligned_speed = np.full((n_sections, n_pairs, trimmed_time), 60.0)
        timestamps_ns = np.arange(trimmed_time, dtype=np.int64) * int(1e9 / SAMPLING_RATE_HZ)

        detections = detector.extract_detections(
            glrt_summed=glrt_summed,
            aligned_speed_pairs=aligned_speed,
            direction=0,
            timestamps_ns=timestamps_ns,
            min_vehicle_duration_s=0.3,
        )
        assert len(detections) == 0, "Short interval should be rejected"


class TestCorrelationThreshold:
    """Tests for the binary thresholding utility."""

    def test_basic_thresholding(self):
        data = np.array([[100, 500, 1000, 200]])
        result = correlation_threshold(data, corr_threshold=500)
        expected = np.array([[0, 1, 1, 0]], dtype=np.float64)
        np.testing.assert_array_equal(result, expected)

    def test_all_below(self):
        data = np.array([[1, 2, 3]])
        result = correlation_threshold(data, corr_threshold=100)
        np.testing.assert_array_equal(result, np.zeros_like(data, dtype=np.float64))

    def test_all_above(self):
        data = np.array([[100, 200, 300]])
        result = correlation_threshold(data, corr_threshold=50)
        np.testing.assert_array_equal(result, np.ones_like(data, dtype=np.float64))
