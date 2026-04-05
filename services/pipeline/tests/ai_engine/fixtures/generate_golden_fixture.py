"""Generate golden test fixtures from real DAS HDF5 data.

This script runs ONCE locally to produce the .npz fixture files that are
committed to the repo. It requires h5py and the HDF5 test data in
tools/pipeline/experiments/test_data/.

The generated fixtures capture:
1. A post-preprocessing input array (what the AI engine actually receives)
2. The reference inference output (detections, GLRT, speeds)
3. Preprocessing intermediate: normalized channel energy output

Usage:
    cd services/pipeline
    python tests/ai_engine/fixtures/generate_golden_fixture.py

Or via Makefile:
    make snapshot-confirm
"""

from __future__ import annotations

import importlib.util
import platform
import sys
from pathlib import Path

import numpy as np

# Ensure services/pipeline is on sys.path
PIPELINE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PIPELINE_ROOT))

import torch  # noqa: E402

# Match test execution settings for bit-identical results:
# - Disable torch.compile (conftest.py also disables dynamo)
# - Disable cudnn.benchmark (prevents non-deterministic algorithm selection)
torch._dynamo.config.disable = True
torch.backends.cudnn.benchmark = False

from ai_engine.model_vehicle.model_T import Args_NN_model_all_channels  # noqa: E402
from ai_engine.model_vehicle.utils import normalize_channel_energy  # noqa: E402
from ai_engine.model_vehicle.vehicle_speed import VehicleSpeedEstimator  # noqa: E402

# Load bandpass filter from processor without pulling full processor __init__
_bp_spec = importlib.util.spec_from_file_location(
    "bandpass", PIPELINE_ROOT / "processor" / "processing_tools" / "math" / "bandpass.py"
)
_bp_mod = importlib.util.module_from_spec(_bp_spec)
_bp_spec.loader.exec_module(_bp_mod)
VectorizedBiquadFilter = _bp_mod.VectorizedBiquadFilter

FIXTURE_DIR = Path(__file__).parent
_ARCH = platform.machine()  # "arm64" or "x86_64"

# Config matching production (fibers.yaml carros default section)
CONFIG = {
    "hdf5_data_path": str(
        PIPELINE_ROOT.parent.parent / "tools" / "pipeline" / "experiments" / "test_data"
    ),
    "start_time": "082106",
    "end_time": "082226",
    "section_channel_start": 1200,
    "section_channel_end": 2748,
    "filter_freqs": [0.3, 2.0],
    "downsample_factor": 12,
    "gauge_raw": 5.1282051282,
    "original_fs": 125,
    "spatial_decimation": 3,
    "Nch": 9,
    "window_seconds": 30,
    "exp_name": "allignment_parameters_3_03_2026_30s_windows",
    "version": "best",
    "corr_threshold": 300.0,
    "glrt_window": 20,
    "min_speed": 20,
    "max_speed": 120,
    "time_overlap_ratio": 0.25,
    "bidirectional": True,
    "scale_factor": 213.05,
}


def load_and_preprocess() -> tuple[np.ndarray, float, float]:
    """Load HDF5 data and preprocess exactly as the production processor does.

    Pipeline matches fibers.yaml defaults (reordered: spatial first):
    1. Spatial decimation (channel selection + stride)
    2. Scale (x 213.05)
    3. Common mode removal (spatial median subtraction)
    4. Bandpass filter (0.3-2.0 Hz, order 4)
    5. Temporal decimation (x 12)
    """
    import h5py

    data_path = Path(CONFIG["hdf5_data_path"])
    files = sorted(data_path.glob("*.hdf5"))
    files = [f for f in files if CONFIG["start_time"] <= f.stem <= CONFIG["end_time"]]

    if not files:
        raise FileNotFoundError(
            f"No HDF5 files found in {data_path} between "
            f"{CONFIG['start_time']} and {CONFIG['end_time']}"
        )

    section_ch_start = CONFIG["section_channel_start"]
    section_ch_end = CONFIG["section_channel_end"]
    ds_factor = CONFIG["downsample_factor"]
    spatial_stride = int(CONFIG["spatial_decimation"])
    scale_factor = CONFIG["scale_factor"]

    # After spatial decimation, this many channels remain
    n_section_raw = section_ch_end - section_ch_start
    n_decimated_channels = len(range(0, n_section_raw, spatial_stride))

    # Bandpass filter operates on spatially-decimated channels
    bp_filter = VectorizedBiquadFilter(
        low_freq=CONFIG["filter_freqs"][0],
        high_freq=CONFIG["filter_freqs"][1],
        sampling_rate=CONFIG["original_fs"],
    )
    filter_state = bp_filter.create_state(n_decimated_channels)
    decim_counter = 0
    collected = []

    for fpath in files:
        with h5py.File(fpath, "r") as f:
            raw = f["data"][:]
        n_time = min(raw.shape[0], 1250)
        for t in range(n_time):
            # 1. Spatial decimation (channel selection + stride)
            sample = raw[t, section_ch_start:section_ch_end].astype(np.float64)
            sample = sample[::spatial_stride]

            # 2. Scale
            sample = sample * scale_factor

            # 3. Common mode removal (spatial median subtraction)
            sample = sample - np.median(sample)

            # 4. Bandpass filter
            filtered = bp_filter.filter(sample, filter_state)

            # 5. Temporal decimation
            decim_counter += 1
            if decim_counter % ds_factor != 0:
                continue
            collected.append(filtered)

    data = np.array(collected, dtype=np.float32).T
    fs = CONFIG["original_fs"] / ds_factor
    gauge = CONFIG["gauge_raw"] * spatial_stride
    return data, fs, gauge


def generate_golden_input(data: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Extract one 30s window matching production config."""
    window_samples = int(CONFIG["window_seconds"] * fs)
    data_window = data[:, :window_samples].copy()
    timestamps = np.arange(window_samples, dtype=np.float64) / fs
    timestamps_ns = (timestamps * 1e9).astype(np.int64) + 1_700_000_000_000_000_000
    return data_window, timestamps, timestamps_ns


def generate_normalization_reference(data_window: np.ndarray, dtan) -> np.ndarray:
    """Run split_channel_overlap + normalize_channel_energy, save first window output."""
    space_split = dtan.split_channel_overlap(data_window)
    normalized_first_window = normalize_channel_energy(space_split[0])
    return normalized_first_window


def run_inference_and_save(
    data_window: np.ndarray,
    timestamps: np.ndarray,
    timestamps_ns: np.ndarray,
    fs: float,
    gauge: float,
):
    """Run full inference pipeline on the golden input and save all artifacts."""
    window_samples = data_window.shape[1]

    model_args = Args_NN_model_all_channels(
        data_window_length=window_samples,
        gauge=gauge,
        Nch=CONFIG["Nch"],
        N_channels=CONFIG["Nch"] - 1,
        fs=fs,
        exp_name=CONFIG["exp_name"],
        version=CONFIG["version"],
        bidirectional_rnn=True,
    )

    estimator = VehicleSpeedEstimator(
        model_args=model_args,
        ovr_time=CONFIG["time_overlap_ratio"],
        glrt_win=CONFIG["glrt_window"],
        min_speed=CONFIG["min_speed"],
        max_speed=CONFIG["max_speed"],
        corr_threshold=CONFIG["corr_threshold"],
        bidirectional_detection=CONFIG["bidirectional"],
    )

    # Generate normalization reference
    norm_ref = generate_normalization_reference(data_window, estimator._dtan)

    # Run inference (deterministic)
    torch.manual_seed(42)
    results = list(estimator.process_file(data_window, timestamps, timestamps_ns))

    # Extract detections for each direction
    all_detections = []
    result_arrays = {}
    for _i, result in enumerate(results):
        direction = int(result.direction_mask[0, 0])
        dir_key = "fwd" if direction == 0 else "rev"

        result_arrays[f"{dir_key}_glrt_summed"] = result.glrt_summed
        result_arrays[f"{dir_key}_filtered_speed"] = result.filtered_speed
        result_arrays[f"{dir_key}_aligned_speed_per_pair"] = result.aligned_speed_per_pair

        detections = estimator.extract_detections(
            glrt_summed=result.glrt_summed,
            aligned_speed_pairs=result.aligned_speed_per_pair,
            direction=direction,
            timestamps_ns=result.timestamps_ns,
            aligned_data=result.aligned_data,
        )
        all_detections.extend(detections)

    # Serialize detections to arrays for .npz storage
    n_det = len(all_detections)
    det_speeds = (
        np.array([d["speed_kmh"] for d in all_detections], dtype=np.float64)
        if n_det
        else np.array([], dtype=np.float64)
    )
    det_directions = (
        np.array([d["direction"] for d in all_detections], dtype=np.int32)
        if n_det
        else np.array([], dtype=np.int32)
    )
    det_glrt_max = (
        np.array([d["glrt_max"] for d in all_detections], dtype=np.float64)
        if n_det
        else np.array([], dtype=np.float64)
    )
    det_vehicle_count = (
        np.array([d["vehicle_count"] for d in all_detections], dtype=np.float64)
        if n_det
        else np.array([], dtype=np.float64)
    )
    det_n_cars = (
        np.array([d["n_cars"] for d in all_detections], dtype=np.float64)
        if n_det
        else np.array([], dtype=np.float64)
    )
    det_n_trucks = (
        np.array([d["n_trucks"] for d in all_detections], dtype=np.float64)
        if n_det
        else np.array([], dtype=np.float64)
    )
    det_section_idx = (
        np.array([d["section_idx"] for d in all_detections], dtype=np.int32)
        if n_det
        else np.array([], dtype=np.int32)
    )
    det_t_mid = (
        np.array([d["_t_mid_sample"] for d in all_detections], dtype=np.int32)
        if n_det
        else np.array([], dtype=np.int32)
    )
    det_strain_peak = (
        np.array([d["strain_peak"] for d in all_detections], dtype=np.float64)
        if n_det
        else np.array([], dtype=np.float64)
    )
    det_strain_rms = (
        np.array([d["strain_rms"] for d in all_detections], dtype=np.float64)
        if n_det
        else np.array([], dtype=np.float64)
    )

    # Save golden input
    np.savez_compressed(
        FIXTURE_DIR / "golden_input.npz",
        data_window=data_window,
        timestamps=timestamps,
        timestamps_ns=timestamps_ns,
        fs=np.float64(fs),
        gauge=np.float64(gauge),
    )

    # Save golden reference output (platform-specific due to float32 accumulation differences)
    np.savez_compressed(
        FIXTURE_DIR / f"golden_reference_{_ARCH}.npz",
        n_detections=np.int32(n_det),
        det_speeds=det_speeds,
        det_directions=det_directions,
        det_glrt_max=det_glrt_max,
        det_vehicle_count=det_vehicle_count,
        det_n_cars=det_n_cars,
        det_n_trucks=det_n_trucks,
        det_section_idx=det_section_idx,
        det_t_mid=det_t_mid,
        det_strain_peak=det_strain_peak,
        det_strain_rms=det_strain_rms,
        **result_arrays,
    )

    # Save normalization reference (platform-specific)
    np.savez_compressed(
        FIXTURE_DIR / f"golden_normalization_{_ARCH}.npz",
        normalized_first_window=norm_ref,
    )

    # Print summary
    print("\nGolden fixture generated:")
    print(f"  Input: {FIXTURE_DIR / 'golden_input.npz'}")
    print(f"    Shape: {data_window.shape} ({data_window.nbytes / 1024:.0f} KB)")
    print(f"    fs={fs:.4f} Hz, gauge={gauge:.4f} m")
    print(f"  Reference: {FIXTURE_DIR / f'golden_reference_{_ARCH}.npz'}")
    print(f"    Detections: {n_det}")
    if n_det:
        print(f"    Speeds: [{det_speeds.min():.1f}, {det_speeds.max():.1f}] km/h")
        print(f"    Directions: fwd={sum(det_directions == 0)}, rev={sum(det_directions == 1)}")
        print(f"    GLRT range: [{det_glrt_max.min():.0f}, {det_glrt_max.max():.0f}]")
    print(f"  Normalization: {FIXTURE_DIR / f'golden_normalization_{_ARCH}.npz'}")
    print(f"    Shape: {norm_ref.shape}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate AI engine golden test fixtures")
    parser.add_argument(
        "--rerun",
        action="store_true",
        help="Re-record reference output from existing golden_input.npz (skips HDF5 loading)",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("Generating AI Engine Golden Test Fixtures")
    print("=" * 70)

    golden_input_path = FIXTURE_DIR / "golden_input.npz"

    if args.rerun:
        if not golden_input_path.exists():
            print(f"ERROR: {golden_input_path} not found. Run without --rerun first.")
            sys.exit(1)
        print("\n[1/1] Re-recording from existing golden_input.npz...")
        data = np.load(golden_input_path)
        data_window = data["data_window"]
        timestamps = data["timestamps"]
        timestamps_ns = data["timestamps_ns"]
        fs = CONFIG["original_fs"] / CONFIG["downsample_factor"]
        gauge = CONFIG["gauge_raw"] * CONFIG["spatial_decimation"]
    else:
        print("\n[1/3] Loading and preprocessing HDF5 data...")
        data, fs, gauge = load_and_preprocess()
        print(f"  Loaded: {data.shape[0]} channels x {data.shape[1]} samples @ {fs:.4f} Hz")

        print("\n[2/3] Extracting 30s golden window...")
        data_window, timestamps, timestamps_ns = generate_golden_input(data, fs)
        print(f"  Window: {data_window.shape}")

    print(f"\n{'[2/2]' if args.rerun else '[3/3]'} Running inference and saving fixtures...")
    run_inference_and_save(data_window, timestamps, timestamps_ns, fs, gauge)

    print("\n" + "=" * 70)
    print("Done. Commit the .npz files in tests/ai_engine/fixtures/")
    print("=" * 70)


if __name__ == "__main__":
    main()
