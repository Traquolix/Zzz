"""Tests for BandpassFilter processing step and VectorizedBiquadFilter.

Validates frequency response, stateful filtering across batches,
NaN contamination, channel changes, and determinism.
"""

from __future__ import annotations

import numpy as np
import pytest

from processor.processing_tools.math.bandpass import VectorizedBiquadFilter
from processor.processing_tools.processing_steps.bandpass_filter import BandpassFilter

from .conftest import BANDPASS_HIGH_HZ, BANDPASS_LOW_HZ, ORIGINAL_SAMPLING_RATE_HZ, make_measurement


# ---------------------------------------------------------------------------
# VectorizedBiquadFilter (low-level)
# ---------------------------------------------------------------------------
class TestVectorizedBiquadFilter:
    """Direct tests for the scipy sosfilt wrapper."""

    def test_create_state_shape(self):
        f = VectorizedBiquadFilter(0.3, 2.0, sampling_rate=125.0)
        state = f.create_state(100)

        assert state.shape == (f.num_sections, 100, 2)
        assert state.dtype == np.float64
        np.testing.assert_array_equal(state, 0.0)

    def test_passband_signal_preserved(self):
        """A 1 Hz sinusoid (inside 0.3-2.0 Hz passband) should pass through."""
        fs = 125.0
        f = VectorizedBiquadFilter(0.3, 2.0, sampling_rate=fs)
        state = f.create_state(1)

        # Generate 10 seconds of 1 Hz sine (well within passband)
        t = np.arange(int(10 * fs)) / fs
        signal = np.sin(2 * np.pi * 1.0 * t).reshape(-1, 1)

        filtered = f.filter(signal, state)

        # After settling (~2 seconds for order-4 Butterworth), amplitude should be ~1
        steady_state = filtered[int(4 * fs) :, 0]
        amplitude = (np.max(steady_state) - np.min(steady_state)) / 2
        assert amplitude > 0.9, f"Passband signal attenuated to {amplitude:.3f}"

    def test_stopband_signal_attenuated(self):
        """A 10 Hz sinusoid (outside 0.3-2.0 Hz passband) should be attenuated."""
        fs = 125.0
        f = VectorizedBiquadFilter(0.3, 2.0, sampling_rate=fs)
        state = f.create_state(1)

        t = np.arange(int(10 * fs)) / fs
        signal = np.sin(2 * np.pi * 10.0 * t).reshape(-1, 1)

        filtered = f.filter(signal, state)

        steady_state = filtered[int(4 * fs) :, 0]
        amplitude = (np.max(steady_state) - np.min(steady_state)) / 2
        assert amplitude < 0.01, f"Stopband signal not attenuated: {amplitude:.3f}"

    def test_dc_rejected(self):
        """DC component (0 Hz, below 0.3 Hz cutoff) should be removed."""
        fs = 125.0
        f = VectorizedBiquadFilter(0.3, 2.0, sampling_rate=fs)
        state = f.create_state(1)

        # 30 seconds of DC to allow full settling at 0.3 Hz cutoff
        # (time constant ~ 1/(2*pi*0.3) ≈ 0.5s, need ~10x for 4th order)
        signal = np.ones((int(30 * fs), 1)) * 100.0
        filtered = f.filter(signal, state)

        # After 20 seconds of settling, output should be near zero
        steady_state = filtered[int(20 * fs) :, 0]
        assert np.abs(steady_state).max() < 0.01

    def test_state_updated_in_place(self):
        f = VectorizedBiquadFilter(0.3, 2.0, sampling_rate=125.0)
        state = f.create_state(5)
        assert np.all(state == 0)

        signal = np.random.default_rng(42).standard_normal((100, 5))
        f.filter(signal, state)

        assert not np.all(state == 0), "State should be modified after filtering"

    def test_1d_input(self):
        f = VectorizedBiquadFilter(0.3, 2.0, sampling_rate=125.0)
        state = f.create_state(10)
        signal = np.random.default_rng(42).standard_normal(10)

        result = f.filter(signal, state)
        assert result.shape == (10,)

    def test_2d_input_shape_preserved(self):
        f = VectorizedBiquadFilter(0.3, 2.0, sampling_rate=125.0)
        state = f.create_state(20)
        signal = np.random.default_rng(42).standard_normal((50, 20))

        result = f.filter(signal, state)
        assert result.shape == (50, 20)


class TestVectorizedBiquadFilterStateContinuity:
    """Filter state continuity across successive calls."""

    def test_batch_vs_chunked_equivalence(self):
        """Processing as one batch vs. two chunks must produce identical output."""
        fs = 125.0
        f1 = VectorizedBiquadFilter(0.3, 2.0, sampling_rate=fs)
        f2 = VectorizedBiquadFilter(0.3, 2.0, sampling_rate=fs)
        state1 = f1.create_state(5)
        state2 = f2.create_state(5)

        rng = np.random.default_rng(99)
        data = rng.standard_normal((200, 5))

        # One shot
        result_whole = f1.filter(data, state1)

        # Two chunks
        result_part1 = f2.filter(data[:100], state2)
        result_part2 = f2.filter(data[100:], state2)
        result_chunked = np.vstack([result_part1, result_part2])

        np.testing.assert_allclose(result_whole, result_chunked, rtol=1e-12, atol=1e-15)


# ---------------------------------------------------------------------------
# BandpassFilter step
# ---------------------------------------------------------------------------
class TestBandpassFilterStep:
    """Tests for the ProcessingStep wrapper."""

    async def test_basic_filtering(self, small_batch):
        step = BandpassFilter(
            low_freq=BANDPASS_LOW_HZ,
            high_freq=BANDPASS_HIGH_HZ,
            sampling_rate=ORIGINAL_SAMPLING_RATE_HZ,
        )
        m = make_measurement(small_batch)
        result = await step.process(m)

        assert result is not None
        assert result["values"].shape == small_batch.shape
        assert result["values"].dtype == np.float64

    async def test_none_input_returns_none(self):
        step = BandpassFilter(low_freq=0.3, high_freq=2.0, sampling_rate=125.0)
        assert await step.process(None) is None

    async def test_empty_channels_unchanged(self):
        step = BandpassFilter(low_freq=0.3, high_freq=2.0, sampling_rate=125.0)
        values = np.array([]).reshape(0, 0)
        m = make_measurement(values)
        result = await step.process(m)
        # Empty channel count → returned unchanged
        assert result["values"].size == 0

    async def test_per_fiber_state_isolation(self):
        """Different fibers get independent filter states."""
        step = BandpassFilter(low_freq=0.3, high_freq=2.0, sampling_rate=125.0)
        rng = np.random.default_rng(42)

        data_a = rng.standard_normal((50, 10))
        data_b = rng.standard_normal((50, 10))

        r_a = await step.process(make_measurement(data_a, fiber_id="fiber_a"))
        r_b = await step.process(make_measurement(data_b, fiber_id="fiber_b"))

        assert step.get_active_fiber_count() == 2
        # Outputs should differ (different inputs, independent states)
        assert not np.array_equal(r_a["values"], r_b["values"])

    async def test_channel_count_change_resets_state(self):
        """If channel count changes, filter state is recreated."""
        step = BandpassFilter(low_freq=0.3, high_freq=2.0, sampling_rate=125.0)

        data_10ch = np.random.default_rng(42).standard_normal((24, 10))
        await step.process(make_measurement(data_10ch, fiber_id="f1"))
        assert step._fiber_states["f1"]["channels"] == 10

        data_20ch = np.random.default_rng(42).standard_normal((24, 20))
        await step.process(make_measurement(data_20ch, fiber_id="f1"))
        assert step._fiber_states["f1"]["channels"] == 20

    async def test_metadata_preserved(self, small_batch):
        step = BandpassFilter(low_freq=0.3, high_freq=2.0, sampling_rate=125.0)
        m = make_measurement(small_batch, fiber_id="carros", sampling_rate_hz=125.0)
        result = await step.process(m)

        assert result["fiber_id"] == "carros"
        assert result["sampling_rate_hz"] == 125.0

    async def test_does_not_modify_input(self, small_batch):
        step = BandpassFilter(low_freq=0.3, high_freq=2.0, sampling_rate=125.0)
        original = small_batch.copy()
        await step.process(make_measurement(small_batch))

        np.testing.assert_array_equal(small_batch, original)


class TestBandpassFilterValidation:
    """Constructor validation."""

    def test_high_freq_at_nyquist_raises(self):
        with pytest.raises(ValueError, match="Nyquist"):
            BandpassFilter(low_freq=0.3, high_freq=62.5, sampling_rate=125.0)

    def test_high_freq_above_nyquist_raises(self):
        with pytest.raises(ValueError, match="Nyquist"):
            BandpassFilter(low_freq=0.3, high_freq=100.0, sampling_rate=125.0)

    def test_low_freq_above_high_freq_raises(self):
        with pytest.raises(ValueError, match="less than high_freq"):
            BandpassFilter(low_freq=5.0, high_freq=2.0, sampling_rate=125.0)

    def test_equal_freqs_raises(self):
        with pytest.raises(ValueError, match="less than high_freq"):
            BandpassFilter(low_freq=2.0, high_freq=2.0, sampling_rate=125.0)


class TestBandpassFilterNaNSanitization:
    """NaN/Inf sanitization prevents filter state contamination."""

    async def test_nan_sanitized_output_is_finite(self):
        """NaN values are replaced with 0.0 before filtering."""
        step = BandpassFilter(low_freq=0.3, high_freq=2.0, sampling_rate=125.0)
        rng = np.random.default_rng(42)

        # Clean batch to establish state
        clean = rng.standard_normal((100, 5))
        await step.process(make_measurement(clean, fiber_id="f1"))

        # Inject NaN — should be sanitized, not propagated
        dirty = rng.standard_normal((10, 5))
        dirty[5, 2] = np.nan
        result_dirty = await step.process(make_measurement(dirty, fiber_id="f1"))

        assert np.all(np.isfinite(result_dirty["values"])), (
            "NaN should be sanitized to 0.0 before filtering"
        )

    async def test_nan_does_not_contaminate_subsequent_batches(self):
        """After a NaN batch, subsequent clean batches produce finite output."""
        step = BandpassFilter(low_freq=0.3, high_freq=2.0, sampling_rate=125.0)
        rng = np.random.default_rng(42)

        clean = rng.standard_normal((100, 5))
        await step.process(make_measurement(clean, fiber_id="f1"))

        dirty = rng.standard_normal((10, 5))
        dirty[5, 2] = np.nan
        await step.process(make_measurement(dirty, fiber_id="f1"))

        # Subsequent clean batch must be NaN-free
        clean2 = rng.standard_normal((10, 5))
        result_after = await step.process(make_measurement(clean2, fiber_id="f1"))

        assert np.all(np.isfinite(result_after["values"])), (
            "Filter state should not be contaminated after NaN sanitization"
        )

    async def test_inf_sanitized(self):
        """Inf values are also replaced with 0.0."""
        step = BandpassFilter(low_freq=0.3, high_freq=2.0, sampling_rate=125.0)

        values = np.ones((10, 5))
        values[3, 1] = np.inf
        values[7, 4] = -np.inf
        result = await step.process(make_measurement(values, fiber_id="f1"))

        assert np.all(np.isfinite(result["values"]))

    async def test_nan_does_not_contaminate_other_fibers(self):
        """NaN in fiber A should not affect fiber B."""
        step = BandpassFilter(low_freq=0.3, high_freq=2.0, sampling_rate=125.0)
        rng = np.random.default_rng(42)

        dirty = rng.standard_normal((10, 5))
        dirty[5, 2] = np.nan
        await step.process(make_measurement(dirty, fiber_id="fiber_a"))

        clean = rng.standard_normal((10, 5))
        result_b = await step.process(make_measurement(clean, fiber_id="fiber_b"))

        assert not np.any(np.isnan(result_b["values"]))

    async def test_nan_input_not_modified(self):
        """Sanitization should not modify the original input array."""
        step = BandpassFilter(low_freq=0.3, high_freq=2.0, sampling_rate=125.0)
        values = np.ones((5, 3))
        values[2, 1] = np.nan
        original = values.copy()

        await step.process(make_measurement(values))

        # Original array should still have NaN
        assert np.isnan(original[2, 1])
        assert np.isnan(values[2, 1])


class TestBandpassFilterDeterminism:
    """Deterministic output for identical inputs."""

    async def test_fresh_instances_produce_identical_output(self):
        rng = np.random.default_rng(42)
        data = rng.standard_normal((100, 10))

        step1 = BandpassFilter(low_freq=0.3, high_freq=2.0, sampling_rate=125.0)
        step2 = BandpassFilter(low_freq=0.3, high_freq=2.0, sampling_rate=125.0)

        r1 = await step1.process(make_measurement(data.copy()))
        r2 = await step2.process(make_measurement(data.copy()))

        np.testing.assert_array_equal(r1["values"], r2["values"])
