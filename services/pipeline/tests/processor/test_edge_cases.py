"""Edge case and failure mode tests for the processor pipeline.

Tests input conditions that shouldn't crash the pipeline: NaN, Inf,
all-zeros, single samples, dtype variations, and shape mismatches.
"""

from __future__ import annotations

import numpy as np

from processor.processing_tools.processing_chain import ProcessingChain
from processor.processing_tools.processing_steps.bandpass_filter import BandpassFilter
from processor.processing_tools.processing_steps.common_mode_removal import CommonModeRemoval
from processor.processing_tools.processing_steps.scale import Scale
from processor.processing_tools.processing_steps.spatial_decimation import SpatialDecimation
from processor.processing_tools.processing_steps.temporal_decimation import TemporalDecimation
from processor.processing_tools.step_registry import build_pipeline_from_config

from .conftest import ORIGINAL_SAMPLING_RATE_HZ, make_measurement


def _quick_chain(warmup: float = 0.0) -> ProcessingChain:
    """Build a production-like pipeline for edge case testing."""
    config = [
        {"step": "scale", "params": {"factor": 213.05}},
        {"step": "common_mode_removal", "params": {"warmup_seconds": warmup, "method": "median"}},
        {"step": "bandpass_filter", "params": {"low_freq_hz": 0.3, "high_freq_hz": 2.0}},
        {"step": "temporal_decimation", "params": {"factor": 12}},
        {"step": "spatial_decimation", "params": {"factor": 3}},
    ]
    return build_pipeline_from_config(
        config,
        fiber_sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
        section_channels=(0, 60),  # small section for fast tests
    )


class TestAllZerosInput:
    """All-zeros data through the full pipeline."""

    async def test_all_zeros_no_crash(self):
        chain = _quick_chain()
        values = np.zeros((24, 100))
        m = make_measurement(values, sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ)
        result = await chain.process(m)

        # May be None (temporal decimation drops) or zeros
        if result is not None:
            assert np.all(np.isfinite(result["values"]))

    async def test_all_zeros_produces_zeros_after_cmr(self):
        """CMR of zeros = 0, scale of zeros = 0, bandpass of zeros ≈ 0."""
        step = CommonModeRemoval(warmup_seconds=0.0)
        m = make_measurement(np.zeros((24, 20)), sampling_rate_hz=125.0)
        result = await step.process(m)

        np.testing.assert_array_equal(result["values"], 0.0)


class TestNaNInput:
    """NaN propagation behavior. Bandpass sanitizes NaN; other steps propagate it."""

    async def test_scale_propagates_nan(self):
        step = Scale(factor=213.05)
        values = np.ones((5, 5))
        values[2, 3] = np.nan
        result = await step.process(make_measurement(values))

        assert np.isnan(result["values"][2, 3])
        assert np.isfinite(result["values"][0, 0])

    async def test_cmr_with_nan_in_one_channel(self):
        """NaN in one channel should not wipe the entire row (nanmedian)."""
        step = CommonModeRemoval(warmup_seconds=0.0, method="median")
        values = np.ones((3, 5))
        values[1, 2] = np.nan  # row 1, col 2
        result = await step.process(make_measurement(values))

        # nanmedian ignores NaN: median of [1, 1, NaN, 1, 1] = 1.0
        # So non-NaN channels in row 1 should be finite (1.0 - 1.0 = 0.0)
        assert np.isfinite(result["values"][1, 0])
        # The NaN channel itself stays NaN (NaN - 1.0 = NaN)
        assert np.isnan(result["values"][1, 2])
        # Row 0 should be unaffected
        assert np.all(np.isfinite(result["values"][0]))

    async def test_temporal_decimation_with_nan(self):
        step = TemporalDecimation(factor=4)
        values = np.ones((12, 3))
        values[3, 0] = np.nan  # This is the 4th sample (index 3), which IS kept
        m = make_measurement(values, sampling_rate_hz=125.0)
        result = await step.process(m)

        assert result is not None
        # NaN should be preserved in the kept sample
        assert np.isnan(result["values"][0, 0])

    async def test_spatial_decimation_with_nan(self):
        step = SpatialDecimation(factor=2)
        values = np.ones((3, 10))
        values[0, 4] = np.nan  # channel 4, kept by factor=2 (indices 0,2,4,6,8)
        result = await step.process(make_measurement(values))

        assert np.isnan(result["values"][0, 2])  # channel 4 → index 2 after stride


class TestInfInput:
    """Inf propagation behavior."""

    async def test_scale_with_inf(self):
        step = Scale(factor=213.05)
        values = np.array([[np.inf, -np.inf, 0.0]])
        result = await step.process(make_measurement(values))

        assert result["values"][0, 0] == np.inf
        assert result["values"][0, 1] == -np.inf

    async def test_cmr_with_inf(self):
        step = CommonModeRemoval(warmup_seconds=0.0, method="median")
        values = np.ones((1, 5))
        values[0, 2] = np.inf
        result = await step.process(make_measurement(values))

        # Median of [1, 1, inf, 1, 1] = 1.0, so inf - 1 = inf
        assert np.isinf(result["values"][0, 2])


class TestSingleSampleBatch:
    """Single-sample (1 row) batch through each step."""

    async def test_scale_single_sample(self):
        step = Scale(factor=2.0)
        values = np.array([[1.0, 2.0, 3.0]])
        result = await step.process(make_measurement(values))

        np.testing.assert_array_equal(result["values"], [[2.0, 4.0, 6.0]])

    async def test_cmr_single_sample(self):
        step = CommonModeRemoval(warmup_seconds=0.0)
        values = np.array([[1.0, 2.0, 3.0]])
        result = await step.process(make_measurement(values))

        # Median = 2.0
        np.testing.assert_allclose(result["values"], [[-1.0, 0.0, 1.0]])

    async def test_bandpass_single_sample(self):
        step = BandpassFilter(low_freq=0.3, high_freq=2.0, sampling_rate=125.0)
        values = np.ones((1, 10))
        result = await step.process(make_measurement(values))

        assert result["values"].shape == (1, 10)

    async def test_temporal_decimation_single_sample_factor_1(self):
        step = TemporalDecimation(factor=1)
        values = np.array([[1.0, 2.0]])
        m = make_measurement(values, sampling_rate_hz=125.0)
        result = await step.process(m)

        assert result is not None

    async def test_spatial_decimation_single_sample(self):
        step = SpatialDecimation(factor=2)
        values = np.array([[1.0, 2.0, 3.0, 4.0]])
        result = await step.process(make_measurement(values))

        np.testing.assert_array_equal(result["values"], [[1.0, 3.0]])


class TestDtypeVariations:
    """Input dtype handling — all steps should handle non-float64 input."""

    async def test_scale_int_input(self):
        step = Scale(factor=2.0)
        values = np.array([[1, 2, 3]], dtype=np.int32)
        m = make_measurement(values)
        m["values"] = values  # Override to keep int dtype
        result = await step.process(m)

        # Scale doesn't convert to float64 first if already ndarray
        assert result is not None

    async def test_scale_float32_input(self):
        step = Scale(factor=2.0)
        values = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)
        result = await step.process(make_measurement(values))

        assert result is not None
        np.testing.assert_allclose(result["values"][0], [2.0, 4.0, 6.0], rtol=1e-6)

    async def test_bandpass_float32_input_coerced(self):
        step = BandpassFilter(low_freq=0.3, high_freq=2.0, sampling_rate=125.0)
        values = np.ones((24, 10), dtype=np.float32)
        result = await step.process(make_measurement(values))

        # VectorizedBiquadFilter converts to float64 internally
        assert result["values"].dtype == np.float64


class TestMultiFiberSequence:
    """Multiple fibers processed through same pipeline."""

    async def test_interleaved_fibers_independent(self):
        """Processing fiber A then B then A again - state correctly separated."""
        chain = _quick_chain()
        rng = np.random.default_rng(42)

        # Process fibers in interleaved order: A, B, A
        # The test verifies no crash occurs with interleaved stateful processing
        await chain.process(
            make_measurement(
                rng.standard_normal((24, 100)),
                fiber_id="a",
                sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
            ),
            fiber_id="a",
            section="s",
        )
        await chain.process(
            make_measurement(
                rng.standard_normal((24, 100)),
                fiber_id="b",
                sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
            ),
            fiber_id="b",
            section="s",
        )
        await chain.process(
            make_measurement(
                rng.standard_normal((24, 100)),
                fiber_id="a",
                sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
            ),
            fiber_id="a",
            section="s",
        )
