"""Tests for energy normalization (Phase 2.2)."""

import sys
from unittest.mock import MagicMock

import numpy as np

# Mock heavy dependencies that utils.py doesn't need but __init__.py imports
sys.modules.setdefault("torch", MagicMock())
sys.modules.setdefault("matplotlib", MagicMock())
sys.modules.setdefault("matplotlib.pyplot", MagicMock())

from ai_engine.model_vehicle.utils import normalize_channel_energy  # noqa: E402


class TestNormalizeChannelEnergy:
    """Test per-channel energy equalization."""

    def test_equalizes_channel_energy(self):
        """Channels with different energy should be equalized."""
        rng = np.random.default_rng(42)
        data = rng.standard_normal((50, 300))
        # Make some channels 10x louder
        data[0:10] *= 10.0

        result = normalize_channel_energy(data)

        channel_energy = np.sum(np.square(result), axis=1)
        # Energy std should be near zero after normalization
        assert np.std(channel_energy) / np.mean(channel_energy) < 0.01

    def test_preserves_shape(self):
        """Output shape should match input."""
        data = np.random.default_rng(42).standard_normal((50, 300))
        result = normalize_channel_energy(data)
        assert result.shape == (50, 300)

    def test_centers_channels(self):
        """Output mean per channel should be approximately 0."""
        data = np.random.default_rng(42).standard_normal((50, 300)) + 5.0
        result = normalize_channel_energy(data)
        channel_means = np.mean(result, axis=1)
        assert np.allclose(channel_means, 0, atol=1e-10)

    def test_handles_zero_energy_channel(self):
        """Channel of all zeros should not cause division error."""
        data = np.random.default_rng(42).standard_normal((5, 100))
        data[2, :] = 0.0  # Zero-energy channel
        result = normalize_channel_energy(data)
        # Should not raise; zero channel stays zero
        assert np.allclose(result[2, :], 0.0)

    def test_single_channel(self):
        """Single channel should return centered data."""
        data = np.array([[1.0, 2.0, 3.0, 4.0, 5.0]])
        result = normalize_channel_energy(data)
        assert result.shape == (1, 5)
        assert np.abs(np.mean(result)) < 1e-10

    def test_identical_channels_unchanged(self):
        """Channels with equal energy should have same output energy."""
        rng = np.random.default_rng(42)
        data = rng.standard_normal((10, 200))
        # Make all channels have exactly the same energy by normalizing
        for i in range(10):
            data[i] -= np.mean(data[i])
            data[i] /= np.sqrt(np.sum(data[i] ** 2))

        result = normalize_channel_energy(data)
        energies = np.sum(np.square(result), axis=1)
        assert np.std(energies) / np.mean(energies) < 0.01

    def test_does_not_modify_input(self):
        """Should not modify input array."""
        data = np.random.default_rng(42).standard_normal((5, 50))
        data_copy = data.copy()
        normalize_channel_energy(data)
        np.testing.assert_array_equal(data, data_copy)
