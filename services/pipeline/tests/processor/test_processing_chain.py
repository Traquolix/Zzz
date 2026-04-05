"""Tests for ProcessingChain orchestration.

Validates step execution order, None propagation, metrics recording,
and the full production pipeline configuration.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from processor.processing_tools.processing_chain import ProcessingChain
from processor.processing_tools.processing_steps.bandpass_filter import BandpassFilter
from processor.processing_tools.processing_steps.base_step import ProcessingStep
from processor.processing_tools.processing_steps.scale import Scale
from processor.processing_tools.processing_steps.spatial_decimation import SpatialDecimation
from processor.processing_tools.step_registry import build_pipeline_from_config, create_step

from .conftest import (
    ORIGINAL_SAMPLING_RATE_HZ,
    SECTION_CHANNEL_START,
    SECTION_CHANNEL_STOP,
    SECTION_DECIMATED_CHANNELS,
    make_measurement,
)


# ---------------------------------------------------------------------------
# Spy step for verifying call order
# ---------------------------------------------------------------------------
class SpyStep(ProcessingStep):
    """Records calls for inspection."""

    def __init__(self, name: str, call_log: list):
        super().__init__(name)
        self._call_log = call_log

    async def process(self, measurement_data: dict[str, Any]) -> dict[str, Any] | None:
        self._call_log.append(
            {
                "name": self.name,
                "shape": measurement_data["values"].shape
                if isinstance(measurement_data.get("values"), np.ndarray)
                else None,
            }
        )
        return measurement_data


class DroppingStep(ProcessingStep):
    """Always returns None (simulates warmup or empty output)."""

    def __init__(self, name: str = "dropper"):
        super().__init__(name)

    async def process(self, measurement_data: dict[str, Any]) -> dict[str, Any] | None:
        return None


# ---------------------------------------------------------------------------
# ProcessingChain tests
# ---------------------------------------------------------------------------
class TestChainExecution:
    """Step execution order and data flow."""

    async def test_steps_execute_in_order(self):
        log = []
        steps = [SpyStep("first", log), SpyStep("second", log), SpyStep("third", log)]
        chain = ProcessingChain(steps)

        m = make_measurement(np.ones((10, 5)))
        await chain.process(m)

        assert [entry["name"] for entry in log] == ["first", "second", "third"]

    async def test_none_propagation_stops_chain(self):
        log = []
        steps = [SpyStep("before", log), DroppingStep(), SpyStep("after", log)]
        chain = ProcessingChain(steps)

        m = make_measurement(np.ones((10, 5)))
        result = await chain.process(m)

        assert result is None
        assert len(log) == 1  # "after" never called
        assert log[0]["name"] == "before"

    async def test_empty_chain(self):
        chain = ProcessingChain([])
        m = make_measurement(np.ones((5, 3)))
        result = await chain.process(m)

        assert result is not None
        np.testing.assert_array_equal(result["values"], np.ones((5, 3)))

    async def test_single_step_chain(self):
        chain = ProcessingChain([Scale(factor=2.0)])
        m = make_measurement(np.array([[1.0, 2.0]]))
        result = await chain.process(m)

        np.testing.assert_array_equal(result["values"], [[2.0, 4.0]])


class TestChainMetrics:
    """Metrics recording integration."""

    async def test_metrics_recorded_per_step(self):
        mock_metrics = MagicMock()
        steps = [Scale(factor=1.0), Scale(factor=1.0)]
        chain = ProcessingChain(steps, processor_metrics=mock_metrics)

        m = make_measurement(np.ones((5, 3)))
        await chain.process(m, fiber_id="carros", section="202Bis")

        assert mock_metrics.record_step.call_count == 2
        calls = mock_metrics.record_step.call_args_list

        assert calls[0].args[0] == "scale"  # step_name
        assert calls[0].args[2] == "carros"  # fiber_id
        assert calls[0].args[3] == "202Bis"  # section
        assert calls[0].args[1] > 0  # duration > 0

    async def test_metrics_not_recorded_when_none(self):
        steps = [Scale(factor=1.0)]
        chain = ProcessingChain(steps, processor_metrics=None)

        m = make_measurement(np.ones((5, 3)))
        result = await chain.process(m)

        assert result is not None  # no crash

    async def test_metrics_stop_on_none_propagation(self):
        mock_metrics = MagicMock()
        steps = [Scale(factor=1.0), DroppingStep(), Scale(factor=1.0)]
        chain = ProcessingChain(steps, processor_metrics=mock_metrics)

        m = make_measurement(np.ones((5, 3)))
        await chain.process(m, fiber_id="f", section="s")

        # Only first two steps recorded (scale + dropper), third never reached
        assert mock_metrics.record_step.call_count == 2


class TestChainStats:
    """Stats collection."""

    async def test_chain_stats_contains_all_steps(self):
        steps = [Scale(factor=1.0), Scale(factor=2.0)]
        chain = ProcessingChain(steps)

        stats = chain.get_chain_stats()
        assert "scale" in stats
        assert stats["scale"]["call_count"] == 0

    async def test_reset_all_stats(self):
        steps = [Scale(factor=1.0)]
        chain = ProcessingChain(steps)
        m = make_measurement(np.ones((5, 3)))
        await steps[0].process_with_stats(m)

        assert steps[0].get_stats()["call_count"] == 1
        chain.reset_all_stats()
        assert steps[0].get_stats()["call_count"] == 0


# ---------------------------------------------------------------------------
# Step registry
# ---------------------------------------------------------------------------
class TestStepRegistry:
    """Tests for create_step and build_pipeline_from_config."""

    def test_all_registered_steps_instantiate(self):
        step_names = [
            "scale",
            "common_mode_removal",
            "bandpass_filter",
            "temporal_decimation",
            "spatial_decimation",
        ]
        for name in step_names:
            step = create_step(name, {}, fiber_sampling_rate_hz=125.0)
            assert step.name == name

    def test_unknown_step_raises(self):
        with pytest.raises(ValueError, match="Unknown processing step"):
            create_step("nonexistent_step", {})

    def test_bandpass_gets_sampling_rate_injected(self):
        step = create_step(
            "bandpass_filter",
            {"low_freq_hz": 0.3, "high_freq_hz": 2.0},
            fiber_sampling_rate_hz=125.0,
        )
        assert isinstance(step, BandpassFilter)

    def test_build_pipeline_reorders_spatial_first(self):
        config = [
            {"step": "scale", "params": {"factor": 213.05}},
            {"step": "common_mode_removal", "params": {"warmup_seconds": 0.0}},
            {"step": "bandpass_filter", "params": {"low_freq_hz": 0.3, "high_freq_hz": 2.0}},
            {"step": "temporal_decimation", "params": {"factor": 12}},
            {"step": "spatial_decimation", "params": {"factor": 3}},
        ]
        chain = build_pipeline_from_config(
            config,
            fiber_sampling_rate_hz=125.0,
            section_channels=(1200, 2748),
        )

        step_names = [s.name for s in chain.steps]
        assert step_names[0] == "spatial_decimation"
        assert "scale" in step_names
        assert "temporal_decimation" in step_names

    def test_build_pipeline_injects_section_channels(self):
        config = [
            {"step": "spatial_decimation", "params": {"factor": 3}},
        ]
        chain = build_pipeline_from_config(
            config,
            fiber_sampling_rate_hz=125.0,
            section_channels=(1200, 2748),
        )

        spatial = chain.steps[0]
        assert isinstance(spatial, SpatialDecimation)
        assert spatial.channel_start == 1200
        assert spatial.channel_stop == 2748

    def test_missing_step_field_raises(self):
        config = [{"params": {"factor": 3}}]
        with pytest.raises(ValueError, match="missing 'step' field"):
            build_pipeline_from_config(config)


# ---------------------------------------------------------------------------
# Full production pipeline integration
# ---------------------------------------------------------------------------
class TestProductionPipeline:
    """End-to-end test with production config values."""

    async def test_full_pipeline_produces_correct_shape(self, raw_batch, timestamps_ns):
        config = [
            {"step": "scale", "params": {"factor": 213.05}},
            {"step": "common_mode_removal", "params": {"warmup_seconds": 0.0, "method": "median"}},
            {"step": "bandpass_filter", "params": {"low_freq_hz": 0.3, "high_freq_hz": 2.0}},
            {"step": "temporal_decimation", "params": {"factor": 12}},
            {"step": "spatial_decimation", "params": {"factor": 3}},
        ]
        chain = build_pipeline_from_config(
            config,
            fiber_sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
            section_channels=(SECTION_CHANNEL_START, SECTION_CHANNEL_STOP),
        )

        m = make_measurement(
            raw_batch,
            sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
            timestamps_ns=timestamps_ns,
        )
        result = await chain.process(m, fiber_id="carros", section="202Bis")

        assert result is not None
        # After spatial decimation: 516 channels
        assert result["values"].shape[1] == SECTION_DECIMATED_CHANNELS
        # After temporal decimation (factor 12 from 24 samples): 2 samples
        assert result["values"].shape[0] == 2
        assert result["sampling_rate_hz"] == pytest.approx(ORIGINAL_SAMPLING_RATE_HZ / 12)

    async def test_pipeline_output_dtype(self, raw_batch, timestamps_ns):
        config = [
            {"step": "scale", "params": {"factor": 213.05}},
            {"step": "common_mode_removal", "params": {"warmup_seconds": 0.0}},
            {"step": "bandpass_filter", "params": {"low_freq_hz": 0.3, "high_freq_hz": 2.0}},
            {"step": "temporal_decimation", "params": {"factor": 12}},
            {"step": "spatial_decimation", "params": {"factor": 3}},
        ]
        chain = build_pipeline_from_config(
            config,
            fiber_sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
            section_channels=(SECTION_CHANNEL_START, SECTION_CHANNEL_STOP),
        )
        m = make_measurement(
            raw_batch, sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ, timestamps_ns=timestamps_ns
        )
        result = await chain.process(m)

        assert result["values"].dtype == np.float64

    async def test_pipeline_output_all_finite(self, raw_batch, timestamps_ns):
        config = [
            {"step": "scale", "params": {"factor": 213.05}},
            {"step": "common_mode_removal", "params": {"warmup_seconds": 0.0}},
            {"step": "bandpass_filter", "params": {"low_freq_hz": 0.3, "high_freq_hz": 2.0}},
            {"step": "temporal_decimation", "params": {"factor": 12}},
            {"step": "spatial_decimation", "params": {"factor": 3}},
        ]
        chain = build_pipeline_from_config(
            config,
            fiber_sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
            section_channels=(SECTION_CHANNEL_START, SECTION_CHANNEL_STOP),
        )
        m = make_measurement(
            raw_batch, sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ, timestamps_ns=timestamps_ns
        )
        result = await chain.process(m)

        assert np.all(np.isfinite(result["values"]))

    async def test_pipeline_determinism(self, timestamps_ns):
        """Same input through fresh pipelines → identical output."""
        rng = np.random.default_rng(42)
        data = rng.standard_normal((24, SECTION_DECIMATED_CHANNELS))

        config = [
            {"step": "scale", "params": {"factor": 213.05}},
            {"step": "common_mode_removal", "params": {"warmup_seconds": 0.0}},
            {"step": "bandpass_filter", "params": {"low_freq_hz": 0.3, "high_freq_hz": 2.0}},
            {"step": "temporal_decimation", "params": {"factor": 12}},
            # No spatial decimation — data is already section-sized
        ]

        chain1 = build_pipeline_from_config(
            config, fiber_sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ
        )
        chain2 = build_pipeline_from_config(
            config, fiber_sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ
        )

        m1 = make_measurement(
            data.copy(), sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ, timestamps_ns=timestamps_ns[:]
        )
        m2 = make_measurement(
            data.copy(), sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ, timestamps_ns=timestamps_ns[:]
        )

        r1 = await chain1.process(m1)
        r2 = await chain2.process(m2)

        np.testing.assert_array_equal(r1["values"], r2["values"])


# ---------------------------------------------------------------------------
# Metrics registry alignment
# ---------------------------------------------------------------------------
class TestMetricsRegistryAlignment:
    """Verify metrics and step registry are in sync."""

    def test_all_steps_have_metrics(self):
        from shared.processor_metrics import _VALID_STEPS

        step_names = {
            "scale",
            "common_mode_removal",
            "bandpass_filter",
            "temporal_decimation",
            "spatial_decimation",
        }
        assert step_names == _VALID_STEPS
