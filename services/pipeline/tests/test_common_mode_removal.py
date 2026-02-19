"""Unit tests for CommonModeRemoval processing step."""

import pytest

from processor.processing_tools.processing_steps.common_mode_removal import (
    CommonModeRemoval,
)


class TestCommonModeRemoval:
    """Test suite for CommonModeRemoval step."""

    @pytest.fixture
    def sample_measurement(self):
        """Create a sample measurement for testing."""
        return {
            "fiber_id": "test_fiber",
            "timestamp_ns": 1000000000000,
            "sampling_rate_hz": 50.0,
            "channel_start": 0,
            "values": [10.0, 12.0, 11.0, 13.0, 15.0, 14.0, 16.0, 18.0, 17.0, 19.0],
        }

    @pytest.mark.asyncio
    async def test_warmup_returns_none(self, sample_measurement):
        """Test that messages during warmup period return None."""
        step = CommonModeRemoval(warmup_seconds=0.1, method="median")

        # With 50 Hz sampling rate, 0.1s warmup = 5 samples
        # First 5 messages should return None
        for i in range(5):
            result = await step.process(sample_measurement)
            assert result is None, f"Sample {i} should return None during warmup"

        # 6th message should return data
        result = await step.process(sample_measurement)
        assert result is not None, "Sample after warmup should return data"

    @pytest.mark.asyncio
    async def test_applies_median_removal(self, sample_measurement):
        """Test that median common mode is removed correctly."""
        step = CommonModeRemoval(warmup_seconds=0.0, method="median")

        result = await step.process(sample_measurement)

        assert result is not None
        assert "values" in result

        # Original median: median([10, 12, 11, 13, 15, 14, 16, 18, 17, 19]) = 14.5
        # Corrected values should be original - 14.5
        expected = [
            v - 14.5 for v in sample_measurement["values"]
        ]  # [-4.5, -2.5, -3.5, -1.5, 0.5, -0.5, 1.5, 3.5, 2.5, 4.5]

        assert len(result["values"]) == len(expected)
        for actual, exp in zip(result["values"], expected):
            assert abs(actual - exp) < 1e-10, f"Expected {exp}, got {actual}"

    @pytest.mark.asyncio
    async def test_applies_mean_removal(self, sample_measurement):
        """Test that mean common mode is removed correctly."""
        step = CommonModeRemoval(warmup_seconds=0.0, method="mean")

        result = await step.process(sample_measurement)

        assert result is not None
        assert "values" in result

        # Original mean: mean([10, 12, 11, 13, 15, 14, 16, 18, 17, 19]) = 14.5
        # Corrected values should be original - 14.5
        expected = [v - 14.5 for v in sample_measurement["values"]]

        assert len(result["values"]) == len(expected)
        for actual, exp in zip(result["values"], expected):
            assert abs(actual - exp) < 1e-10, f"Expected {exp}, got {actual}"

    @pytest.mark.asyncio
    async def test_per_fiber_state(self):
        """Test that different fibers maintain independent state."""
        step = CommonModeRemoval(warmup_seconds=0.1, method="median")

        fiber1_data = {
            "fiber_id": "fiber1",
            "timestamp_ns": 1000000000000,
            "sampling_rate_hz": 50.0,
            "values": [10.0, 20.0, 30.0],
        }

        fiber2_data = {
            "fiber_id": "fiber2",
            "timestamp_ns": 1000000000000,
            "sampling_rate_hz": 50.0,
            "values": [100.0, 200.0, 300.0],
        }

        # Process fiber1 through warmup
        for _ in range(5):
            result = await step.process(fiber1_data)
            assert result is None

        # fiber2 should still be in warmup
        result = await step.process(fiber2_data)
        assert result is None

        # fiber1 should be out of warmup
        result = await step.process(fiber1_data)
        assert result is not None

        # fiber2 still in warmup (only 1 sample so far)
        for _ in range(4):
            result = await step.process(fiber2_data)
            assert result is None

        # fiber2 now out of warmup
        result = await step.process(fiber2_data)
        assert result is not None

    @pytest.mark.asyncio
    async def test_empty_values(self):
        """Test handling of empty values array."""
        step = CommonModeRemoval(warmup_seconds=0.0, method="median")

        measurement = {
            "fiber_id": "test",
            "timestamp_ns": 1000000000000,
            "sampling_rate_hz": 50.0,
            "values": [],
        }

        result = await step.process(measurement)

        assert result is not None
        assert result == measurement  # Should pass through unchanged

    @pytest.mark.asyncio
    async def test_none_input(self):
        """Test handling of None input."""
        step = CommonModeRemoval(warmup_seconds=0.0, method="median")

        result = await step.process(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_preserves_other_fields(self, sample_measurement):
        """Test that non-values fields are preserved."""
        step = CommonModeRemoval(warmup_seconds=0.0, method="median")

        result = await step.process(sample_measurement)

        assert result is not None
        assert result["fiber_id"] == "test_fiber"
        assert result["timestamp_ns"] == 1000000000000
        assert result["sampling_rate_hz"] == 50.0
        assert result["channel_start"] == 0

    @pytest.mark.asyncio
    async def test_warmup_adjusts_to_sampling_rate(self):
        """Test that warmup period adjusts based on sampling rate."""
        step = CommonModeRemoval(warmup_seconds=1.0, method="median")

        # 100 Hz sampling rate -> 100 samples warmup
        high_rate_data = {
            "fiber_id": "high_rate",
            "sampling_rate_hz": 100.0,
            "values": [1.0, 2.0, 3.0],
        }

        # Should need 100 samples to clear warmup
        for i in range(100):
            result = await step.process(high_rate_data)
            assert result is None, f"Sample {i} should be in warmup"

        result = await step.process(high_rate_data)
        assert result is not None, "Sample 101 should be out of warmup"

        # 10 Hz sampling rate -> 10 samples warmup
        low_rate_data = {
            "fiber_id": "low_rate",
            "sampling_rate_hz": 10.0,
            "values": [1.0, 2.0, 3.0],
        }

        # Should need only 10 samples to clear warmup
        for i in range(10):
            result = await step.process(low_rate_data)
            assert result is None, f"Sample {i} should be in warmup"

        result = await step.process(low_rate_data)
        assert result is not None, "Sample 11 should be out of warmup"

    def test_invalid_method_raises_error(self):
        """Test that invalid method raises ValueError."""
        with pytest.raises(ValueError, match="Invalid method"):
            CommonModeRemoval(method="invalid")

    def test_estimate_memory_usage(self):
        """Test memory estimation."""
        step = CommonModeRemoval()

        # Should return reasonable estimate
        memory_mb = step.estimate_memory_usage(num_channels=1000, buffer_size=100)
        assert memory_mb > 0
        assert memory_mb < 10  # Should be small for typical usage
