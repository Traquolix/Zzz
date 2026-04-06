"""Tests for TemporalDecimation processing step.

Validates sample selection, global counter alignment, cross-batch
continuity, timestamp handling, and edge cases.
"""

from __future__ import annotations

import numpy as np
import pytest

from processor.processing_tools.processing_steps.temporal_decimation import (
    TemporalDecimation,
)

from .conftest import make_measurement


class TestTemporalDecimationBasic:
    """Core decimation behavior."""

    async def test_output_sampling_rate(self):
        step = TemporalDecimation(factor=12)
        values = np.ones((24, 10))
        m = make_measurement(values, sampling_rate_hz=125.0)
        result = await step.process(m)

        if result is not None:
            assert result["sampling_rate_hz"] == pytest.approx(125.0 / 12)

    async def test_factor_1_keeps_all_samples(self):
        step = TemporalDecimation(factor=1)
        values = np.arange(24 * 5, dtype=np.float64).reshape(24, 5)
        m = make_measurement(values, sampling_rate_hz=125.0)
        result = await step.process(m)

        # factor=1: sample_indices % 1 == 0 is always True
        # But 1-based indexing: indices are 1..24, all % 1 == 0
        assert result is not None
        assert result["values"].shape[0] == 24
        assert result["sampling_rate_hz"] == 125.0

    async def test_output_sample_count_correct(self):
        """With factor=12 and 24 input samples, exactly 2 should be kept."""
        step = TemporalDecimation(factor=12)
        values = np.arange(24 * 5, dtype=np.float64).reshape(24, 5)
        m = make_measurement(values, sampling_rate_hz=125.0)
        result = await step.process(m)

        assert result is not None
        # 1-based: indices 1..24. Indices % 12 == 0: 12, 24. So 2 samples.
        assert result["values"].shape[0] == 2

    async def test_correct_samples_selected(self):
        """Verify which exact rows are kept."""
        step = TemporalDecimation(factor=4)
        # 12 samples, each row is identifiable
        values = np.arange(12 * 3, dtype=np.float64).reshape(12, 3)
        m = make_measurement(values, sampling_rate_hz=125.0)
        result = await step.process(m)

        assert result is not None
        # 1-based indices: 1..12. Indices % 4 == 0: 4, 8, 12 → local [3, 7, 11]
        expected_rows = values[[3, 7, 11]]
        np.testing.assert_array_equal(result["values"], expected_rows)


class TestTemporalDecimationCrossBatch:
    """Global counter continuity across batches."""

    async def test_counter_spans_batches(self):
        """Samples selected depend on cumulative position, not batch-local index."""
        step = TemporalDecimation(factor=12)

        all_kept = []
        for batch_idx in range(5):
            values = np.full((24, 3), float(batch_idx))
            m = make_measurement(values, sampling_rate_hz=125.0)
            result = await step.process(m)
            if result is not None:
                all_kept.append(result["values"])

        # 5 batches x 24 = 120 samples. Indices 1..120.
        # 120/12 = 10 samples kept total.
        total_kept = sum(v.shape[0] for v in all_kept)
        assert total_kept == 10

    async def test_all_dropped_batch_returns_none(self):
        """A batch where no samples align with the decimation grid returns None."""
        step = TemporalDecimation(factor=100)
        # 24 samples: indices 1..24, none divisible by 100
        values = np.ones((24, 5))
        m = make_measurement(values, sampling_rate_hz=125.0)
        result = await step.process(m)

        assert result is None

    async def test_per_fiber_counter_isolation(self):
        step = TemporalDecimation(factor=12)

        # Fiber A: 24 samples → counter advances to 24
        m_a = make_measurement(np.ones((24, 5)), fiber_id="a", sampling_rate_hz=125.0)
        await step.process(m_a)

        # Fiber B: starts fresh from counter=0
        m_b = make_measurement(np.ones((24, 5)), fiber_id="b", sampling_rate_hz=125.0)
        await step.process(m_b)

        # Both fibers at same batch -> same decimation behavior
        # (both start from counter 0, same result)
        assert step._counts["a"] == 24
        assert step._counts["b"] == 24


class TestTemporalDecimationTimestamps:
    """Timestamp handling."""

    async def test_timestamps_decimated_in_sync(self):
        step = TemporalDecimation(factor=4)
        values = np.arange(12 * 3, dtype=np.float64).reshape(12, 3)
        ts = list(range(1000, 1012))
        m = make_measurement(values, sampling_rate_hz=125.0, timestamps_ns=ts)
        result = await step.process(m)

        assert result is not None
        # Kept indices: [3, 7, 11] → timestamps [1003, 1007, 1011]
        assert result["timestamps_ns"] == [1003, 1007, 1011]

    async def test_no_timestamps_still_works(self):
        step = TemporalDecimation(factor=4)
        values = np.ones((12, 3))
        m = make_measurement(values, sampling_rate_hz=125.0)
        # No timestamps_ns in measurement
        result = await step.process(m)

        assert result is not None
        assert "timestamps_ns" not in result or result.get("timestamps_ns") is None


class TestTemporalDecimationEdgeCases:
    """Edge cases and validation."""

    async def test_none_input_returns_none(self):
        step = TemporalDecimation(factor=12)
        assert await step.process(None) is None

    def test_factor_zero_raises(self):
        with pytest.raises(ValueError, match="factor must be >= 1"):
            TemporalDecimation(factor=0)

    def test_negative_factor_raises(self):
        with pytest.raises(ValueError, match="factor must be >= 1"):
            TemporalDecimation(factor=-1)

    async def test_missing_sampling_rate_raises(self):
        step = TemporalDecimation(factor=12)
        m = {"fiber_id": "test", "values": np.ones((24, 5))}
        # No sampling_rate_hz
        with pytest.raises(ValueError, match="sampling_rate_hz"):
            await step.process(m)

    async def test_single_sample_batch(self):
        """Single-sample batch: only kept if counter aligns."""
        step = TemporalDecimation(factor=3)

        kept_count = 0
        for _ in range(6):
            values = np.ones((1, 5))
            m = make_measurement(values, sampling_rate_hz=125.0)
            result = await step.process(m)
            if result is not None:
                kept_count += 1

        # 6 single-sample messages: indices 1..6. Divisible by 3: {3, 6} → 2 kept
        assert kept_count == 2

    async def test_decimation_factor_metadata_set(self):
        step = TemporalDecimation(factor=12)
        values = np.ones((24, 5))
        m = make_measurement(values, sampling_rate_hz=125.0)
        result = await step.process(m)

        if result is not None:
            assert result["temporal_decimation_factor"] == 12


class TestTemporalDecimationDeterminism:
    """Deterministic output."""

    async def test_fresh_instances_same_output(self):
        data = np.random.default_rng(42).standard_normal((48, 10))

        step1 = TemporalDecimation(factor=12)
        step2 = TemporalDecimation(factor=12)

        r1 = await step1.process(make_measurement(data.copy(), sampling_rate_hz=125.0))
        r2 = await step2.process(make_measurement(data.copy(), sampling_rate_hz=125.0))

        np.testing.assert_array_equal(r1["values"], r2["values"])
