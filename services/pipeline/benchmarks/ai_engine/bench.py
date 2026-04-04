"""AI Engine inference benchmarks.

Times each pipeline stage independently using the golden fixture data.
Results are compared against a committed baseline to detect regressions.

Usage:
    make bench              # Run benchmarks, compare to baseline
    make bench-save         # Save current results as new baseline

Runs 2 warmup iterations (discarded) then 10 measured iterations per stage.
Reports median and p95. Comparison uses median-to-median delta.
"""

from __future__ import annotations

import json
import platform
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import torch

warnings.filterwarnings("ignore")

# Ensure pipeline root is on sys.path
_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PIPELINE_ROOT))

from ai_engine.message_utils import ProcessingContext, create_detection_messages  # noqa: E402
from ai_engine.model_vehicle.model_T import Args_NN_model_all_channels  # noqa: E402
from ai_engine.model_vehicle.utils import (  # noqa: E402
    correlation_threshold,
    normalize_channel_energy,
)
from ai_engine.model_vehicle.vehicle_speed import VehicleSpeedEstimator  # noqa: E402

FIXTURE_DIR = _PIPELINE_ROOT / "tests" / "ai_engine" / "fixtures"
BASELINE_PATH = Path(__file__).parent / "baselines" / "baseline.json"

# Production config
SAMPLING_RATE_HZ = 10.4167
CHANNELS_PER_SECTION = 9
GAUGE_METERS = 15.3846
GLRT_WINDOW = 20
CORR_THRESHOLD = 300.0

WARMUP = 2
ITERATIONS = 10


def _percentile(values: list[float], p: float) -> float:
    s = sorted(values)
    idx = int(len(s) * p / 100)
    return s[min(idx, len(s) - 1)]


def _median(values: list[float]) -> float:
    return _percentile(values, 50)


def _p95(values: list[float]) -> float:
    return _percentile(values, 95)


def _time_fn(fn, warmup: int = WARMUP, iterations: int = ITERATIONS) -> list[float]:
    """Time a function with warmup, return list of durations in milliseconds."""
    for _ in range(warmup):
        fn()

    times = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        fn()
        elapsed_ms = (time.perf_counter_ns() - start) / 1e6
        times.append(elapsed_ms)
    return times


def load_golden_data() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load golden fixture input data."""
    golden_input = FIXTURE_DIR / "golden_input.npz"
    if not golden_input.exists():
        print(f"ERROR: Golden fixture not found: {golden_input}")
        print("Run: make snapshot-confirm")
        sys.exit(1)

    data = np.load(golden_input)
    return data["data_window"], data["timestamps"], data["timestamps_ns"]


def build_estimator(window_samples: int) -> VehicleSpeedEstimator:
    """Build a VehicleSpeedEstimator matching production config."""
    model_args = Args_NN_model_all_channels(
        data_window_length=window_samples,
        gauge=GAUGE_METERS,
        Nch=CHANNELS_PER_SECTION,
        N_channels=CHANNELS_PER_SECTION - 1,
        fs=SAMPLING_RATE_HZ,
        exp_name="allignment_parameters_3_03_2026_30s_windows",
        version="best",
        bidirectional_rnn=True,
    )
    return VehicleSpeedEstimator(
        model_args=model_args,
        ovr_time=0.25,
        glrt_win=GLRT_WINDOW,
        min_speed=20.0,
        max_speed=120.0,
        corr_threshold=CORR_THRESHOLD,
        bidirectional_detection=True,
    )


def run_benchmarks() -> dict:
    """Run all benchmarks, return results dict."""
    print("Loading golden fixture data...")
    data_window, timestamps, timestamps_ns = load_golden_data()
    window_samples = data_window.shape[1]

    print("Building estimator (model load)...")
    estimator = build_estimator(window_samples)
    dtan = estimator._dtan
    glrt_detector = estimator._glrt
    speed_filter = estimator._speed_filter

    # Prepare intermediate data for stage benchmarks
    space_split = dtan.split_channel_overlap(data_window)
    n_windows = space_split.shape[0]

    space_normalized = space_split.copy()
    for i in range(n_windows):
        space_normalized[i] = normalize_channel_energy(space_normalized[i])

    torch.manual_seed(42)
    thetas, grid_t = dtan.predict_theta(space_normalized)
    align_idx = (CHANNELS_PER_SECTION - 1) // 2

    aligned = dtan.align_window(space_normalized, thetas, CHANNELS_PER_SECTION, align_idx)
    all_speed = dtan.comp_speed(grid_t)

    glrt_per_pair = glrt_detector.apply_glrt(aligned).detach().cpu().numpy()
    binary_filter = correlation_threshold(glrt_per_pair, corr_threshold=CORR_THRESHOLD)

    results = {}

    # --- Stage benchmarks ---

    print(f"\nBenchmarking ({WARMUP} warmup + {ITERATIONS} measured iterations per stage)...")
    print(f"  Input: {data_window.shape[0]} channels x {window_samples} samples")
    print(f"  Spatial windows: {n_windows}")
    print()

    # 1. split_channel_overlap
    times = _time_fn(lambda: dtan.split_channel_overlap(data_window))
    results["split_channel_overlap"] = {"median_ms": _median(times), "p95_ms": _p95(times)}

    # 2. normalize_channel_energy (all windows)
    def _bench_normalize():
        for i in range(n_windows):
            normalize_channel_energy(space_split[i])

    times = _time_fn(_bench_normalize)
    results["normalize_energy"] = {"median_ms": _median(times), "p95_ms": _p95(times)}

    # 3. predict_theta
    def _bench_predict():
        torch.manual_seed(42)
        dtan.predict_theta(space_normalized)

    times = _time_fn(_bench_predict)
    results["predict_theta"] = {"median_ms": _median(times), "p95_ms": _p95(times)}

    # 4. align_window (data)
    times = _time_fn(
        lambda: dtan.align_window(space_normalized, thetas, CHANNELS_PER_SECTION, align_idx)
    )
    results["align_window_data"] = {"median_ms": _median(times), "p95_ms": _p95(times)}

    # 5. align_window (speed)
    times = _time_fn(
        lambda: dtan.align_window(all_speed, thetas[:, :-1, :], CHANNELS_PER_SECTION - 1, align_idx)
    )
    results["align_window_speed"] = {"median_ms": _median(times), "p95_ms": _p95(times)}

    # 6. comp_speed
    times = _time_fn(lambda: dtan.comp_speed(grid_t))
    results["comp_speed"] = {"median_ms": _median(times), "p95_ms": _p95(times)}

    # 7. apply_glrt
    times = _time_fn(lambda: glrt_detector.apply_glrt(aligned))
    results["apply_glrt"] = {"median_ms": _median(times), "p95_ms": _p95(times)}

    # 8. filtering_speed
    times = _time_fn(lambda: speed_filter.filtering_speed(glrt_per_pair, binary_filter))
    results["filtering_speed"] = {"median_ms": _median(times), "p95_ms": _p95(times)}

    # --- Postprocess benchmarks ---
    # Run process_file once to get DirectionResult tuples for postprocess timing
    torch.manual_seed(42)
    direction_results = list(estimator.process_file(data_window, timestamps, timestamps_ns))

    min_vehicle_duration_s = 0.3
    classify_threshold_factor = 2.0

    # 9. extract_detections (all directions)
    def _bench_extract():
        dets = []
        for result in direction_results:
            direction = int(result.direction_mask[0, 0])
            dets.extend(
                estimator.extract_detections(
                    glrt_summed=result.glrt_summed,
                    aligned_speed_pairs=result.aligned_speed_per_pair,
                    direction=direction,
                    timestamps_ns=result.timestamps_ns,
                    min_vehicle_duration_s=min_vehicle_duration_s,
                    classify_threshold_factor=classify_threshold_factor,
                    aligned_data=result.aligned_data,
                )
            )
        return dets

    times = _time_fn(_bench_extract)
    results["extract_detections"] = {"median_ms": _median(times), "p95_ms": _p95(times)}

    # Get detections for message creation benchmark
    sample_detections = _bench_extract()
    ctx = ProcessingContext()

    # 10. create_detection_messages
    times = _time_fn(
        lambda: create_detection_messages(
            fiber_id="bench",
            detections=sample_detections,
            ctx=ctx,
            service_name="bench",
        )
    )
    results["create_messages"] = {"median_ms": _median(times), "p95_ms": _p95(times)}

    n_dets = len(sample_detections)
    fwd = sum(1 for d in sample_detections if d["direction"] == 0)
    rev = sum(1 for d in sample_detections if d["direction"] == 1)
    print(f"  Detections: {n_dets} ({fwd} fwd, {rev} rev)")
    print()

    # --- End-to-end benchmarks ---

    # 11. process_file (end-to-end, single section)
    def _bench_process_file():
        torch.manual_seed(42)
        list(estimator.process_file(data_window, timestamps, timestamps_ns))

    times = _time_fn(_bench_process_file)
    results["process_file_e2e"] = {"median_ms": _median(times), "p95_ms": _p95(times)}

    # 12. process_batch (end-to-end, 3 sections simulating multi-section fiber)
    def _bench_process_batch():
        torch.manual_seed(42)
        estimator.process_batch(
            [
                (data_window, timestamps, timestamps_ns),
                (data_window[:60, :], timestamps, timestamps_ns),
                (data_window[:30, :], timestamps, timestamps_ns),
            ]
        )

    times = _time_fn(_bench_process_batch)
    results["process_batch_e2e"] = {"median_ms": _median(times), "p95_ms": _p95(times)}

    return results


def get_environment() -> dict:
    """Capture environment info for baseline reproducibility."""
    return {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cuda": torch.cuda.is_available(),
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


def print_results(results: dict, baseline: dict | None = None) -> bool:
    """Print results table with optional baseline comparison. Returns True if no regression."""
    header = f"{'Stage':<28} {'Median':>10} {'p95':>10}"
    if baseline:
        header += f" {'Baseline':>10} {'Delta':>10} {'Status':>6}"
    print(header)
    print("─" * len(header))

    has_regression = False

    for stage, timing in results.items():
        median = timing["median_ms"]
        p95 = timing["p95_ms"]
        line = f"{stage:<28} {median:>8.1f}ms {p95:>8.1f}ms"

        if baseline and stage in baseline.get("results", {}):
            base_median = baseline["results"][stage]["median_ms"]
            delta_pct = (median - base_median) / base_median * 100

            if delta_pct > 20:
                status = "✗ SLOW"
                has_regression = True
            elif delta_pct < -5:
                status = "✓ FAST"
            else:
                status = "≈"

            line += f" {base_median:>8.1f}ms {delta_pct:>+8.1f}% {status:>6}"

        print(line)

    return not has_regression


def save_baseline(results: dict) -> None:
    """Save current results as the new baseline."""
    baseline = {
        "environment": get_environment(),
        "results": results,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(baseline, indent=2) + "\n")
    print(f"\nBaseline saved: {BASELINE_PATH}")


def load_baseline() -> dict | None:
    """Load existing baseline, or None if not found."""
    if not BASELINE_PATH.exists():
        return None
    return json.loads(BASELINE_PATH.read_text())


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AI Engine inference benchmarks")
    parser.add_argument("--save", action="store_true", help="Save results as new baseline")
    args = parser.parse_args()

    print("=" * 70)
    print("AI Engine Benchmark")
    print("=" * 70)

    env = get_environment()
    print(f"  Python: {env['python']}")
    print(f"  Torch:  {env['torch']}")
    print(f"  CUDA:   {env['cuda_device'] or 'CPU only'}")
    print()

    results = run_benchmarks()

    print()
    baseline = load_baseline()

    if baseline and not args.save:
        base_env = baseline.get("environment", {})
        if base_env.get("cuda") != env["cuda"]:
            print(
                f"WARNING: Baseline recorded with cuda={base_env.get('cuda')}, "
                f"current cuda={env['cuda']}. Absolute numbers not comparable.\n"
            )

    ok = print_results(results, baseline if not args.save else None)

    if args.save:
        save_baseline(results)
    else:
        print()
        if baseline is None:
            print("No baseline found. Run with --save to create one.")
        elif ok:
            print("No regressions detected.")
        else:
            print("REGRESSION DETECTED. Investigate before merging.")

    # Sum up the stage times
    total = sum(r["median_ms"] for r in results.values() if "e2e" not in r)
    e2e = results.get("process_file_e2e", {}).get("median_ms", 0)
    print(f"\nStage total: {total:.0f}ms | End-to-end: {e2e:.0f}ms")
    overhead = e2e - total
    if total > 0:
        print(
            f"Overhead (buffer mgmt, object creation): {overhead:.0f}ms ({overhead / e2e * 100:.0f}%)"
        )


if __name__ == "__main__":
    main()
