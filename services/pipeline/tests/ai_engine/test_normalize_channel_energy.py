"""Tests for normalize_channel_energy.

Validates that per-channel energy equalization works correctly:
- DC offset removal
- Energy scaling
- Edge cases (zero channels, single channel)
"""

from __future__ import annotations

import numpy as np

from ai_engine.model_vehicle.utils import normalize_channel_energy
from tests.ai_engine.conftest import CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW


class TestNormalizeChannelEnergy:
    """Tests for per-channel energy normalization."""

    def test_dc_offset_removed(self, rng):
        """After normalization, each channel should be zero-mean."""
        data = rng.standard_normal((CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW)) + 10.0
        result = normalize_channel_energy(data)
        channel_means = np.mean(result, axis=1)
        np.testing.assert_allclose(channel_means, 0.0, atol=1e-10)

    def test_energy_equalized(self, rng):
        """After normalization, all channels should have the same energy."""
        # Create data with very different per-channel amplitudes
        data = rng.standard_normal((CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW))
        for i in range(CHANNELS_PER_SECTION):
            data[i] *= (i + 1) * 10  # channel 0: x10, channel 8: x90

        result = normalize_channel_energy(data)
        channel_energies = np.sum(result**2, axis=1)

        # All energies should be equal (to the mean)
        np.testing.assert_allclose(
            channel_energies,
            np.mean(channel_energies),
            rtol=1e-10,
        )

    def test_does_not_modify_input(self, rng):
        """normalize_channel_energy must not modify the input array."""
        data = rng.standard_normal((CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW))
        original = data.copy()
        normalize_channel_energy(data)
        np.testing.assert_array_equal(data, original)

    def test_output_shape_matches_input(self, rng):
        """Output shape must equal input shape."""
        data = rng.standard_normal((CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW))
        result = normalize_channel_energy(data)
        assert result.shape == data.shape

    def test_dtype_preserved(self, rng):
        """Output dtype must match input dtype."""
        data = rng.standard_normal((CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW))
        result = normalize_channel_energy(data)
        assert result.dtype == data.dtype

    def test_zero_energy_channel_preserved(self):
        """A channel with all zeros should remain all zeros (no division by zero)."""
        data = np.ones((3, SAMPLES_PER_WINDOW))
        data[1, :] = 0.0  # zero channel
        # DC removal makes it: channel 0 all zeros, channel 1 all -1, channel 2 all 0
        # Actually: mean is 1.0 for channels 0,2. After DC removal: all zeros.
        # Channel 1 mean is 0, after DC removal still 0. Energy=0 → should stay 0.
        data = np.array(
            [
                [5.0] * SAMPLES_PER_WINDOW,
                [0.0] * SAMPLES_PER_WINDOW,
                [3.0] * SAMPLES_PER_WINDOW,
            ]
        )
        result = normalize_channel_energy(data)
        # After DC removal, channel 1 is still all zeros
        np.testing.assert_array_equal(result[1], 0.0)

    def test_single_channel(self, rng):
        """Single channel should work without error."""
        data = rng.standard_normal((1, SAMPLES_PER_WINDOW))
        result = normalize_channel_energy(data)
        assert result.shape == (1, SAMPLES_PER_WINDOW)
        # Single channel: DC removed, energy scaled to itself → no change in scale
        np.testing.assert_allclose(np.mean(result, axis=1), 0.0, atol=1e-10)

    def test_deterministic(self, rng):
        """Same input must produce identical output."""
        data = rng.standard_normal((CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW))
        r1 = normalize_channel_energy(data)
        r2 = normalize_channel_energy(data)
        np.testing.assert_array_equal(r1, r2)

    def test_known_values(self):
        """Test with a small known-value example for manual verification."""
        # 2 channels, 4 samples
        data = np.array(
            [
                [1.0, 2.0, 3.0, 4.0],
                [10.0, 20.0, 30.0, 40.0],
            ]
        )
        result = normalize_channel_energy(data)

        # After DC removal: ch0 = [-1.5, -0.5, 0.5, 1.5], ch1 = [-15, -5, 5, 15]
        ch0_centered = np.array([-1.5, -0.5, 0.5, 1.5])
        ch1_centered = np.array([-15.0, -5.0, 5.0, 15.0])

        e0 = np.sum(ch0_centered**2)  # 5.0
        e1 = np.sum(ch1_centered**2)  # 500.0
        mean_e = (e0 + e1) / 2  # 252.5

        expected_ch0 = ch0_centered * np.sqrt(mean_e / e0)
        expected_ch1 = ch1_centered * np.sqrt(mean_e / e1)

        np.testing.assert_allclose(result[0], expected_ch0, rtol=1e-10)
        np.testing.assert_allclose(result[1], expected_ch1, rtol=1e-10)
