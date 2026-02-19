"""Tests for spatial decimation processing step."""

import pytest

from processor.processing_tools.processing_steps.spatial_decimation import (
    SpatialDecimation,
)


class TestSpatialDecimation:
    """Test spatial decimation step."""

    @pytest.fixture
    def sample_measurement(self):
        return {
            "fiber_id": "test_fiber",
            "timestamp_ns": 1000000000000,
            "sampling_rate_hz": 50.0,
            "channel_start": 0,
            "values": list(range(100)),  # [0, 1, 2, ..., 99]
        }

    @pytest.mark.asyncio
    async def test_decimation_factor_2(self, sample_measurement):
        """Factor=2 should keep every other channel."""
        decimator = SpatialDecimation(factor=2)

        result = await decimator.process(sample_measurement)

        assert result is not None
        assert len(result["values"]) == 50
        assert result["values"] == list(range(0, 100, 2))  # [0, 2, 4, ..., 98]
        assert result["spatial_decimation_factor"] == 2

    @pytest.mark.asyncio
    async def test_decimation_factor_5(self, sample_measurement):
        """Factor=5 should keep every 5th channel."""
        decimator = SpatialDecimation(factor=5)

        result = await decimator.process(sample_measurement)

        assert result is not None
        assert len(result["values"]) == 20
        assert result["values"] == list(range(0, 100, 5))  # [0, 5, 10, ..., 95]

    @pytest.mark.asyncio
    async def test_channel_selection_with_start_stop(self, sample_measurement):
        """Should select only channels within start/stop range."""
        decimator = SpatialDecimation(factor=1, channel_start=20, channel_stop=30)

        result = await decimator.process(sample_measurement)

        assert result is not None
        assert len(result["values"]) == 10
        assert result["values"] == list(range(20, 30))
        assert result["channel_start"] == 20

    @pytest.mark.asyncio
    async def test_channel_selection_with_decimation(self, sample_measurement):
        """Should apply both channel selection and decimation."""
        decimator = SpatialDecimation(factor=2, channel_start=10, channel_stop=20)

        result = await decimator.process(sample_measurement)

        assert result is not None
        assert len(result["values"]) == 5
        assert result["values"] == [10, 12, 14, 16, 18]
        assert result["channel_start"] == 10

    @pytest.mark.asyncio
    async def test_preserves_other_fields(self, sample_measurement):
        """Should preserve all other message fields."""
        decimator = SpatialDecimation(factor=2)

        result = await decimator.process(sample_measurement)

        assert result["fiber_id"] == "test_fiber"
        assert result["timestamp_ns"] == 1000000000000
        assert result["sampling_rate_hz"] == 50.0

    @pytest.mark.asyncio
    async def test_handles_none_input(self):
        """Should return None for None input."""
        decimator = SpatialDecimation(factor=2)

        result = await decimator.process(None)

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_empty_values(self, sample_measurement):
        """Should return measurement unchanged if values empty."""
        decimator = SpatialDecimation(factor=2)
        sample_measurement["values"] = []

        result = await decimator.process(sample_measurement)

        assert result == sample_measurement

    @pytest.mark.asyncio
    async def test_returns_none_if_no_channels_selected(self, sample_measurement):
        """Should return None if channel range results in no selection."""
        # Channels 200-300 don't exist in 100-channel message
        decimator = SpatialDecimation(factor=1, channel_start=200, channel_stop=300)

        result = await decimator.process(sample_measurement)

        assert result is None

    def test_rejects_invalid_factor(self):
        """Should reject factor < 1."""
        with pytest.raises(ValueError, match="factor must be >= 1"):
            SpatialDecimation(factor=0)

        with pytest.raises(ValueError, match="factor must be >= 1"):
            SpatialDecimation(factor=-1)


class TestSpatialDecimationWithOffset:
    """Test spatial decimation with non-zero channel_start in message."""

    @pytest.fixture
    def offset_measurement(self):
        return {
            "fiber_id": "test_fiber",
            "timestamp_ns": 1000000000000,
            "sampling_rate_hz": 50.0,
            "channel_start": 100,  # Message starts at channel 100
            "values": list(range(50)),  # [0, 1, 2, ..., 49] representing channels 100-149
        }

    @pytest.mark.asyncio
    async def test_respects_message_channel_start(self, offset_measurement):
        """Should calculate indices relative to message's channel_start."""
        # Select channels 120-130 (which are indices 20-30 in the values array)
        decimator = SpatialDecimation(factor=1, channel_start=120, channel_stop=130)

        result = await decimator.process(offset_measurement)

        assert result is not None
        assert len(result["values"]) == 10
        assert result["values"] == list(range(20, 30))  # Original values at those positions
        assert result["channel_start"] == 120

    @pytest.mark.asyncio
    async def test_handles_partial_overlap(self, offset_measurement):
        """Should handle when selection only partially overlaps message."""
        # Select channels 90-110, but message starts at 100
        decimator = SpatialDecimation(factor=1, channel_start=90, channel_stop=110)

        result = await decimator.process(offset_measurement)

        assert result is not None
        assert len(result["values"]) == 10  # Channels 100-109
        assert result["values"] == list(range(10))
        assert result["channel_start"] == 100

    @pytest.mark.asyncio
    async def test_no_overlap_returns_none(self, offset_measurement):
        """Should return None when selection doesn't overlap message."""
        # Select channels 0-50, but message is 100-149
        decimator = SpatialDecimation(factor=1, channel_start=0, channel_stop=50)

        result = await decimator.process(offset_measurement)

        assert result is None


class TestSpatialDecimationFactor1:
    """Test edge case with factor=1 (no decimation, just selection)."""

    @pytest.mark.asyncio
    async def test_factor_1_returns_all_channels(self):
        """Factor=1 with no range should return all channels."""
        decimator = SpatialDecimation(factor=1)
        measurement = {
            "fiber_id": "test",
            "channel_start": 0,
            "values": list(range(10)),
        }

        result = await decimator.process(measurement)

        assert result["values"] == list(range(10))
        assert result["spatial_decimation_factor"] == 1

    @pytest.mark.asyncio
    async def test_factor_1_with_range_selects_subset(self):
        """Factor=1 with range should select subset without decimation."""
        decimator = SpatialDecimation(factor=1, channel_start=2, channel_stop=7)
        measurement = {
            "fiber_id": "test",
            "channel_start": 0,
            "values": list(range(10)),
        }

        result = await decimator.process(measurement)

        assert result["values"] == [2, 3, 4, 5, 6]
