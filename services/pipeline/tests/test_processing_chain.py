"""Tests for ProcessingChain and step registry."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from processor.processing_tools import (
    ProcessingChain,
    build_pipeline_from_config,
    create_step,
    get_available_steps,
    register_step,
)
from processor.processing_tools.processing_steps.base_step import ProcessingStep


class MockStep(ProcessingStep):
    """Mock processing step for testing."""

    def __init__(self, name: str = "mock", multiplier: float = 1.0):
        super().__init__(name)
        self.multiplier = multiplier

    async def process(self, data: dict) -> dict:
        values = data.get("values", [])
        data["values"] = [v * self.multiplier for v in values]
        return data


class TestProcessingChain:
    """Test ProcessingChain execution."""

    @pytest.mark.asyncio
    async def test_empty_chain(self):
        """Empty chain should return data unchanged."""
        chain = ProcessingChain([])
        data = {"values": [1, 2, 3]}
        result = await chain.process(data)
        assert result == {"values": [1, 2, 3]}

    @pytest.mark.asyncio
    async def test_single_step(self):
        """Single step should process data."""
        step = MockStep("double", multiplier=2.0)
        chain = ProcessingChain([step])

        data = {"values": [1.0, 2.0, 3.0]}
        result = await chain.process(data)

        assert result["values"] == [2.0, 4.0, 6.0]

    @pytest.mark.asyncio
    async def test_multiple_steps_execute_in_order(self):
        """Steps should execute in order, chaining results."""
        step1 = MockStep("double", multiplier=2.0)
        step2 = MockStep("triple", multiplier=3.0)
        chain = ProcessingChain([step1, step2])

        data = {"values": [1.0]}
        result = await chain.process(data)

        assert result["values"] == [6.0]  # 1 * 2 * 3

    @pytest.mark.asyncio
    async def test_stops_on_none_result(self):
        """Chain should stop if a step returns None."""
        step1 = MockStep("first")
        step2 = AsyncMock(return_value=None)
        step2.name = "null_step"
        step2.process_with_stats = AsyncMock(return_value=None)
        step3 = MockStep("third")

        chain = ProcessingChain([step1, step2, step3])
        data = {"values": [1.0]}
        result = await chain.process(data)

        assert result is None

    def test_get_chain_stats(self):
        """Should aggregate stats from all steps."""
        step1 = MockStep("step1")
        step2 = MockStep("step2")
        chain = ProcessingChain([step1, step2])

        stats = chain.get_chain_stats()

        assert "step1" in stats
        assert "step2" in stats

    def test_reset_all_stats(self):
        """Should reset stats for all steps."""
        step1 = MockStep("step1")
        step2 = MockStep("step2")
        step1._call_count = 10
        step2._call_count = 20

        chain = ProcessingChain([step1, step2])
        chain.reset_all_stats()

        assert step1._call_count == 0
        assert step2._call_count == 0


class TestStepRegistry:
    """Test step registry functions."""

    def test_get_available_steps(self):
        """Should return list of registered step names."""
        steps = get_available_steps()

        assert "bandpass_filter" in steps
        assert "temporal_decimation" in steps
        assert "spatial_decimation" in steps

    def test_create_known_step(self):
        """Should create registered step with params."""
        step = create_step(
            "temporal_decimation",
            {"factor": 10},
            fiber_sampling_rate_hz=50.0
        )

        assert step is not None
        assert step.name == "temporal_decimation"

    def test_create_unknown_step_raises(self):
        """Should raise ValueError for unknown step."""
        with pytest.raises(ValueError, match="Unknown processing step"):
            create_step("nonexistent_step", {})

    def test_create_step_with_defaults(self):
        """Should use defaults when params not provided."""
        step = create_step("temporal_decimation", {})

        assert step is not None


class TestBuildPipelineFromConfig:
    """Test pipeline building from config."""

    def test_build_empty_pipeline(self):
        """Empty config should create empty chain."""
        chain = build_pipeline_from_config([])
        assert len(chain.steps) == 0

    def test_build_single_step_pipeline(self):
        """Should build chain with one step."""
        config = [{"step": "temporal_decimation", "params": {"factor": 5}}]

        chain = build_pipeline_from_config(config)

        assert len(chain.steps) == 1
        assert chain.steps[0].name == "temporal_decimation"

    def test_build_multi_step_pipeline(self):
        """Should build chain with multiple steps in order."""
        config = [
            {"step": "bandpass_filter", "params": {"low_freq_hz": 0.1}},
            {"step": "temporal_decimation", "params": {"factor": 5}},
        ]

        chain = build_pipeline_from_config(
            config,
            fiber_sampling_rate_hz=50.0
        )

        assert len(chain.steps) == 2
        assert chain.steps[0].name == "bandpass_filter"
        assert chain.steps[1].name == "temporal_decimation"

    def test_missing_step_field_raises(self):
        """Config without 'step' field should raise."""
        config = [{"params": {"factor": 5}}]

        with pytest.raises(ValueError, match="missing 'step' field"):
            build_pipeline_from_config(config)

    def test_injects_section_channels_for_spatial_decimation(self):
        """Should inject channel bounds for spatial decimation."""
        config = [{"step": "spatial_decimation", "params": {"factor": 2}}]

        chain = build_pipeline_from_config(
            config,
            section_channels=(100, 200)
        )

        assert len(chain.steps) == 1


class TestCustomStepRegistration:
    """Test registering custom steps."""

    def test_register_custom_step(self):
        """Should be able to register and use custom steps."""
        register_step(
            name="test_custom_step",
            step_class=MockStep,
            param_map={"mult": "multiplier"},
            defaults={"multiplier": 1.0}
        )

        assert "test_custom_step" in get_available_steps()

        step = create_step("test_custom_step", {"mult": 5.0})
        assert step.multiplier == 5.0
