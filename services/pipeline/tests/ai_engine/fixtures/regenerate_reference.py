"""Regenerate golden reference output from existing golden input.

Unlike generate_golden_fixture.py (which requires HDF5 + h5py), this script
only needs the golden_input.npz to exist. It runs inference on the input
and saves the reference output. Use this when:
- The model hasn't changed but you need platform-specific reference values
- You've run generate_golden_fixture.py on one machine and need to
  regenerate the reference on the CI server

Usage:
    cd services/pipeline
    python tests/ai_engine/fixtures/regenerate_reference.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PIPELINE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PIPELINE_ROOT))

import torch  # noqa: E402

torch._dynamo.config.disable = True  # avoid dtype mismatches in compiled CPAB

from ai_engine.model_vehicle.model_T import Args_NN_model_all_channels  # noqa: E402
from ai_engine.model_vehicle.utils import normalize_channel_energy  # noqa: E402
from ai_engine.model_vehicle.vehicle_speed import VehicleSpeedEstimator  # noqa: E402

FIXTURE_DIR = Path(__file__).parent
GOLDEN_INPUT = FIXTURE_DIR / "golden_input.npz"


def main():
    assert GOLDEN_INPUT.exists(), f"Golden input missing: {GOLDEN_INPUT}"

    data = np.load(GOLDEN_INPUT)
    data_window = data["data_window"]
    timestamps = data["timestamps"]
    timestamps_ns = data["timestamps_ns"]
    fs = float(data["fs"])
    gauge = float(data["gauge"])

    window_samples = data_window.shape[1]

    model_args = Args_NN_model_all_channels(
        data_window_length=window_samples,
        gauge=gauge,
        Nch=9,
        N_channels=8,
        fs=fs,
        exp_name="allignment_parameters_3_03_2026_30s_windows",
        version="best",
        bidirectional_rnn=True,
    )

    estimator = VehicleSpeedEstimator(
        model_args=model_args,
        ovr_time=0.25,
        glrt_win=20,
        min_speed=20.0,
        max_speed=120.0,
        corr_threshold=300.0,
        bidirectional_detection=True,
    )

    # Normalization reference
    space_split = estimator._dtan.split_channel_overlap(data_window)
    norm_ref = normalize_channel_energy(space_split[0])

    # Inference
    torch.manual_seed(42)
    results = list(estimator.process_file(data_window, timestamps, timestamps_ns))

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

    import platform

    arch = platform.machine()  # "arm64" or "x86_64"

    np.savez_compressed(
        FIXTURE_DIR / f"golden_reference_{arch}.npz",
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

    np.savez_compressed(
        FIXTURE_DIR / f"golden_normalization_{arch}.npz",
        normalized_first_window=norm_ref,
    )

    print(f"Reference regenerated ({arch}): {n_det} detections")
    if n_det:
        print(f"  Speeds: [{det_speeds.min():.1f}, {det_speeds.max():.1f}] km/h")
        print(f"  Directions: fwd={sum(det_directions == 0)}, rev={sum(det_directions == 1)}")


if __name__ == "__main__":
    main()
