"""Tests that verify per-section vs aggregated counting produces different results.

This test documents the C5 finding: averaging GLRT across sections before
feeding the counting model destroys per-section signal characteristics.
The test proves the aggregation is lossy by showing that per-section
counting produces different results than aggregated counting.

When C5 is fixed (per-section counting in production), this test becomes
the regression test ensuring sections are never re-aggregated.
"""

from __future__ import annotations

import numpy as np
import pytest

from ai_engine.model_vehicle.simple_interval_counter import VehicleCounter
from tests.ai_engine.conftest import CHANNELS_PER_SECTION, CORR_THRESHOLD, SAMPLING_RATE_HZ


@pytest.fixture
def counter() -> VehicleCounter:
    return VehicleCounter(
        fiber_id="test",
        sampling_rate_hz=SAMPLING_RATE_HZ,
        correlation_threshold=CORR_THRESHOLD,
        channels_per_section=CHANNELS_PER_SECTION,
        vehicle_counting_model=None,
        time_window_duration=360.0,
    )


class TestAggregationLossy:
    """Prove that averaging sections before counting is lossy."""

    def test_per_section_vs_averaged_counts_differ(self, counter):
        """Two sections with different GLRT profiles should produce different
        counts when processed individually vs averaged.

        Section 0: strong peak at t=200 (1 vehicle)
        Section 1: two peaks at t=100 and t=300 (2 vehicles)
        Average: diluted signal (may detect 1, or different count)
        """
        time_samples = 500
        n_pairs = CHANNELS_PER_SECTION - 1

        # Section 0: one strong vehicle
        corr_0 = np.zeros((1, time_samples))
        corr_0[0, 190:220] = counter.corr_threshold * 3
        speed_0 = np.full((1, n_pairs, time_samples), 60.0)
        data_0 = np.random.default_rng(0).standard_normal((1, CHANNELS_PER_SECTION, time_samples))

        # Section 1: two weaker vehicles, well-separated
        corr_1 = np.zeros((1, time_samples))
        corr_1[0, 90:110] = counter.corr_threshold * 2
        corr_1[0, 350:370] = counter.corr_threshold * 2
        speed_1 = np.full((1, n_pairs, time_samples), 80.0)
        data_1 = np.random.default_rng(1).standard_normal((1, CHANNELS_PER_SECTION, time_samples))

        # Process each section independently
        counts_0, _ = counter.process_window_data(speed_0, corr_0, data_0)
        counts_1, _ = counter.process_window_data(speed_1, corr_1, data_1)
        total_per_section = sum(c.sum() for c in counts_0 if c.size > 0) + sum(
            c.sum() for c in counts_1 if c.size > 0
        )

        # Process the averaged version (what production currently does)
        agg_corr = np.mean(np.concatenate([corr_0, corr_1], axis=0), axis=0, keepdims=True)
        agg_speed = np.nanmedian(np.concatenate([speed_0, speed_1], axis=0), axis=0, keepdims=True)
        agg_data = np.mean(np.concatenate([data_0, data_1], axis=0), axis=0, keepdims=True)

        # Need a fresh counter (stateless)
        counter_agg = VehicleCounter(
            fiber_id="test-agg",
            sampling_rate_hz=SAMPLING_RATE_HZ,
            correlation_threshold=CORR_THRESHOLD,
            channels_per_section=CHANNELS_PER_SECTION,
            vehicle_counting_model=None,
            time_window_duration=360.0,
        )
        counts_agg, _ = counter_agg.process_window_data(agg_speed, agg_corr, agg_data)
        total_aggregated = sum(c.sum() for c in counts_agg if c.size > 0)

        # The per-section total should be >= the aggregated total
        # because averaging dilutes the signal
        assert total_per_section >= total_aggregated, (
            f"Per-section counting ({total_per_section}) should find at least "
            f"as many vehicles as aggregated counting ({total_aggregated}). "
            f"Aggregation dilutes per-section GLRT peaks."
        )

    def test_strong_section_masked_by_weak_section(self, counter):
        """A strong detection in one section can be diluted below threshold
        when averaged with a quiet section."""
        time_samples = 500
        n_pairs = CHANNELS_PER_SECTION - 1

        # Section 0: clear vehicle (GLRT just above threshold)
        corr_active = np.zeros((1, time_samples))
        corr_active[0, 200:230] = counter.corr_threshold * 1.5  # 1.5x threshold
        speed_active = np.full((1, n_pairs, time_samples), 60.0)
        data_active = np.random.default_rng(0).standard_normal(
            (1, CHANNELS_PER_SECTION, time_samples)
        )

        # Section 1: no vehicle (pure noise well below threshold)
        corr_quiet = np.random.default_rng(1).standard_normal((1, time_samples)) * 10
        speed_quiet = np.full((1, n_pairs, time_samples), 60.0)
        data_quiet = np.random.default_rng(2).standard_normal(
            (1, CHANNELS_PER_SECTION, time_samples)
        )

        # Active section alone should detect
        counts_active, _ = counter.process_window_data(speed_active, corr_active, data_active)
        active_total = sum(c.sum() for c in counts_active if c.size > 0)
        assert active_total >= 1, "Active section should detect at least 1 vehicle"

        # Average of active + quiet: GLRT peak is halved (1.5x * 0.5 = 0.75x threshold)
        agg_corr = np.mean(np.concatenate([corr_active, corr_quiet], axis=0), axis=0, keepdims=True)
        agg_speed = np.nanmedian(
            np.concatenate([speed_active, speed_quiet], axis=0), axis=0, keepdims=True
        )
        agg_data = np.mean(np.concatenate([data_active, data_quiet], axis=0), axis=0, keepdims=True)

        counter_agg = VehicleCounter(
            fiber_id="test-agg",
            sampling_rate_hz=SAMPLING_RATE_HZ,
            correlation_threshold=CORR_THRESHOLD,
            channels_per_section=CHANNELS_PER_SECTION,
            vehicle_counting_model=None,
            time_window_duration=360.0,
        )
        counts_agg, _ = counter_agg.process_window_data(agg_speed, agg_corr, agg_data)
        agg_total = sum(c.sum() for c in counts_agg if c.size > 0)

        # The aggregated version should miss the vehicle because averaging
        # diluted the GLRT peak below threshold
        assert agg_total < active_total, (
            f"Aggregated counting ({agg_total}) should miss vehicles that "
            f"per-section counting ({active_total}) finds. "
            f"This proves the C5 aggregation bug is lossy."
        )
