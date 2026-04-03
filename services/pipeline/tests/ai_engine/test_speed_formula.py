"""Tests that pin the speed computation formula to physical reality.

The speed formula is: speed = abs(3.6 * fs * gauge / delta)
where delta = (grid_t - uniform_grid) * window_size + epsilon

These tests construct grid_t with known displacements and assert the
formula produces the expected km/h value. No model involved — we are
testing the physics, not the neural network.
"""

from __future__ import annotations

import numpy as np
import pytest

from ai_engine.model_vehicle.constants import DEFAULT_EPSILON, SPEED_CONVERSION_FACTOR
from ai_engine.model_vehicle.dtan_inference import DTANInference
from tests.ai_engine.conftest import (
    CHANNELS_PER_SECTION,
    GAUGE_METERS,
    SAMPLES_PER_WINDOW,
    SAMPLING_RATE_HZ,
)


class TestSpeedFormulaPinning:
    """Pin the speed computation to exact analytical values."""

    @pytest.fixture
    def dtan(self, estimator) -> DTANInference:
        return estimator._dtan

    def test_known_displacement_produces_known_speed(self, dtan):
        """A uniform displacement of 0.01 in [0,1] domain → known speed.

        delta_samples = 0.01 * 312 = 3.12
        speed = abs(3.6 * 10.4167 * 15.3846 / 3.12) ≈ 184.93 km/h
        """
        n_windows = 1
        n_pairs = CHANNELS_PER_SECTION - 1
        displacement = 0.01  # in [0, 1] normalized domain

        grid_t = np.broadcast_to(dtan.uniform_grid, (n_windows, n_pairs, SAMPLES_PER_WINDOW)).copy()
        grid_t += displacement

        speed = dtan.comp_speed(grid_t)

        delta_samples = displacement * SAMPLES_PER_WINDOW + DEFAULT_EPSILON
        expected_speed = abs(
            SPEED_CONVERSION_FACTOR * SAMPLING_RATE_HZ * GAUGE_METERS / delta_samples
        )

        np.testing.assert_allclose(speed, expected_speed, rtol=1e-4)

    def test_larger_displacement_slower_speed(self, dtan):
        """Larger displacement (more time delay) = slower vehicle speed.

        delta_samples = 0.05 * 312 = 15.6
        speed = abs(3.6 * 10.4167 * 15.3846 / 15.6) ≈ 36.99 km/h
        """
        n_windows = 1
        n_pairs = CHANNELS_PER_SECTION - 1
        displacement = 0.05

        grid_t = np.broadcast_to(dtan.uniform_grid, (n_windows, n_pairs, SAMPLES_PER_WINDOW)).copy()
        grid_t += displacement

        speed = dtan.comp_speed(grid_t)

        delta_samples = displacement * SAMPLES_PER_WINDOW + DEFAULT_EPSILON
        expected_speed = abs(
            SPEED_CONVERSION_FACTOR * SAMPLING_RATE_HZ * GAUGE_METERS / delta_samples
        )

        np.testing.assert_allclose(speed, expected_speed, rtol=1e-4)

    def test_negative_displacement_same_magnitude(self, dtan):
        """Negative displacement (vehicle going other direction) → same speed magnitude."""
        n_windows = 1
        n_pairs = CHANNELS_PER_SECTION - 1
        displacement = 0.02

        grid_t_pos = np.broadcast_to(
            dtan.uniform_grid, (n_windows, n_pairs, SAMPLES_PER_WINDOW)
        ).copy()
        grid_t_pos += displacement

        grid_t_neg = np.broadcast_to(
            dtan.uniform_grid, (n_windows, n_pairs, SAMPLES_PER_WINDOW)
        ).copy()
        grid_t_neg -= displacement

        speed_pos = dtan.comp_speed(grid_t_pos)
        speed_neg = dtan.comp_speed(grid_t_neg)

        # comp_speed takes abs(), so both should be positive
        assert speed_pos.min() > 0
        assert speed_neg.min() > 0
        # Speeds won't be identical because epsilon shifts the denominator,
        # but they should be very close for large enough displacement
        np.testing.assert_allclose(speed_pos, speed_neg, rtol=0.02)

    def test_speed_conversion_factor_is_ms_to_kmh(self, dtan):
        """SPEED_CONVERSION_FACTOR must be 3.6 (m/s → km/h)."""
        assert SPEED_CONVERSION_FACTOR == 3.6

    def test_speed_scaling_precomputed_correctly(self, dtan):
        """DTANInference.speed_scaling = 3.6 * fs * gauge."""
        expected = SPEED_CONVERSION_FACTOR * SAMPLING_RATE_HZ * GAUGE_METERS
        assert abs(dtan.speed_scaling - expected) < 1e-6

    def test_epsilon_prevents_division_by_zero(self, dtan):
        """When grid_t == uniform_grid, delta ≈ epsilon → large but finite speed."""
        n_windows = 1
        n_pairs = CHANNELS_PER_SECTION - 1

        grid_t = np.broadcast_to(dtan.uniform_grid, (n_windows, n_pairs, SAMPLES_PER_WINDOW)).copy()
        # grid_t == uniform_grid exactly

        speed = dtan.comp_speed(grid_t)

        # Speed should be finite (epsilon prevents inf)
        assert np.all(np.isfinite(speed))
        # Speed should be very large (division by epsilon)
        assert speed.min() > 1000

    def test_per_pair_different_displacements(self, dtan):
        """Different displacement per channel pair → different speed per pair."""
        n_windows = 1
        n_pairs = CHANNELS_PER_SECTION - 1

        grid_t = np.broadcast_to(dtan.uniform_grid, (n_windows, n_pairs, SAMPLES_PER_WINDOW)).copy()

        # Pair 0: displacement 0.01 → fast, Pair 7: displacement 0.08 → slow
        for pair in range(n_pairs):
            grid_t[0, pair, :] += 0.01 * (pair + 1)

        speed = dtan.comp_speed(grid_t)

        # Pair 0 should be fastest, pair 7 slowest
        mean_speeds = [speed[0, p, :].mean() for p in range(n_pairs)]
        for i in range(n_pairs - 1):
            assert mean_speeds[i] > mean_speeds[i + 1], (
                f"Pair {i} ({mean_speeds[i]:.1f}) should be faster than "
                f"pair {i + 1} ({mean_speeds[i + 1]:.1f})"
            )

    def test_60kmh_displacement(self, dtan):
        """A vehicle at 60 km/h should produce specific displacement.

        60 km/h = 16.667 m/s
        time_between_channels = gauge / speed = 15.3846 / 16.667 = 0.923 s
        samples_delay = 0.923 * fs = 0.923 * 10.4167 = 9.614 samples
        displacement_normalized = 9.614 / 312 = 0.0308
        """
        n_windows = 1
        n_pairs = CHANNELS_PER_SECTION - 1
        target_speed_kmh = 60.0
        target_speed_ms = target_speed_kmh / 3.6
        time_delay_s = GAUGE_METERS / target_speed_ms
        samples_delay = time_delay_s * SAMPLING_RATE_HZ
        displacement = samples_delay / SAMPLES_PER_WINDOW

        grid_t = np.broadcast_to(dtan.uniform_grid, (n_windows, n_pairs, SAMPLES_PER_WINDOW)).copy()
        grid_t += displacement

        speed = dtan.comp_speed(grid_t)

        # Should be close to 60 km/h (epsilon introduces small error)
        np.testing.assert_allclose(speed.mean(), target_speed_kmh, rtol=0.01)
