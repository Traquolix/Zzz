"""Golden snapshot tests for the processor preprocessing pipeline.

Runs real HDF5 data through the production ProcessingChain and compares
output to a saved reference. If output changes (due to filter coefficient
changes, step reordering bugs, numerical regressions), the test fails.

Unlike the AI engine golden tests which use an inline reimplementation of
preprocessing, these tests exercise the actual production code path:
ProcessingChain, ProcessingStep subclasses, step_registry, and all
stateful components (filter state, decimation counters, CMR warmup).

To regenerate after an intentional change:
    cd services/pipeline
    python tests/processor/fixtures/generate_golden_processor.py
    git add tests/processor/fixtures/golden_processor_*.npz
    git commit -m 'test: update processor golden snapshots'
"""

from __future__ import annotations

import logging
import platform
from pathlib import Path

import numpy as np
import pytest

from processor.processing_tools.step_registry import build_pipeline_from_config

logger = logging.getLogger(__name__)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
_ARCH = platform.machine()
GOLDEN_REF = FIXTURE_DIR / f"golden_processor_{_ARCH}.npz"

HDF5_DATA_PATH = (
    Path(__file__).resolve().parents[4] / "tools" / "pipeline" / "experiments" / "test_data"
)

_SNAPSHOT_HELP = f"""
PROCESSOR SNAPSHOT MISMATCH (platform: {_ARCH})

  This test fails when processor preprocessing output changes. Expected after:
    - Processing step changes (scale, CMR, bandpass, decimation)
    - Step ordering changes
    - Filter coefficient or config parameter changes

  To accept the new baseline:
    cd services/pipeline
    python tests/processor/fixtures/generate_golden_processor.py

  Then commit the updated .npz file.
"""

# Production config
PIPELINE_CONFIG = [
    {"step": "scale", "params": {"factor": 213.05}},
    {"step": "common_mode_removal", "params": {"warmup_seconds": 5.0, "method": "median"}},
    {"step": "bandpass_filter", "params": {"low_freq_hz": 0.3, "high_freq_hz": 2.0}},
    {"step": "temporal_decimation", "params": {"factor": 12}},
    {"step": "spatial_decimation", "params": {"factor": 3}},
]
ORIGINAL_FS = 125.0
SECTION_CHANNELS = (1200, 2748)
BATCH_SIZE = 24
HDF5_START = "082106"
HDF5_END = "082136"


def _hdf5_available() -> bool:
    return HDF5_DATA_PATH.exists() and any(HDF5_DATA_PATH.glob("*.hdf5"))


def _require_hdf5():
    if not _hdf5_available():
        pytest.skip(f"HDF5 test data not found at {HDF5_DATA_PATH}")


def _require_golden():
    if not GOLDEN_REF.exists():
        pytest.skip(
            f"Golden reference not found: {GOLDEN_REF}\n"
            f"Generate with: python tests/processor/fixtures/generate_golden_processor.py"
        )


@pytest.fixture(scope="module")
def golden_ref():
    _require_golden()
    return np.load(GOLDEN_REF)


@pytest.fixture(scope="module")
def pipeline_output():
    """Run production pipeline on HDF5 data, return list of output arrays."""
    import asyncio

    _require_hdf5()

    import h5py

    files = sorted(HDF5_DATA_PATH.glob("*.hdf5"))
    files = [f for f in files if HDF5_START <= f.stem <= HDF5_END]
    if not files:
        pytest.skip("No HDF5 files in expected time range")

    raw_chunks = []
    for fpath in files:
        with h5py.File(fpath, "r") as f:
            raw_chunks.append(f["data"][:].astype(np.float64))
    raw_data = np.concatenate(raw_chunks, axis=0)

    chain = build_pipeline_from_config(
        PIPELINE_CONFIG,
        fiber_sampling_rate_hz=ORIGINAL_FS,
        section_channels=SECTION_CHANNELS,
    )

    async def _run():
        outputs = []
        n_batches = raw_data.shape[0] // BATCH_SIZE
        base_ts = 1_700_000_000_000_000_000
        sample_interval_ns = int(1e9 / ORIGINAL_FS)

        for i in range(n_batches):
            batch = raw_data[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
            ts = [base_ts + (i * BATCH_SIZE + j) * sample_interval_ns for j in range(BATCH_SIZE)]

            measurement = {
                "fiber_id": "carros",
                "values": batch,
                "sampling_rate_hz": ORIGINAL_FS,
                "channel_start": 0,
                "timestamps_ns": ts,
            }
            result = await chain.process(measurement, fiber_id="carros", section="202Bis")
            if result is not None:
                outputs.append(result["values"])

        return outputs

    return asyncio.get_event_loop().run_until_complete(_run())


class TestGoldenProcessorSnapshot:
    """Compare current pipeline output to saved golden reference."""

    def test_output_shape_matches(self, pipeline_output, golden_ref):
        actual = np.concatenate(pipeline_output, axis=0)
        expected = golden_ref["values"]

        if actual.shape != expected.shape:
            pytest.fail(
                f"Output shape changed: expected {expected.shape}, got {actual.shape}\n"
                f"{_SNAPSHOT_HELP}"
            )

    def test_output_values_match(self, pipeline_output, golden_ref):
        actual = np.concatenate(pipeline_output, axis=0)
        expected = golden_ref["values"]

        if actual.shape != expected.shape:
            pytest.skip("Shape mismatch — see test_output_shape_matches")

        max_abs_diff = np.abs(actual - expected).max()
        # Tolerance: float64 deterministic math should be exact, but allow
        # for minor platform differences in scipy sosfilt
        if max_abs_diff > 1e-10:
            rel_diff = np.abs(actual - expected) / (np.abs(expected) + 1e-15)
            max_rel = rel_diff.max()
            pytest.fail(
                f"Output values changed:\n"
                f"  Max absolute diff: {max_abs_diff:.2e}\n"
                f"  Max relative diff: {max_rel:.2e}\n"
                f"{_SNAPSHOT_HELP}"
            )

    def test_batch_count_matches(self, pipeline_output, golden_ref):
        expected_count = int(golden_ref["n_output_batches"])
        actual_count = len(pipeline_output)

        if actual_count != expected_count:
            pytest.fail(
                f"Output batch count changed: expected {expected_count}, got {actual_count}\n"
                f"(This usually means warmup duration or decimation factor changed)\n"
                f"{_SNAPSHOT_HELP}"
            )


class TestGoldenProcessorInvariants:
    """Properties that must hold regardless of golden reference version."""

    def test_all_output_finite(self, pipeline_output):
        for i, batch in enumerate(pipeline_output):
            assert np.all(np.isfinite(batch)), f"Non-finite values in output batch {i}"

    def test_output_dtype_float64(self, pipeline_output):
        for batch in pipeline_output:
            assert batch.dtype == np.float64

    def test_produces_output(self, pipeline_output):
        assert len(pipeline_output) > 0, "Pipeline produced zero output batches from real data"

    def test_consistent_channel_count(self, pipeline_output):
        channel_counts = {batch.shape[1] for batch in pipeline_output}
        assert len(channel_counts) == 1, (
            f"Inconsistent channel counts across batches: {channel_counts}"
        )
