"""Processor-to-AI-engine contract tests.

Verifies that processor output matches what the AI engine expects:
serialization format, sampling rate, channel count, byte layout.
These tests catch interface regressions that would cause silent
deserialization failures or wrong inference results.
"""

from __future__ import annotations

import numpy as np
import pytest

from processor.processing_tools.step_registry import build_pipeline_from_config

from .conftest import (
    ORIGINAL_SAMPLING_RATE_HZ,
    SECTION_CHANNEL_START,
    SECTION_CHANNEL_STOP,
    SECTION_DECIMATED_CHANNELS,
    make_measurement,
)

# AI engine expectations (from ai_engine/message_utils.py and conftest.py)
AI_ENGINE_EXPECTED_RATE_HZ = 10.4167
AI_ENGINE_RATE_TOLERANCE = 0.1  # validate_sampling_rate tolerance
AI_ENGINE_NCH = 9  # channels_per_section
AI_ENGINE_VALUES_DTYPE = np.float32  # np.frombuffer(values, dtype=np.float32)


def _run_production_pipeline(raw_data: np.ndarray, timestamps_ns: list[int]):
    """Build and run a production-config pipeline, return the processed dict."""
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
    return chain


def _simulate_build_output(processed: dict, original_rate: float = ORIGINAL_SAMPLING_RATE_HZ):
    """Simulate _build_batch_output serialization (the Kafka message payload)."""
    values = processed["values"]
    if not isinstance(values, np.ndarray):
        values = np.asarray(values, dtype=np.float64)

    if values.ndim == 2:
        n_samples, n_channels = values.shape
    elif values.ndim == 1:
        n_samples, n_channels = 1, values.shape[0]
        values = values.reshape(1, n_channels)
    else:
        return None

    flat_values = values.flatten().astype(np.float32)
    temporal_decimation = processed.get("temporal_decimation_factor", 1)

    return {
        "sampling_rate_hz": processed.get("sampling_rate_hz", original_rate / temporal_decimation),
        "channel_count": n_channels,
        "sample_count": n_samples,
        "values": flat_values.tobytes(),
    }


class TestSamplingRateContract:
    """Processor output sampling rate matches AI engine expectation."""

    async def test_rate_matches_ai_engine_expectation(self, raw_batch, timestamps_ns):
        chain = _run_production_pipeline(raw_batch, timestamps_ns)
        m = make_measurement(
            raw_batch, sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ, timestamps_ns=timestamps_ns
        )
        processed = await chain.process(m)
        assert processed is not None

        output = _simulate_build_output(processed)
        rate = output["sampling_rate_hz"]

        assert abs(rate - AI_ENGINE_EXPECTED_RATE_HZ) < AI_ENGINE_RATE_TOLERANCE, (
            f"Processor output rate {rate:.4f} Hz differs from AI engine expectation "
            f"{AI_ENGINE_EXPECTED_RATE_HZ} Hz by more than {AI_ENGINE_RATE_TOLERANCE} Hz. "
            f"This would cause validate_sampling_rate() to raise ValueError."
        )

    async def test_rate_is_original_divided_by_decimation(self, raw_batch, timestamps_ns):
        chain = _run_production_pipeline(raw_batch, timestamps_ns)
        m = make_measurement(
            raw_batch, sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ, timestamps_ns=timestamps_ns
        )
        processed = await chain.process(m)

        output = _simulate_build_output(processed)
        expected = ORIGINAL_SAMPLING_RATE_HZ / 12
        assert output["sampling_rate_hz"] == pytest.approx(expected)


class TestChannelCountContract:
    """Processor output channel count is compatible with AI engine Nch."""

    async def test_channel_count_at_least_nch(self, raw_batch, timestamps_ns):
        """AI engine requires at least Nch channels to form one spatial window."""
        chain = _run_production_pipeline(raw_batch, timestamps_ns)
        m = make_measurement(
            raw_batch, sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ, timestamps_ns=timestamps_ns
        )
        processed = await chain.process(m)

        output = _simulate_build_output(processed)
        assert output["channel_count"] >= AI_ENGINE_NCH, (
            f"Processor output {output['channel_count']} channels < Nch={AI_ENGINE_NCH}. "
            f"AI engine would skip this section with 'insufficient_channels'."
        )

    async def test_carros_channel_count(self, raw_batch, timestamps_ns):
        """Carros 202Bis section: (2748-1200)/3 = 516 channels."""
        chain = _run_production_pipeline(raw_batch, timestamps_ns)
        m = make_measurement(
            raw_batch, sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ, timestamps_ns=timestamps_ns
        )
        processed = await chain.process(m)

        output = _simulate_build_output(processed)
        assert output["channel_count"] == SECTION_DECIMATED_CHANNELS


class TestValueSerializationContract:
    """Values byte format matches what AI engine deserializes."""

    async def test_values_are_bytes(self, raw_batch, timestamps_ns):
        chain = _run_production_pipeline(raw_batch, timestamps_ns)
        m = make_measurement(
            raw_batch, sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ, timestamps_ns=timestamps_ns
        )
        processed = await chain.process(m)

        output = _simulate_build_output(processed)
        assert isinstance(output["values"], bytes)

    async def test_values_deserialize_as_float32(self, raw_batch, timestamps_ns):
        """AI engine does np.frombuffer(values, dtype=np.float32)."""
        chain = _run_production_pipeline(raw_batch, timestamps_ns)
        m = make_measurement(
            raw_batch, sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ, timestamps_ns=timestamps_ns
        )
        processed = await chain.process(m)

        output = _simulate_build_output(processed)
        arr = np.frombuffer(output["values"], dtype=np.float32)

        assert arr.dtype == np.float32
        assert np.all(np.isfinite(arr))

    async def test_values_byte_length_matches_shape(self, raw_batch, timestamps_ns):
        """len(values) == channel_count * sample_count * 4 (float32 = 4 bytes)."""
        chain = _run_production_pipeline(raw_batch, timestamps_ns)
        m = make_measurement(
            raw_batch, sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ, timestamps_ns=timestamps_ns
        )
        processed = await chain.process(m)

        output = _simulate_build_output(processed)
        expected_bytes = output["channel_count"] * output["sample_count"] * 4
        assert len(output["values"]) == expected_bytes, (
            f"Values byte length {len(output['values'])} != "
            f"{output['channel_count']} channels * {output['sample_count']} samples * 4 bytes"
        )

    async def test_reshape_roundtrip(self, raw_batch, timestamps_ns):
        """AI engine reshapes to (sample_count, channel_count) then transposes to (channels, samples)."""
        chain = _run_production_pipeline(raw_batch, timestamps_ns)
        m = make_measurement(
            raw_batch, sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ, timestamps_ns=timestamps_ns
        )
        processed = await chain.process(m)

        output = _simulate_build_output(processed)
        arr = np.frombuffer(output["values"], dtype=np.float32).astype(np.float64)
        reshaped = arr.reshape(output["sample_count"], output["channel_count"])

        # AI engine transposes: (samples, channels) -> (channels, samples)
        transposed = reshaped.T
        assert transposed.shape == (output["channel_count"], output["sample_count"])

    async def test_values_all_finite(self, raw_batch, timestamps_ns):
        """No NaN or Inf in serialized output."""
        chain = _run_production_pipeline(raw_batch, timestamps_ns)
        m = make_measurement(
            raw_batch, sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ, timestamps_ns=timestamps_ns
        )
        processed = await chain.process(m)

        output = _simulate_build_output(processed)
        arr = np.frombuffer(output["values"], dtype=np.float32)
        assert np.all(np.isfinite(arr)), "Serialized values contain NaN or Inf"
