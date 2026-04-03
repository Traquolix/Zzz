"""Integration tests for VehicleSpeedEstimator.

Uses golden fixture data (real DAS) for inference tests to avoid CPAB CUDA
kernel issues with random noise. Boundary conditions and failure modes are
tested in test_failure_modes.py (CPU-only). Detection quality is tested in
test_golden_snapshot.py and test_synthetic_detection.py.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from ai_engine.model_vehicle.vehicle_speed import compute_edge_trim
from tests.ai_engine.conftest import (
    SAMPLES_PER_WINDOW,
    TIME_OVERLAP_RATIO,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
GOLDEN_INPUT = FIXTURE_DIR / "golden_input.npz"


class TestComputeEdgeTrim:
    """Tests for edge trim calculation (pure math, no GPU)."""

    def test_default_config(self):
        trim = compute_edge_trim(SAMPLES_PER_WINDOW, TIME_OVERLAP_RATIO)
        assert trim > 0
        assert trim < SAMPLES_PER_WINDOW // 2

    def test_trim_respects_safety(self):
        trim = compute_edge_trim(100, 0.0, safety=15)
        assert trim >= 15

    def test_trim_scales_with_overlap(self):
        trim_low = compute_edge_trim(100, 0.1)
        trim_high = compute_edge_trim(100, 0.5)
        assert trim_high >= trim_low

    def test_trimmed_window_size(self):
        trim = compute_edge_trim(SAMPLES_PER_WINDOW, TIME_OVERLAP_RATIO)
        trimmed = SAMPLES_PER_WINDOW - 2 * trim
        assert trimmed > 0, f"Trimmed size {trimmed} must be positive"


class TestProcessBatchConsistency:
    """Tests that process_batch and process_file produce equivalent results.

    Uses golden fixture data (real DAS) so the DTAN model receives realistic
    input that works on both CPU and GPU.
    """

    def _load_golden(self):
        if not GOLDEN_INPUT.exists():
            return None
        data = np.load(GOLDEN_INPUT)
        return data["data_window"], data["timestamps"], data["timestamps_ns"]

    def test_batch_matches_single(self, estimator):
        """Batched inference on 1 section must match process_file output."""
        loaded = self._load_golden()
        assert loaded is not None, "Golden fixture missing. Run: make snapshot-confirm"
        data_window, timestamps, timestamps_ns = loaded

        torch.manual_seed(42)
        single_results = list(estimator.process_file(data_window, timestamps, timestamps_ns))

        torch.manual_seed(42)
        batch_results = estimator.process_batch([(data_window, timestamps, timestamps_ns)])

        assert len(batch_results[0]) == len(single_results)
        for single_r, batch_r in zip(single_results, batch_results[0], strict=False):
            np.testing.assert_allclose(
                single_r.glrt_summed, batch_r.glrt_summed, rtol=1e-4, atol=1e-4
            )
            np.testing.assert_allclose(
                single_r.filtered_speed, batch_r.filtered_speed, rtol=1e-4, atol=1e-4
            )
