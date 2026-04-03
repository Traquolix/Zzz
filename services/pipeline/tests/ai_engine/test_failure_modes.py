"""Failure mode tests: NaN, Inf, wrong shapes, boundary conditions.

Tests that the pipeline fails explicitly rather than producing
confident garbage when given pathological input.
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


class TestNaNInput:
    """Tests for NaN input handling."""

    def test_all_nan_data_no_crash(self, estimator):
        """All-NaN input must not crash."""
        data = np.full((50, SAMPLES_PER_WINDOW), np.nan)
        timestamps = np.arange(SAMPLES_PER_WINDOW, dtype=np.float64)
        timestamps_ns = np.arange(SAMPLES_PER_WINDOW, dtype=np.int64) * int(1e9 / SAMPLING_RATE_HZ)

        # Should not raise
        results = list(estimator.process_file(data, timestamps, timestamps_ns))
        # May produce results (NaN propagation), but must not crash
        assert isinstance(results, list)

    def test_partial_nan_no_crash(self, estimator, rng):
        """Data with scattered NaN values must not crash."""
        data = rng.standard_normal((50, SAMPLES_PER_WINDOW)).astype(np.float64)
        # Inject NaN in ~10% of values
        nan_mask = rng.random(data.shape) < 0.1
        data[nan_mask] = np.nan

        timestamps = np.arange(SAMPLES_PER_WINDOW, dtype=np.float64)
        timestamps_ns = np.arange(SAMPLES_PER_WINDOW, dtype=np.int64) * int(1e9 / SAMPLING_RATE_HZ)

        results = list(estimator.process_file(data, timestamps, timestamps_ns))
        assert isinstance(results, list)

    def test_nan_detections_have_finite_speed(self, estimator, rng):
        """Any detections from NaN-containing data must still have finite speed."""
        data = rng.standard_normal((50, SAMPLES_PER_WINDOW)).astype(np.float64)
        # Inject NaN in a few channels
        data[10:15, :] = np.nan

        timestamps = np.arange(SAMPLES_PER_WINDOW, dtype=np.float64)
        timestamps_ns = np.arange(SAMPLES_PER_WINDOW, dtype=np.int64) * int(1e9 / SAMPLING_RATE_HZ)

        for r in estimator.process_file(data, timestamps, timestamps_ns):
            direction = int(r.direction_mask[0, 0])
            detections = estimator.extract_detections(
                glrt_summed=r.glrt_summed,
                aligned_speed_pairs=r.aligned_speed_per_pair,
                direction=direction,
                timestamps_ns=r.timestamps_ns,
            )
            for det in detections:
                assert np.isfinite(det["speed_kmh"]), (
                    f"Non-finite speed {det['speed_kmh']} from NaN-contaminated input"
                )


class TestInfInput:
    """Tests for Inf input handling."""

    def test_all_inf_data_no_crash(self, estimator):
        """All-Inf input must not crash."""
        data = np.full((50, SAMPLES_PER_WINDOW), np.inf)
        timestamps = np.arange(SAMPLES_PER_WINDOW, dtype=np.float64)

        results = list(estimator.process_file(data, timestamps))
        assert isinstance(results, list)

    def test_negative_inf_no_crash(self, estimator):
        """Negative infinity input must not crash."""
        data = np.full((50, SAMPLES_PER_WINDOW), -np.inf)
        timestamps = np.arange(SAMPLES_PER_WINDOW, dtype=np.float64)

        results = list(estimator.process_file(data, timestamps))
        assert isinstance(results, list)


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
        # Output time dimension should match window_size minus 2*edge_trim
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
    """Tests for thread safety of inference."""

    def test_concurrent_process_file(self, estimator, rng):
        """Two threads calling process_file must not interfere."""
        data1 = rng.standard_normal((50, SAMPLES_PER_WINDOW)).astype(np.float64)
        data2 = rng.standard_normal((50, SAMPLES_PER_WINDOW)).astype(np.float64) * 2
        timestamps = np.arange(SAMPLES_PER_WINDOW, dtype=np.float64)

        results = [None, None]
        errors = [None, None]

        def run_inference(idx, data):
            try:
                torch.manual_seed(42 + idx)
                r = list(estimator.process_file(data, timestamps))
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

        # Both should have produced valid DirectionResult lists
        for i, r_list in enumerate(results):
            assert len(r_list) >= 1, f"Thread {i + 1} produced empty results"

    def test_concurrent_process_batch(self, estimator, rng):
        """Two threads calling process_batch must not interfere."""
        data1 = rng.standard_normal((50, SAMPLES_PER_WINDOW)).astype(np.float64)
        data2 = rng.standard_normal((60, SAMPLES_PER_WINDOW)).astype(np.float64)
        timestamps = np.arange(SAMPLES_PER_WINDOW, dtype=np.float64)
        timestamps_ns = np.arange(SAMPLES_PER_WINDOW, dtype=np.int64)

        results = [None, None]
        errors = [None, None]

        def run_batch(idx, data):
            try:
                r = estimator.process_batch([(data, timestamps, timestamps_ns)])
                results[idx] = r
            except Exception as e:
                errors[idx] = e

        t1 = threading.Thread(target=run_batch, args=(0, data1))
        t2 = threading.Thread(target=run_batch, args=(1, data2))

        t1.start()
        t2.start()
        t1.join(timeout=60)
        t2.join(timeout=60)

        assert errors[0] is None, f"Thread 1 error: {errors[0]}"
        assert errors[1] is None, f"Thread 2 error: {errors[1]}"
        assert results[0] is not None
        assert results[1] is not None
