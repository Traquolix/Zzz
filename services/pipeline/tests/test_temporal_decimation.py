"""Tests for temporal decimation processing step."""

import pytest

from processor.processing_tools.processing_steps.temporal_decimation import (
    TemporalDecimation,
)


class TestTemporalDecimation:
    """Test temporal decimation step."""

    @pytest.fixture
    def decimator(self):
        return TemporalDecimation(factor=5)

    @pytest.fixture
    def sample_measurement(self):
        return {
            "fiber_id": "test_fiber",
            "timestamp_ns": 1000000000000,
            "sampling_rate_hz": 50.0,
            "channel_start": 0,
            "values": [0.1 * i for i in range(100)],
        }

    @pytest.mark.asyncio
    async def test_decimation_outputs_every_nth_message(self, decimator, sample_measurement):
        """Should output only every Nth message where N=factor."""
        outputs = []
        for i in range(10):
            result = await decimator.process(sample_measurement.copy())
            if result is not None:
                outputs.append(result)

        # With factor=5, we should get 2 outputs for 10 messages (at message 5 and 10)
        assert len(outputs) == 2

    @pytest.mark.asyncio
    async def test_decimation_reduces_sampling_rate(self, decimator, sample_measurement):
        """Should reduce sampling rate by decimation factor."""
        # Send 5 messages to trigger first output
        for i in range(4):
            await decimator.process(sample_measurement.copy())

        result = await decimator.process(sample_measurement.copy())

        assert result is not None
        assert result["sampling_rate_hz"] == 50.0 / 5  # 10.0 Hz
        assert result["temporal_decimation_factor"] == 5

    @pytest.mark.asyncio
    async def test_decimation_preserves_other_fields(self, decimator, sample_measurement):
        """Should preserve all other message fields."""
        # Send 5 messages to trigger first output
        for i in range(4):
            await decimator.process(sample_measurement.copy())

        result = await decimator.process(sample_measurement.copy())

        assert result["fiber_id"] == "test_fiber"
        assert result["timestamp_ns"] == 1000000000000
        assert result["values"] == sample_measurement["values"]

    @pytest.mark.asyncio
    async def test_decimation_tracks_per_fiber(self):
        """Should track decimation count separately per fiber."""
        decimator = TemporalDecimation(factor=3)

        fiber_a = {"fiber_id": "fiber_a", "sampling_rate_hz": 30.0, "values": []}
        fiber_b = {"fiber_id": "fiber_b", "sampling_rate_hz": 30.0, "values": []}

        # Send alternating messages from different fibers
        results = []
        for i in range(6):
            if i % 2 == 0:
                result = await decimator.process(fiber_a.copy())
            else:
                result = await decimator.process(fiber_b.copy())
            if result:
                results.append(result["fiber_id"])

        # Each fiber should output once (at message 3 for each)
        assert results.count("fiber_a") == 1
        assert results.count("fiber_b") == 1

    @pytest.mark.asyncio
    async def test_decimation_returns_none_for_skipped(self, decimator, sample_measurement):
        """Should return None for messages that are skipped."""
        # First 4 messages should return None
        for i in range(4):
            result = await decimator.process(sample_measurement.copy())
            assert result is None

    @pytest.mark.asyncio
    async def test_decimation_handles_none_input(self, decimator):
        """Should return None for None input."""
        result = await decimator.process(None)
        assert result is None

    def test_decimation_rejects_invalid_factor(self):
        """Should reject factor < 1."""
        with pytest.raises(ValueError, match="factor must be >= 1"):
            TemporalDecimation(factor=0)

        with pytest.raises(ValueError, match="factor must be >= 1"):
            TemporalDecimation(factor=-1)

    @pytest.mark.asyncio
    async def test_decimation_requires_sampling_rate(self):
        """Should raise if message missing sampling_rate_hz."""
        decimator = TemporalDecimation(factor=1)
        message = {"fiber_id": "test", "values": []}

        with pytest.raises(ValueError, match="missing required field 'sampling_rate_hz'"):
            await decimator.process(message)


class TestTemporalDecimationFactor1:
    """Test edge case with factor=1 (no decimation)."""

    @pytest.mark.asyncio
    async def test_factor_1_outputs_every_message(self):
        """Factor=1 should output every message."""
        decimator = TemporalDecimation(factor=1)
        measurement = {"fiber_id": "test", "sampling_rate_hz": 50.0, "values": []}

        outputs = []
        for i in range(5):
            result = await decimator.process(measurement.copy())
            if result:
                outputs.append(result)

        assert len(outputs) == 5

    @pytest.mark.asyncio
    async def test_factor_1_preserves_sampling_rate(self):
        """Factor=1 should keep sampling rate unchanged."""
        decimator = TemporalDecimation(factor=1)
        measurement = {"fiber_id": "test", "sampling_rate_hz": 50.0, "values": []}

        result = await decimator.process(measurement)

        assert result["sampling_rate_hz"] == 50.0
        assert result["temporal_decimation_factor"] == 1
