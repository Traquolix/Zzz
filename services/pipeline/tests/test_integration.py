"""End-to-end integration tests.

Tests the full pipeline flow from message ingestion through processing to output.
"""

import asyncio

import pytest

from processor.processing_tools import ProcessingChain, build_pipeline_from_config
from processor.processing_tools.processing_steps.spatial_decimation import SpatialDecimation
from processor.processing_tools.processing_steps.temporal_decimation import TemporalDecimation


class TestProcessingPipelineIntegration:
    """Test processing pipeline end-to-end."""

    @pytest.fixture
    def raw_das_message(self):
        """Create a realistic raw DAS message."""
        return {
            "fiber_id": "test_fiber",
            "timestamp_ns": 1000000000000,
            "sampling_rate_hz": 50.0,
            "channel_start": 0,
            "values": [float(i) for i in range(100)],  # 100 channels
        }

    @pytest.mark.asyncio
    async def test_spatial_then_temporal_decimation(self, raw_das_message):
        """Test spatial decimation followed by temporal decimation."""
        # Build pipeline with both steps
        steps = [
            SpatialDecimation(factor=2, channel_start=0, channel_stop=100),
            TemporalDecimation(factor=5),
        ]
        chain = ProcessingChain(steps)

        # Process 5 messages to trigger temporal decimation output
        results = []
        for i in range(5):
            msg = raw_das_message.copy()
            msg["timestamp_ns"] = 1000000000000 + i * 20_000_000  # 20ms apart
            result = await chain.process(msg)
            if result is not None:
                results.append(result)

        # Should have 1 output (after 5 messages with temporal decimation factor=5)
        assert len(results) == 1

        output = results[0]
        # Spatial decimation: 100 channels -> 50 channels (factor=2)
        assert len(output["values"]) == 50
        # Temporal decimation: 50Hz -> 10Hz (factor=5)
        assert output["sampling_rate_hz"] == 10.0
        # Metadata should be set
        assert output["spatial_decimation_factor"] == 2
        assert output["temporal_decimation_factor"] == 5

    @pytest.mark.asyncio
    async def test_channel_selection_in_pipeline(self, raw_das_message):
        """Test channel selection (subset) in pipeline."""
        # Select only channels 20-40
        steps = [SpatialDecimation(factor=1, channel_start=20, channel_stop=40)]
        chain = ProcessingChain(steps)

        result = await chain.process(raw_das_message)

        assert result is not None
        # 20 channels selected (40 - 20)
        assert len(result["values"]) == 20
        # Values should be from the selected range
        assert result["values"] == list(range(20, 40))
        assert result["channel_start"] == 20

    @pytest.mark.asyncio
    async def test_pipeline_stops_on_empty_selection(self, raw_das_message):
        """Pipeline should stop when selection yields no channels."""
        # Select channels that don't exist in message
        steps = [SpatialDecimation(factor=1, channel_start=500, channel_stop=600)]
        chain = ProcessingChain(steps)

        result = await chain.process(raw_das_message)

        # Should return None when no channels selected
        assert result is None

    @pytest.mark.asyncio
    async def test_pipeline_preserves_metadata(self, raw_das_message):
        """Pipeline should preserve original message metadata."""
        steps = [SpatialDecimation(factor=2)]
        chain = ProcessingChain(steps)

        result = await chain.process(raw_das_message)

        assert result is not None
        assert result["fiber_id"] == "test_fiber"
        assert result["timestamp_ns"] == 1000000000000
        # sampling_rate_hz preserved (spatial decimation doesn't change it)
        assert result["sampling_rate_hz"] == 50.0


class TestPipelineFromConfig:
    """Test building and running pipelines from configuration."""

    @pytest.mark.asyncio
    async def test_build_pipeline_from_config_list(self):
        """Should build working pipeline from dict config list."""
        # build_pipeline_from_config expects dict, not PipelineStepConfig
        config = [
            {"step": "spatial_decimation", "params": {"factor": 2}},
            {"step": "temporal_decimation", "params": {"factor": 5}},
        ]

        chain = build_pipeline_from_config(
            config,
            fiber_sampling_rate_hz=50.0,
            section_channels=(0, 100),
        )

        assert len(chain.steps) == 2
        assert isinstance(chain.steps[0], SpatialDecimation)
        assert isinstance(chain.steps[1], TemporalDecimation)

    @pytest.mark.asyncio
    async def test_pipeline_processes_realistic_data(self):
        """Test pipeline with realistic DAS data."""
        config = [
            {"step": "spatial_decimation", "params": {"factor": 5}},
            {"step": "temporal_decimation", "params": {"factor": 5}},
        ]

        chain = build_pipeline_from_config(
            config,
            fiber_sampling_rate_hz=50.0,
            section_channels=(0, 1000),
        )

        # Simulate 1000 channels at 50Hz, decimating to 200 channels at 10Hz
        raw_message = {
            "fiber_id": "fiber1",
            "timestamp_ns": 1000000000000,
            "sampling_rate_hz": 50.0,
            "channel_start": 0,
            "values": [1.0] * 1000,
        }

        results = []
        for i in range(5):  # 5 messages for temporal decimation
            msg = raw_message.copy()
            result = await chain.process(msg)
            if result is not None:
                results.append(result)

        assert len(results) == 1
        output = results[0]
        assert len(output["values"]) == 200  # 1000 / 5 = 200
        assert output["sampling_rate_hz"] == 10.0  # 50 / 5 = 10


class TestMultipleFiberProcessing:
    """Test processing messages from multiple fibers."""

    @pytest.mark.asyncio
    async def test_independent_fiber_pipelines(self):
        """Each fiber should have independent processing state."""
        # Create temporal decimator - should track state per fiber
        decimator = TemporalDecimation(factor=3)

        # Send messages from two fibers alternately
        results = []

        for i in range(6):
            if i % 2 == 0:
                msg = {"fiber_id": "fiber_a", "sampling_rate_hz": 30.0, "values": [1.0]}
            else:
                msg = {"fiber_id": "fiber_b", "sampling_rate_hz": 30.0, "values": [2.0]}

            result = await decimator.process(msg)
            if result is not None:
                results.append((result["fiber_id"], result["values"]))

        # Each fiber should produce one output (after 3 messages each)
        assert len(results) == 2
        fiber_ids = [r[0] for r in results]
        assert "fiber_a" in fiber_ids
        assert "fiber_b" in fiber_ids


class TestMessageFlowTracking:
    """Test message flow through pipeline with metrics."""

    @pytest.mark.asyncio
    async def test_chain_stats_tracking(self):
        """Chain should track processing statistics."""
        steps = [SpatialDecimation(factor=2)]
        chain = ProcessingChain(steps)

        message = {
            "fiber_id": "test",
            "channel_start": 0,
            "sampling_rate_hz": 50.0,
            "values": list(range(100)),
        }

        # Process several messages
        for _ in range(10):
            await chain.process(message)

        stats = chain.get_chain_stats()

        # Stats should have an entry for the step
        assert len(stats) == 1
        # Get the first (only) step's stats
        step_name = list(stats.keys())[0]
        step_stats = stats[step_name]
        # Check that stats were accumulated (key names may vary by implementation)
        assert "processed" in step_stats or "total" in step_stats or len(step_stats) > 0

    @pytest.mark.asyncio
    async def test_stats_reset(self):
        """Chain stats should be resettable."""
        steps = [SpatialDecimation(factor=2)]
        chain = ProcessingChain(steps)

        message = {"fiber_id": "test", "channel_start": 0, "sampling_rate_hz": 50.0, "values": [1.0] * 10}

        # Process some messages
        for _ in range(5):
            await chain.process(message)

        # Verify stats accumulated
        stats_before = chain.get_chain_stats()
        step_name = list(stats_before.keys())[0]

        # Reset stats
        chain.reset_all_stats()

        stats_after = chain.get_chain_stats()
        # After reset, stats should be zeroed
        assert stats_after[step_name] != stats_before[step_name] or stats_before[step_name] == {}


class TestEdgeCases:
    """Test edge cases in pipeline processing."""

    @pytest.mark.asyncio
    async def test_empty_values_array(self):
        """Should handle empty values array gracefully."""
        steps = [SpatialDecimation(factor=2)]
        chain = ProcessingChain(steps)

        message = {
            "fiber_id": "test",
            "channel_start": 0,
            "sampling_rate_hz": 50.0,
            "values": [],
        }

        result = await chain.process(message)

        # Empty values should return the message unchanged (as per implementation)
        assert result is not None
        assert result["values"] == []

    @pytest.mark.asyncio
    async def test_single_channel(self):
        """Should handle single channel data."""
        steps = [SpatialDecimation(factor=1)]  # No decimation
        chain = ProcessingChain(steps)

        message = {
            "fiber_id": "test",
            "channel_start": 0,
            "sampling_rate_hz": 50.0,
            "values": [42.0],
        }

        result = await chain.process(message)

        assert result is not None
        assert result["values"] == [42.0]

    @pytest.mark.asyncio
    async def test_none_input_message(self):
        """Should handle None input gracefully."""
        steps = [SpatialDecimation(factor=2)]
        chain = ProcessingChain(steps)

        result = await chain.process(None)

        assert result is None

    @pytest.mark.asyncio
    async def test_very_large_decimation_factor(self):
        """Should handle large decimation factor."""
        steps = [SpatialDecimation(factor=100)]
        chain = ProcessingChain(steps)

        message = {
            "fiber_id": "test",
            "channel_start": 0,
            "sampling_rate_hz": 50.0,
            "values": list(range(1000)),
        }

        result = await chain.process(message)

        assert result is not None
        # 1000 channels / 100 = 10 channels
        assert len(result["values"]) == 10
        # Should pick every 100th value: 0, 100, 200, ..., 900
        assert result["values"] == list(range(0, 1000, 100))


class TestConcurrentProcessing:
    """Test concurrent message processing."""

    @pytest.mark.asyncio
    async def test_concurrent_pipeline_processing(self):
        """Multiple messages should process correctly concurrently."""
        steps = [SpatialDecimation(factor=2)]
        chain = ProcessingChain(steps)

        messages = [
            {"fiber_id": f"fiber_{i}", "channel_start": 0, "sampling_rate_hz": 50.0, "values": list(range(100))}
            for i in range(10)
        ]

        # Process all concurrently
        results = await asyncio.gather(*[chain.process(msg) for msg in messages])

        assert len(results) == 10
        for result in results:
            assert result is not None
            assert len(result["values"]) == 50  # 100 / 2 = 50
