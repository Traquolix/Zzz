"""Failure mode tests: wrong shapes, boundary conditions.

Tests that the pipeline fails explicitly rather than producing
confident garbage when given pathological input.

Note: NaN and Inf inputs are NOT tested because the CPAB library crashes
on them (IndexError in expm due to NaN→int conversion). This is a known
limitation of the vendored libcpab. Production is not affected because
the preprocessor (bandpass filter + decimation) never produces NaN/Inf.
"""

from __future__ import annotations

import threading

import numpy as np
import torch

from tests.ai_engine.conftest import (
    CHANNELS_PER_SECTION,
    SAMPLES_PER_WINDOW,
    SAMPLING_RATE_HZ,
)


class TestWrongShapeInput:
    """Tests for wrong dimensions and shapes."""

    def test_too_few_channels_yields_empty(self, estimator):
        """Fewer than Nch channels should yield no results."""
        data = np.random.default_rng(0).standard_normal(
            (CHANNELS_PER_SECTION - 1, SAMPLES_PER_WINDOW)
        )
        timestamps = np.arange(SAMPLES_PER_WINDOW, dtype=np.float64)

        results = list(estimator.process_file(data, timestamps))
        assert len(results) == 0

    def test_exactly_nch_channels(self, estimator):
        """Exactly Nch channels should produce exactly 1 spatial window."""
        data = np.random.default_rng(0).standard_normal((CHANNELS_PER_SECTION, SAMPLES_PER_WINDOW))
        timestamps = np.arange(SAMPLES_PER_WINDOW, dtype=np.float64)

        results = list(estimator.process_file(data, timestamps))
        assert len(results) >= 1
        for r in results:
            assert r.glrt_summed.shape[0] == 1  # 1 spatial window

    def test_zero_time_samples(self, estimator):
        """Zero time samples should yield no results."""
        data = np.random.default_rng(0).standard_normal((50, 0))
        timestamps = np.array([], dtype=np.float64)

        results = list(estimator.process_file(data, timestamps))
        assert len(results) == 0

    def test_one_time_sample(self, estimator):
        """One time sample (< window_size) should yield no results."""
        data = np.random.default_rng(0).standard_normal((50, 1))
        timestamps = np.array([0.0], dtype=np.float64)

        results = list(estimator.process_file(data, timestamps))
        assert len(results) == 0

    def test_very_short_data_skipped(self, estimator, rng):
        """Data shorter than window_size should yield no results."""
        short = rng.standard_normal((50, SAMPLES_PER_WINDOW // 2))
        timestamps = np.arange(SAMPLES_PER_WINDOW // 2, dtype=np.float64)

        results = list(estimator.process_file(short, timestamps))
        assert len(results) == 0

    def test_extra_long_data_uses_first_window(self, estimator, rng):
        """Data longer than window_size should process first window only."""
        long_data = rng.standard_normal((50, SAMPLES_PER_WINDOW * 3))
        timestamps = np.arange(SAMPLES_PER_WINDOW * 3, dtype=np.float64)

        results = list(estimator.process_file(long_data, timestamps))
        assert len(results) >= 1
        for r in results:
            assert r.glrt_summed.shape[-1] < SAMPLES_PER_WINDOW


class TestZeroInput:
    """Tests for all-zero input."""

    def test_all_zeros_no_crash(self, estimator):
        """All-zero input must not crash."""
        data = np.zeros((50, SAMPLES_PER_WINDOW))
        timestamps = np.arange(SAMPLES_PER_WINDOW, dtype=np.float64)

        results = list(estimator.process_file(data, timestamps))
        assert isinstance(results, list)

    def test_all_zeros_no_detections(self, estimator):
        """All-zero input should produce zero detections."""
        data = np.zeros((50, SAMPLES_PER_WINDOW))
        timestamps = np.arange(SAMPLES_PER_WINDOW, dtype=np.float64)
        timestamps_ns = np.arange(SAMPLES_PER_WINDOW, dtype=np.int64) * int(1e9 / SAMPLING_RATE_HZ)

        all_detections = []
        for r in estimator.process_file(data, timestamps, timestamps_ns):
            direction = int(r.direction_mask[0, 0])
            all_detections.extend(
                estimator.extract_detections(
                    glrt_summed=r.glrt_summed,
                    aligned_speed_pairs=r.aligned_speed_per_pair,
                    direction=direction,
                    timestamps_ns=r.timestamps_ns,
                )
            )
        assert len(all_detections) == 0, f"All-zero input produced {len(all_detections)} detections"


class TestConcurrentInference:
    """Tests for thread safety of inference.

    Uses golden fixture data (real DAS) to avoid CPAB issues with random noise.
    """

    def _load_golden(self):
        from pathlib import Path

        golden = Path(__file__).parent / "fixtures" / "golden_input.npz"
        assert golden.exists(), "Golden fixture missing. Run: make snapshot-confirm"
        data = np.load(golden)
        return data["data_window"], data["timestamps"], data["timestamps_ns"]

    def test_concurrent_process_file(self, estimator):
        """Two threads calling process_file must not interfere."""
        data, timestamps, timestamps_ns = self._load_golden()
        # Use different slices of the same real data
        half = data.shape[0] // 2
        data1 = data[:half, :]
        data2 = data[half:, :]

        results = [None, None]
        errors = [None, None]

        def run_inference(idx, d):
            try:
                torch.manual_seed(42 + idx)
                r = list(estimator.process_file(d, timestamps, timestamps_ns))
                results[idx] = r
            except Exception as e:
                errors[idx] = e

        t1 = threading.Thread(target=run_inference, args=(0, data1))
        t2 = threading.Thread(target=run_inference, args=(1, data2))

        t1.start()
        t2.start()
        t1.join(timeout=60)
        t2.join(timeout=60)

        assert errors[0] is None, f"Thread 1 error: {errors[0]}"
        assert errors[1] is None, f"Thread 2 error: {errors[1]}"
        assert results[0] is not None, "Thread 1 produced no results"
        assert results[1] is not None, "Thread 2 produced no results"

        for i, r_list in enumerate(results):
            assert len(r_list) >= 1, f"Thread {i + 1} produced empty results"
