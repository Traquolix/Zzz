"""Generate golden test fixtures for the processor preprocessing pipeline.

This script runs ONCE to produce the .npz fixture that is committed to the
repo. It requires h5py and the HDF5 test data in
tools/pipeline/experiments/test_data/.

Unlike the AI engine's generate_golden_fixture.py (which reimplements the
preprocessing inline), this script runs raw DAS data through the actual
production ProcessingChain — the same code path that runs in production.
This closes the gap between "the math is correct" and "the production
code that implements the math is correct."

Usage:
    cd services/pipeline
    python tests/processor/fixtures/generate_golden_processor.py

Or via Makefile:
    make snapshot-processor
"""

from __future__ import annotations

import asyncio
import platform
import sys
from pathlib import Path

import numpy as np

# Ensure pipeline root is on sys.path
PIPELINE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PIPELINE_ROOT))

from processor.processing_tools.step_registry import build_pipeline_from_config  # noqa: E402

FIXTURE_DIR = Path(__file__).parent
_ARCH = platform.machine()

# Production config matching fibers.yaml carros section
CONFIG = {
    "hdf5_data_path": str(
        PIPELINE_ROOT.parent.parent / "tools" / "pipeline" / "experiments" / "test_data"
    ),
    "start_time": "082106",
    "end_time": "082136",  # 3 files = ~30s of data
    "section_channel_start": 1200,
    "section_channel_end": 2748,
    "original_fs": 125.0,
    "batch_size": 24,  # samples per raw Kafka message
    "pipeline": [
        {"step": "scale", "params": {"factor": 213.05}},
        {"step": "common_mode_removal", "params": {"warmup_seconds": 5.0, "method": "median"}},
        {"step": "bandpass_filter", "params": {"low_freq_hz": 0.3, "high_freq_hz": 2.0}},
        {"step": "temporal_decimation", "params": {"factor": 12}},
        {"step": "spatial_decimation", "params": {"factor": 3}},
    ],
}


async def run_production_pipeline() -> tuple[list[np.ndarray], int, int]:
    """Load HDF5 data, batch it, and run through production ProcessingChain.

    Returns:
        (outputs, total_batches, warmup_dropped): list of output value arrays,
        total batches processed, and count of batches dropped by warmup.
    """
    import h5py

    data_path = Path(CONFIG["hdf5_data_path"])
    files = sorted(data_path.glob("*.hdf5"))
    files = [f for f in files if CONFIG["start_time"] <= f.stem <= CONFIG["end_time"]]

    if not files:
        raise FileNotFoundError(f"No HDF5 files in {data_path}")

    # Load and concatenate raw data
    raw_chunks = []
    for fpath in files:
        with h5py.File(fpath, "r") as f:
            raw_chunks.append(f["data"][:].astype(np.float64))
    raw_data = np.concatenate(raw_chunks, axis=0)
    print(f"  Raw data: {raw_data.shape} ({raw_data.shape[0]} samples x {raw_data.shape[1]} ch)")

    # Build production pipeline
    chain = build_pipeline_from_config(
        CONFIG["pipeline"],
        fiber_sampling_rate_hz=CONFIG["original_fs"],
        section_channels=(CONFIG["section_channel_start"], CONFIG["section_channel_end"]),
    )

    # Process in batches (mimicking Kafka message boundaries)
    batch_size = CONFIG["batch_size"]
    n_total_samples = raw_data.shape[0]
    n_batches = n_total_samples // batch_size
    outputs = []
    warmup_dropped = 0
    base_ts = 1_700_000_000_000_000_000
    sample_interval_ns = int(1e9 / CONFIG["original_fs"])

    for i in range(n_batches):
        batch = raw_data[i * batch_size : (i + 1) * batch_size]
        ts = [base_ts + (i * batch_size + j) * sample_interval_ns for j in range(batch_size)]

        measurement = {
            "fiber_id": "carros",
            "values": batch,
            "sampling_rate_hz": CONFIG["original_fs"],
            "channel_start": 0,
            "timestamps_ns": ts,
        }

        result = await chain.process(measurement, fiber_id="carros", section="202Bis")

        if result is None:
            warmup_dropped += 1
        else:
            outputs.append(result["values"])

    return outputs, n_batches, warmup_dropped


async def main():
    print("=" * 70)
    print("Generating Processor Golden Test Fixtures")
    print("=" * 70)

    print("\n[1/2] Running production pipeline on HDF5 data...")
    outputs, n_batches, warmup_dropped = await run_production_pipeline()

    if not outputs:
        print("ERROR: No output produced. Check warmup settings.")
        sys.exit(1)

    # Stack all outputs into a single array
    all_values = np.concatenate(outputs, axis=0)
    print(f"  Batches: {n_batches} total, {warmup_dropped} dropped (warmup)")
    print(f"  Output: {all_values.shape} ({all_values.dtype})")
    print(f"  Range: [{all_values.min():.4f}, {all_values.max():.4f}]")

    print(f"\n[2/2] Saving golden reference ({_ARCH})...")
    out_path = FIXTURE_DIR / f"golden_processor_{_ARCH}.npz"
    np.savez_compressed(
        out_path,
        values=all_values,
        n_batches=np.int32(n_batches),
        n_warmup_dropped=np.int32(warmup_dropped),
        n_output_batches=np.int32(len(outputs)),
        # Save individual batch shapes for batch-level comparison
        batch_shapes=np.array([o.shape for o in outputs]),
    )

    print(f"  Saved: {out_path}")
    print(f"  Size: {out_path.stat().st_size / 1024:.0f} KB")

    print("\n" + "=" * 70)
    print("Done. Commit the .npz file:")
    print(f"  git add {out_path}")
    print("  git commit -m 'test: update processor golden snapshots'")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
