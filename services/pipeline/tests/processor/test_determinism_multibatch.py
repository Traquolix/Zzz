"""Multi-batch determinism test.

Runs 50 batches (~10 seconds of DAS data at 125 Hz) through two fresh
pipeline instances and verifies bitwise-identical output for every batch.
This catches nondeterminism that only manifests after state accumulation
in the bandpass filter or temporal decimation counter.
"""

from __future__ import annotations

import numpy as np

from processor.processing_tools.step_registry import build_pipeline_from_config

from .conftest import (
    ORIGINAL_SAMPLING_RATE_HZ,
    RAW_BATCH_SAMPLES,
    SECTION_DECIMATED_CHANNELS,
    make_measurement,
)

# Pipeline without spatial decimation — input is already section-sized.
# Spatial decimation is stateless (tested elsewhere); the stateful steps
# that matter for multi-batch determinism are bandpass filter (IIR state)
# and temporal decimation (global counter).
STATEFUL_CONFIG = [
    {"step": "scale", "params": {"factor": 213.05}},
    {"step": "common_mode_removal", "params": {"warmup_seconds": 0.0, "method": "median"}},
    {"step": "bandpass_filter", "params": {"low_freq_hz": 0.3, "high_freq_hz": 2.0}},
    {"step": "temporal_decimation", "params": {"factor": 12}},
]

N_BATCHES = 50
N_CHANNELS = SECTION_DECIMATED_CHANNELS  # 516


def _build_chain():
    return build_pipeline_from_config(
        STATEFUL_CONFIG,
        fiber_sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
    )


def _generate_batches(seed: int = 42) -> list[np.ndarray]:
    """Generate N_BATCHES of deterministic synthetic raw data."""
    rng = np.random.default_rng(seed)
    return [
        rng.standard_normal((RAW_BATCH_SAMPLES, N_CHANNELS)).astype(np.float64)
        for _ in range(N_BATCHES)
    ]


def _make_timestamps(batch_idx: int) -> list[int]:
    base = 1_700_000_000_000_000_000
    interval = int(1e9 / ORIGINAL_SAMPLING_RATE_HZ)
    offset = batch_idx * RAW_BATCH_SAMPLES * interval
    return [base + offset + i * interval for i in range(RAW_BATCH_SAMPLES)]


class TestMultiBatchDeterminism:
    """Same 50-batch sequence through two fresh pipelines must match exactly."""

    async def test_50_batches_bitwise_identical(self):
        batches = _generate_batches()
        chain1 = _build_chain()
        chain2 = _build_chain()

        for batch_idx, batch_data in enumerate(batches):
            ts = _make_timestamps(batch_idx)

            m1 = make_measurement(
                batch_data.copy(),
                sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
                timestamps_ns=ts[:],
            )
            m2 = make_measurement(
                batch_data.copy(),
                sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
                timestamps_ns=ts[:],
            )

            r1 = await chain1.process(m1, fiber_id="test", section="s")
            r2 = await chain2.process(m2, fiber_id="test", section="s")

            if r1 is None and r2 is None:
                continue

            assert (r1 is None) == (r2 is None), (
                f"Batch {batch_idx}: one pipeline returned None, the other didn't"
            )

            np.testing.assert_array_equal(
                r1["values"],
                r2["values"],
                err_msg=f"Batch {batch_idx}: outputs differ between two fresh pipelines",
            )

    async def test_filter_state_accumulates_identically(self):
        """After 50 batches, both pipelines' internal filter states must match."""
        batches = _generate_batches(seed=99)
        chain1 = _build_chain()
        chain2 = _build_chain()

        for batch_idx, batch_data in enumerate(batches):
            ts = _make_timestamps(batch_idx)
            m1 = make_measurement(
                batch_data.copy(),
                sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
                timestamps_ns=ts[:],
            )
            m2 = make_measurement(
                batch_data.copy(),
                sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
                timestamps_ns=ts[:],
            )
            await chain1.process(m1, fiber_id="test", section="s")
            await chain2.process(m2, fiber_id="test", section="s")

        # Compare filter states directly
        for step1, step2 in zip(chain1.steps, chain2.steps, strict=True):
            if hasattr(step1, "_fiber_states") and "test" in step1._fiber_states:
                state1 = step1._fiber_states["test"]
                state2 = step2._fiber_states["test"]
                if isinstance(state1, dict) and "state" in state1:
                    np.testing.assert_array_equal(
                        state1["state"],
                        state2["state"],
                        err_msg=f"Filter state differs in step {step1.name}",
                    )

    async def test_output_count_consistent(self):
        """Both pipelines produce the same number of non-None outputs."""
        batches = _generate_batches(seed=77)
        chain1 = _build_chain()
        chain2 = _build_chain()

        count1 = 0
        count2 = 0

        for batch_idx, batch_data in enumerate(batches):
            ts = _make_timestamps(batch_idx)
            m1 = make_measurement(
                batch_data.copy(),
                sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
                timestamps_ns=ts[:],
            )
            m2 = make_measurement(
                batch_data.copy(),
                sampling_rate_hz=ORIGINAL_SAMPLING_RATE_HZ,
                timestamps_ns=ts[:],
            )
            r1 = await chain1.process(m1, fiber_id="test", section="s")
            r2 = await chain2.process(m2, fiber_id="test", section="s")
            if r1 is not None:
                count1 += 1
            if r2 is not None:
                count2 += 1

        assert count1 == count2
        assert count1 > 0, "No batches produced output"
