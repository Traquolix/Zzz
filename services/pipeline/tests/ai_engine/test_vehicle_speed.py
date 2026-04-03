"""Integration tests for VehicleSpeedEstimator.

Tests process_file (single section) and process_batch (multi-section
batched GPU pass). Boundary conditions and failure modes are tested in
test_failure_modes.py. Detection quality is tested in test_golden_snapshot.py
and test_synthetic_detection.py.
"""

from __future__ import annotations

import numpy as np

from ai_engine.model_vehicle.vehicle_speed import compute_edge_trim
from tests.ai_engine.conftest import (
    SAMPLES_PER_WINDOW,
    TIME_OVERLAP_RATIO,
)


class TestComputeEdgeTrim:
    """Tests for edge trim calculation."""

    def test_default_config(self):
        """Edge trim with default production config."""
        trim = compute_edge_trim(SAMPLES_PER_WINDOW, TIME_OVERLAP_RATIO)
        assert trim > 0
        assert trim < SAMPLES_PER_WINDOW // 2

    def test_trim_respects_safety(self):
        """Trim must be at least the safety margin."""
        trim = compute_edge_trim(100, 0.0, safety=15)
        assert trim >= 15

    def test_trim_scales_with_overlap(self):
        """Higher overlap ratio -> more trim."""
        trim_low = compute_edge_trim(100, 0.1)
        trim_high = compute_edge_trim(100, 0.5)
        assert trim_high >= trim_low

    def test_trimmed_window_size(self):
        """Trimmed time = window_size - 2 * trim must be positive."""
        trim = compute_edge_trim(SAMPLES_PER_WINDOW, TIME_OVERLAP_RATIO)
        trimmed = SAMPLES_PER_WINDOW - 2 * trim
        assert trimmed > 0, f"Trimmed size {trimmed} must be positive"


class TestProcessFile:
    """Tests for single-section inference via process_file."""

    def test_bidirectional_yields_two(
        self, estimator, synthetic_section_data, synthetic_timestamps, synthetic_timestamps_ns
    ):
        """With bidirectional=True, should yield 2 DirectionResults (fwd + rev)."""
        results = list(
            estimator.process_file(
                synthetic_section_data, synthetic_timestamps, synthetic_timestamps_ns
            )
        )
        assert len(results) == 2
        assert results[0].direction_mask[0, 0] == 0  # forward
        assert results[1].direction_mask[0, 0] == 1  # reverse

    def test_trimmed_time_consistent(
        self, estimator, synthetic_section_data, synthetic_timestamps, synthetic_timestamps_ns
    ):
        """All output arrays in a DirectionResult must have same trimmed time dimension."""
        results = list(
            estimator.process_file(
                synthetic_section_data, synthetic_timestamps, synthetic_timestamps_ns
            )
        )
        for r in results:
            trimmed_time = r.glrt_summed.shape[-1]
            assert r.filtered_speed.shape[-1] == trimmed_time
            assert r.aligned_data.shape[-1] == trimmed_time
            assert r.timestamps.shape[0] == trimmed_time
            assert r.direction_mask.shape[-1] == trimmed_time
            assert r.aligned_speed_per_pair.shape[-1] == trimmed_time
            if r.timestamps_ns is not None:
                assert r.timestamps_ns.shape[0] == trimmed_time

    def test_timestamps_are_trimmed_subset(
        self, estimator, synthetic_section_data, synthetic_timestamps, synthetic_timestamps_ns
    ):
        """Output timestamps must be a contiguous slice of the input."""
        results = list(
            estimator.process_file(
                synthetic_section_data, synthetic_timestamps, synthetic_timestamps_ns
            )
        )
        for r in results:
            assert r.timestamps[0] >= synthetic_timestamps[0]
            assert r.timestamps[-1] <= synthetic_timestamps[-1]

    def test_deterministic(
        self, estimator, synthetic_section_data, synthetic_timestamps, synthetic_timestamps_ns
    ):
        """Same input must produce identical output arrays."""
        import torch

        torch.manual_seed(42)
        r1 = list(
            estimator.process_file(
                synthetic_section_data, synthetic_timestamps, synthetic_timestamps_ns
            )
        )
        torch.manual_seed(42)
        r2 = list(
            estimator.process_file(
                synthetic_section_data, synthetic_timestamps, synthetic_timestamps_ns
            )
        )
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2, strict=False):
            np.testing.assert_array_equal(a.glrt_summed, b.glrt_summed)
            np.testing.assert_array_equal(a.filtered_speed, b.filtered_speed)


class TestProcessBatch:
    """Tests for multi-section batched inference via process_batch."""

    def test_batch_matches_single(
        self, estimator, synthetic_section_data, synthetic_timestamps, synthetic_timestamps_ns
    ):
        """Batched inference on 1 section must match process_file output."""
        import torch

        torch.manual_seed(42)
        single_results = list(
            estimator.process_file(
                synthetic_section_data, synthetic_timestamps, synthetic_timestamps_ns
            )
        )

        torch.manual_seed(42)
        batch_results = estimator.process_batch(
            [
                (synthetic_section_data, synthetic_timestamps, synthetic_timestamps_ns),
            ]
        )

        assert len(batch_results[0]) == len(single_results)
        for single_r, batch_r in zip(single_results, batch_results[0], strict=False):
            np.testing.assert_allclose(
                single_r.glrt_summed, batch_r.glrt_summed, rtol=1e-4, atol=1e-4
            )
            np.testing.assert_allclose(
                single_r.filtered_speed, batch_r.filtered_speed, rtol=1e-4, atol=1e-4
            )

    def test_multi_section_batch(
        self,
        estimator,
        synthetic_section_data,
        synthetic_wide_data,
        synthetic_timestamps,
        synthetic_timestamps_ns,
    ):
        """Batching multiple sections must return results for each."""
        sections = [
            (synthetic_section_data, synthetic_timestamps, synthetic_timestamps_ns),
            (synthetic_wide_data, synthetic_timestamps, synthetic_timestamps_ns),
        ]
        results = estimator.process_batch(sections)
        assert len(results) == 2
        assert len(results[0]) >= 1
        assert len(results[1]) >= 1
