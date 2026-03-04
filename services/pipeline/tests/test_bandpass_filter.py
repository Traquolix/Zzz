"""Tests for BandpassFilter processing step and VectorizedBiquadFilter."""

import numpy as np
import pytest

from processor.processing_tools.math.bandpass import VectorizedBiquadFilter
from processor.processing_tools.processing_steps.bandpass_filter import BandpassFilter


class TestVectorizedBiquadFilter:
    """Test the underlying biquad filter math."""

    def test_creates_state_with_correct_shape(self):
        """State shape should be (num_channels, num_sections, 2)."""
        filt = VectorizedBiquadFilter(low_freq=0.1, high_freq=2.0, sampling_rate=50.0)
        state = filt.create_state(100)

        assert state.shape == (100, filt.num_sections, 2)
        assert state.dtype == np.float64
        assert np.all(state == 0.0)

    def test_filter_returns_same_length(self):
        """Output length should match input length."""
        filt = VectorizedBiquadFilter(low_freq=0.1, high_freq=2.0, sampling_rate=50.0)
        state = filt.create_state(50)
        values = np.random.randn(50)

        result = filt.filter(values, state)

        assert result.shape == values.shape

    def test_filter_attenuates_dc(self):
        """A constant (DC) signal should be attenuated by the bandpass."""
        filt = VectorizedBiquadFilter(low_freq=0.5, high_freq=5.0, sampling_rate=50.0)
        num_channels = 10
        state = filt.create_state(num_channels)

        # Feed constant signal for many samples to let filter settle
        dc_signal = np.ones(num_channels) * 100.0
        for _ in range(500):
            result = filt.filter(dc_signal, state)

        # DC should be heavily attenuated (bandpass rejects 0 Hz)
        assert np.all(np.abs(result) < 1.0), f"DC not attenuated: max={np.max(np.abs(result))}"

    def test_filter_passes_in_band_signal(self):
        """A sine wave within the passband should pass through with significant amplitude."""
        sampling_rate = 50.0
        low_freq = 0.5
        high_freq = 5.0
        in_band_freq = 2.0  # Well within passband
        num_channels = 1

        filt = VectorizedBiquadFilter(low_freq, high_freq, sampling_rate)
        state = filt.create_state(num_channels)

        # Generate in-band sine wave, process sample-by-sample
        num_samples = 1000
        t = np.arange(num_samples) / sampling_rate
        input_signal = np.sin(2 * np.pi * in_band_freq * t)

        outputs = []
        for sample in input_signal:
            result = filt.filter(np.array([sample]), state)
            outputs.append(result[0])

        output_signal = np.array(outputs)

        # After settling (skip first 200 samples), output should have significant amplitude
        settled_output = output_signal[200:]
        peak_amplitude = np.max(np.abs(settled_output))

        assert peak_amplitude > 0.5, f"In-band signal too attenuated: peak={peak_amplitude}"

    def test_filter_attenuates_out_of_band_signal(self):
        """A sine wave well above the passband should be attenuated."""
        sampling_rate = 50.0
        low_freq = 0.5
        high_freq = 5.0
        out_of_band_freq = 20.0  # Well above passband
        num_channels = 1

        filt = VectorizedBiquadFilter(low_freq, high_freq, sampling_rate)
        state = filt.create_state(num_channels)

        num_samples = 1000
        t = np.arange(num_samples) / sampling_rate
        input_signal = np.sin(2 * np.pi * out_of_band_freq * t)

        outputs = []
        for sample in input_signal:
            result = filt.filter(np.array([sample]), state)
            outputs.append(result[0])

        output_signal = np.array(outputs)

        # After settling, output should be heavily attenuated
        settled_output = output_signal[200:]
        peak_amplitude = np.max(np.abs(settled_output))

        assert peak_amplitude < 0.1, f"Out-of-band signal not attenuated: peak={peak_amplitude}"

    def test_state_is_modified_in_place(self):
        """Filter should update state in place for continuity across calls."""
        filt = VectorizedBiquadFilter(low_freq=0.1, high_freq=2.0, sampling_rate=50.0)
        state = filt.create_state(5)

        assert np.all(state == 0.0)

        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        filt.filter(values, state)

        assert not np.all(state == 0.0), "State should be modified after filtering"


class TestBandpassFilter:
    """Test the BandpassFilter processing step."""

    @pytest.fixture
    def sample_measurement(self):
        return {
            "fiber_id": "test_fiber",
            "timestamp_ns": 1000000000000,
            "sampling_rate_hz": 50.0,
            "channel_start": 0,
            "values": [float(i) for i in range(20)],
        }

    def test_rejects_high_freq_above_nyquist(self):
        """Should raise if high_freq >= Nyquist frequency."""
        with pytest.raises(ValueError, match="must be less than Nyquist"):
            BandpassFilter(low_freq=0.1, high_freq=25.0, sampling_rate=50.0)

    def test_rejects_low_freq_above_high_freq(self):
        """Should raise if low_freq >= high_freq."""
        with pytest.raises(ValueError, match="must be less than high_freq"):
            BandpassFilter(low_freq=5.0, high_freq=2.0, sampling_rate=50.0)

    def test_valid_params_construct(self):
        """Should construct successfully with valid params."""
        bf = BandpassFilter(low_freq=0.1, high_freq=2.0, sampling_rate=50.0)
        assert bf.name == "bandpass_filter"

    @pytest.mark.asyncio
    async def test_returns_none_for_none_input(self):
        """Should return None for None input."""
        bf = BandpassFilter(low_freq=0.1, high_freq=2.0, sampling_rate=50.0)
        result = await bf.process(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_unchanged_for_empty_values(self, sample_measurement):
        """Should return measurement unchanged if values empty."""
        bf = BandpassFilter(low_freq=0.1, high_freq=2.0, sampling_rate=50.0)
        sample_measurement["values"] = []

        result = await bf.process(sample_measurement)

        assert result == sample_measurement

    @pytest.mark.asyncio
    async def test_output_has_same_channel_count(self, sample_measurement):
        """Output should have same number of values as input."""
        bf = BandpassFilter(low_freq=0.1, high_freq=2.0, sampling_rate=50.0)

        result = await bf.process(sample_measurement)

        assert result is not None
        assert len(result["values"]) == len(sample_measurement["values"])

    @pytest.mark.asyncio
    async def test_preserves_other_fields(self, sample_measurement):
        """Should preserve non-values fields."""
        bf = BandpassFilter(low_freq=0.1, high_freq=2.0, sampling_rate=50.0)

        result = await bf.process(sample_measurement)

        assert result["fiber_id"] == "test_fiber"
        assert result["timestamp_ns"] == 1000000000000
        assert result["sampling_rate_hz"] == 50.0
        assert result["channel_start"] == 0

    @pytest.mark.asyncio
    async def test_does_not_mutate_input(self, sample_measurement):
        """Should not modify the input measurement dict."""
        bf = BandpassFilter(low_freq=0.1, high_freq=2.0, sampling_rate=50.0)
        original_values = list(sample_measurement["values"])

        await bf.process(sample_measurement)

        assert sample_measurement["values"] == original_values

    @pytest.mark.asyncio
    async def test_creates_per_fiber_state(self):
        """Should maintain separate filter state per fiber_id."""
        bf = BandpassFilter(low_freq=0.1, high_freq=2.0, sampling_rate=50.0)

        fiber_a = {
            "fiber_id": "fiber_a",
            "values": [1.0] * 10,
        }
        fiber_b = {
            "fiber_id": "fiber_b",
            "values": [2.0] * 10,
        }

        await bf.process(fiber_a)
        await bf.process(fiber_b)

        assert bf.get_active_fiber_count() == 2
        assert "fiber_a" in bf._fiber_states
        assert "fiber_b" in bf._fiber_states

    @pytest.mark.asyncio
    async def test_reinitializes_state_on_channel_count_change(self):
        """Should reinitialize state when channel count changes for a fiber."""
        bf = BandpassFilter(low_freq=0.1, high_freq=2.0, sampling_rate=50.0)

        measurement_10ch = {
            "fiber_id": "test",
            "values": [1.0] * 10,
        }
        measurement_20ch = {
            "fiber_id": "test",
            "values": [1.0] * 20,
        }

        await bf.process(measurement_10ch)
        assert bf._fiber_states["test"]["channels"] == 10

        await bf.process(measurement_20ch)
        assert bf._fiber_states["test"]["channels"] == 20

    def test_cleanup_fiber_states(self):
        """Should evict oldest fibers when exceeding max."""
        bf = BandpassFilter(low_freq=0.1, high_freq=2.0, sampling_rate=50.0)

        # Manually populate states
        for i in range(10):
            bf._fiber_states[f"fiber_{i}"] = {
                "state": bf.filter.create_state(5),
                "channels": 5,
            }

        assert bf.get_active_fiber_count() == 10

        bf.cleanup_fiber_states(max_fibers=5)

        assert bf.get_active_fiber_count() == 5

    def test_cleanup_noop_under_limit(self):
        """Cleanup should do nothing when under the limit."""
        bf = BandpassFilter(low_freq=0.1, high_freq=2.0, sampling_rate=50.0)

        bf._fiber_states["fiber_a"] = {
            "state": bf.filter.create_state(5),
            "channels": 5,
        }

        bf.cleanup_fiber_states(max_fibers=10)

        assert bf.get_active_fiber_count() == 1
