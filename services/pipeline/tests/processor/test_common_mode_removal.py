"""Tests for CommonModeRemoval processing step.

Validates warmup behavior, median/mean subtraction, per-fiber isolation,
and edge cases.
"""

from __future__ import annotations

import numpy as np
import pytest

from processor.processing_tools.processing_steps.common_mode_removal import (
    CommonModeRemoval,
)

from .conftest import ORIGINAL_SAMPLING_RATE_HZ, make_measurement


class TestCMRWarmup:
    """Warmup period: messages dropped until warmup_samples reached."""

    async def test_messages_dropped_during_warmup(self):
        step = CommonModeRemoval(warmup_seconds=1.0, method="median")
        # At 125 Hz, warmup = 125 samples. Batch of 24 → need ~6 batches
        for _ in range(5):
            m = make_measurement(
                np.ones((24, 10)),
                sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
            )
            result = await step.process(m)
            assert result is None, "Should return None during warmup"

    async def test_first_post_warmup_message_processed(self):
        step = CommonModeRemoval(warmup_seconds=0.1, method="median")
        # warmup = 0.1 * 125 = 12 samples. One batch of 24 fills warmup.
        # First batch: count goes 0→24, but 0 < 12 check passes → dropped
        # Wait: count starts at 0, check is count < warmup_samples (12).
        # Batch adds 24 samples. count=0 < 12 → return None, count becomes 24.
        # Second batch: count=24 >= 12 → processed
        m1 = make_measurement(np.ones((24, 10)), sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ)
        assert await step.process(m1) is None

        m2 = make_measurement(np.ones((24, 10)), sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ)
        result = await step.process(m2)
        assert result is not None

    async def test_zero_warmup_processes_immediately(self):
        step = CommonModeRemoval(warmup_seconds=0.0, method="median")
        m = make_measurement(np.ones((24, 10)), sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ)
        result = await step.process(m)

        assert result is not None

    async def test_warmup_sample_count_tracks_batch_size(self):
        """Warmup counts actual samples, not messages."""
        step = CommonModeRemoval(warmup_seconds=1.0, method="median")
        # warmup = 125 samples. Send 6 batches of 24 = 144 samples total
        for _i in range(6):
            m = make_measurement(np.ones((24, 10)), sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ)
            result = await step.process(m)
            # Batches 0-4 (120 samples): warmup. Batch 5 (count=120 → check 120 < 125).
            # count incremented to 144 before return None.
            # Actually: batch 0: count=0 < 125 → None, count=24
            # batch 4: count=96 < 125 → None, count=120
            # batch 5: count=120 < 125 → None, count=144
            # batch 6 would be first processed
        # 6 batches = 144 samples, but the check is *before* increment:
        # count is checked, then incremented. So count=120 < 125 → None.
        assert result is None

        m = make_measurement(np.ones((24, 10)), sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ)
        result = await step.process(m)
        # count=144 >= 125 → processed
        assert result is not None


class TestCMRSubtraction:
    """Core common mode removal math."""

    async def test_median_subtraction_2d(self):
        step = CommonModeRemoval(warmup_seconds=0.0, method="median")
        # 3 samples, 5 channels. Median across channels (axis=1) per sample.
        values = np.array(
            [
                [1.0, 2.0, 3.0, 4.0, 5.0],
                [10.0, 20.0, 30.0, 40.0, 50.0],
                [100.0, 100.0, 100.0, 100.0, 100.0],
            ]
        )
        result = await step.process(make_measurement(values))

        # Row 0: median=3.0 → [-2, -1, 0, 1, 2]
        np.testing.assert_allclose(result["values"][0], [-2.0, -1.0, 0.0, 1.0, 2.0])
        # Row 1: median=30.0 → [-20, -10, 0, 10, 20]
        np.testing.assert_allclose(result["values"][1], [-20.0, -10.0, 0.0, 10.0, 20.0])
        # Row 2: median=100.0 → all zeros
        np.testing.assert_allclose(result["values"][2], [0.0, 0.0, 0.0, 0.0, 0.0])

    async def test_mean_subtraction_2d(self):
        step = CommonModeRemoval(warmup_seconds=0.0, method="mean")
        values = np.array([[1.0, 2.0, 3.0, 4.0, 5.0]])
        result = await step.process(make_measurement(values))

        # Mean of [1,2,3,4,5] = 3.0
        np.testing.assert_allclose(result["values"][0], [-2.0, -1.0, 0.0, 1.0, 2.0])

    async def test_1d_input(self):
        step = CommonModeRemoval(warmup_seconds=0.0, method="median")
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = await step.process(make_measurement(values))

        # Median = 3.0
        np.testing.assert_allclose(result["values"], [-2.0, -1.0, 0.0, 1.0, 2.0])

    async def test_output_has_zero_spatial_mean(self, small_batch):
        step = CommonModeRemoval(warmup_seconds=0.0, method="mean")
        result = await step.process(make_measurement(small_batch))

        # After mean removal, each row should have zero mean
        row_means = result["values"].mean(axis=1)
        np.testing.assert_allclose(row_means, 0.0, atol=1e-12)

    async def test_constant_signal_produces_zeros(self):
        step = CommonModeRemoval(warmup_seconds=0.0, method="median")
        values = np.full((10, 20), 42.0)
        result = await step.process(make_measurement(values))

        np.testing.assert_array_equal(result["values"], 0.0)


class TestCMRPerFiberIsolation:
    """Per-fiber state is independent."""

    async def test_separate_fiber_warmup_tracking(self):
        step = CommonModeRemoval(warmup_seconds=0.1, method="median")
        # warmup = 12 samples at 125 Hz

        # Fiber A: send one batch (24 samples), exceeds warmup
        m_a = make_measurement(
            np.ones((24, 10)), fiber_id="fiber_a", sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ
        )
        # First batch for fiber_a: count=0 < 12 → None
        result_a1 = await step.process(m_a)
        assert result_a1 is None

        # Second batch for fiber_a: count=24 >= 12 → processed
        result_a2 = await step.process(m_a)
        assert result_a2 is not None

        # Fiber B: first batch → still in warmup
        m_b = make_measurement(
            np.ones((24, 10)), fiber_id="fiber_b", sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ
        )
        result_b = await step.process(m_b)
        assert result_b is None, "fiber_b warmup should be independent from fiber_a"


class TestCMREdgeCases:
    """Edge cases and error handling."""

    async def test_none_input_returns_none(self):
        step = CommonModeRemoval(warmup_seconds=0.0)
        assert await step.process(None) is None

    async def test_empty_array_returned_unchanged(self):
        step = CommonModeRemoval(warmup_seconds=0.0)
        m = make_measurement(np.array([]))
        result = await step.process(m)
        assert result["values"].size == 0

    async def test_single_channel_2d(self):
        step = CommonModeRemoval(warmup_seconds=0.0, method="median")
        values = np.array([[5.0], [10.0], [15.0]])
        result = await step.process(make_measurement(values))

        # Median of single channel = itself → all zeros
        np.testing.assert_array_equal(result["values"], 0.0)

    async def test_invalid_method_raises(self):
        with pytest.raises(ValueError, match="Invalid method"):
            CommonModeRemoval(method="invalid")

    async def test_does_not_modify_input(self, small_batch):
        step = CommonModeRemoval(warmup_seconds=0.0)
        original = small_batch.copy()
        await step.process(make_measurement(small_batch))

        np.testing.assert_array_equal(small_batch, original)

    async def test_metadata_preserved(self, small_batch):
        step = CommonModeRemoval(warmup_seconds=0.0)
        m = make_measurement(small_batch, fiber_id="carros", sampling_rate_hz=125.0)
        result = await step.process(m)

        assert result["fiber_id"] == "carros"
        assert result["sampling_rate_hz"] == 125.0


class TestCMRDeterminism:
    """Deterministic output."""

    async def test_same_input_twice_identical(self, small_batch):
        step = CommonModeRemoval(warmup_seconds=0.0, method="median")
        r1 = await step.process(make_measurement(small_batch.copy()))
        r2 = await step.process(make_measurement(small_batch.copy()))

        np.testing.assert_array_equal(r1["values"], r2["values"])
