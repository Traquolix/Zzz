"""
Calibration Generation Script
==============================

Generates per-section GLRT threshold curves and coupling correction factors
for the DAS pipeline. Uses nighttime data (minimal traffic) to establish
noise baselines.

This follows the thesis approach (Section 3.2):
- Threshold determined from nighttime DAS data where only noise is present
- Per-section thresholds adapt to local noise floor
- Coupling correction normalizes signal strength across sections

Usage:
    python generate_calibration.py \\
        --data-dir /path/to/preprocessed/fiber/full \\
        --model-path /path/to/dtan_model/best.pt \\
        --output-dir /path/to/calibration/fiber_id \\
        --fiber-id mathis \\
        --section section1 \\
        --threshold-multiplier 5.0

    The output files are compatible with the existing CalibrationManager
    (see ai_engine/model_vehicle/calibration.py).

Requirements:
    pip install torch numpy
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Tuple

import numpy as np

PIPELINE_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GLRT Computation
# ---------------------------------------------------------------------------
def compute_glrt_from_aligned(
    aligned_data: np.ndarray,
    window_size: int = 20,
) -> np.ndarray:
    """Compute GLRT (Generalized Likelihood Ratio Test) from aligned data.

    The GLRT measures cross-channel correlation, which is high when a
    vehicle signature is present (all channels see a correlated signal).

    For aligned data, GLRT at time t = sum over channel pairs of
    correlation in a sliding window.

    Simplified GLRT: sum of squared normalized cross-correlation over
    adjacent channel pairs.

    Args:
        aligned_data: [n_sections, n_channels, n_samples] or [n_channels, n_samples]
        window_size: Sliding window size

    Returns:
        GLRT values [n_sections, n_samples] or [n_samples]
    """
    if aligned_data.ndim == 2:
        aligned_data = aligned_data[np.newaxis, :, :]

    n_sections, n_channels, n_samples = aligned_data.shape
    n_windows = n_samples - window_size + 1

    if n_windows <= 0:
        return np.zeros((n_sections, n_samples))

    glrt = np.zeros((n_sections, n_samples))

    for s in range(n_sections):
        for t in range(n_windows):
            window = aligned_data[s, :, t : t + window_size]  # [n_channels, window_size]
            # Cross-correlation between adjacent channels
            corr_sum = 0.0
            for ch in range(n_channels - 1):
                corr = np.corrcoef(window[ch], window[ch + 1])[0, 1]
                if not np.isnan(corr):
                    corr_sum += corr**2
            glrt[s, t + window_size // 2] = corr_sum

    return glrt.squeeze()


def compute_glrt_simple(
    processed_data: np.ndarray,
    window_size: int = 20,
) -> np.ndarray:
    """Compute simplified GLRT without DTAN alignment.

    Uses sliding-window cross-correlation between adjacent channels.
    This is a quick approximation for calibration purposes.

    Args:
        processed_data: [n_samples, n_channels] section data (post-pipeline)
        window_size: Sliding window size

    Returns:
        GLRT values [n_sections, n_samples] where n_sections = n_channels - 8
        (each "section" is a 9-channel group)
    """
    n_samples, n_channels = processed_data.shape
    n_ch_per_section = 9
    n_sections = max(1, (n_channels - n_ch_per_section + 1))

    # Limit sections for speed
    step = max(1, n_sections // 50)
    section_indices = list(range(0, n_sections, step))
    n_output_sections = len(section_indices)

    glrt = np.zeros((n_output_sections, n_samples))

    for i, sec_start in enumerate(section_indices):
        sec_data = processed_data[:, sec_start : sec_start + n_ch_per_section].T  # [9, n_samples]

        for t in range(window_size, n_samples - window_size):
            window = sec_data[:, t - window_size // 2 : t + window_size // 2]
            corr_sum = 0.0
            for ch in range(n_ch_per_section - 1):
                c = np.corrcoef(window[ch], window[ch + 1])[0, 1]
                if not np.isnan(c):
                    corr_sum += c**2
            glrt[i, t] = corr_sum

    return glrt


# ---------------------------------------------------------------------------
# Calibration Generation
# ---------------------------------------------------------------------------
def generate_threshold_curve(
    glrt_values: np.ndarray,
    method: str = "MAD",
    multiplier: float = 5.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Generate per-section detection thresholds from nighttime GLRT.

    Args:
        glrt_values: [n_sections, n_samples] GLRT from nighttime data
        method: "MAD" (Median Absolute Deviation) or "percentile"
        multiplier: Threshold = baseline + multiplier * noise_estimate

    Returns:
        Tuple of (threshold_curve, baseline, noise_estimate)
        Each is shape [n_sections]
    """
    n_sections = glrt_values.shape[0]

    baseline = np.zeros(n_sections)
    noise_estimate = np.zeros(n_sections)
    threshold_curve = np.zeros(n_sections)

    for s in range(n_sections):
        section_glrt = glrt_values[s]
        # Remove edge effects (zeros at start/end)
        valid = section_glrt[section_glrt > 0]

        if len(valid) == 0:
            baseline[s] = 0
            noise_estimate[s] = 1.0
            threshold_curve[s] = multiplier
            continue

        if method == "MAD":
            median = np.median(valid)
            mad = np.median(np.abs(valid - median))
            baseline[s] = median
            noise_estimate[s] = mad
            threshold_curve[s] = median + multiplier * mad
        elif method == "percentile":
            baseline[s] = np.median(valid)
            noise_estimate[s] = np.std(valid)
            threshold_curve[s] = np.percentile(valid, 95 + multiplier)
        else:
            raise ValueError(f"Unknown method: {method}")

    return threshold_curve, baseline, noise_estimate


def generate_coupling_corrections(
    glrt_values: np.ndarray,
) -> Tuple[np.ndarray, float]:
    """Generate per-section coupling correction factors.

    Normalizes GLRT amplitude across sections to compensate for
    fiber coupling variations (bends, splices, installation depth).

    Args:
        glrt_values: [n_sections, n_samples] GLRT values

    Returns:
        Tuple of (correction_factors [n_sections], median_glrt scalar)
    """
    # Compute median GLRT per section
    section_medians = np.array(
        [
            np.median(glrt_values[s][glrt_values[s] > 0]) if np.any(glrt_values[s] > 0) else 1.0
            for s in range(glrt_values.shape[0])
        ]
    )

    # Global median as reference
    median_glrt = float(np.median(section_medians[section_medians > 0]))
    if median_glrt <= 0:
        median_glrt = 1.0

    # Correction factor: multiply each section's GLRT by this to normalize
    correction_factors = median_glrt / np.maximum(section_medians, 1e-8)

    return correction_factors, median_glrt


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Generate Calibration Files")
    parser.add_argument(
        "--data-dir",
        type=str,
        required=True,
        help="Directory with preprocessed nighttime .npy files",
    )
    parser.add_argument(
        "--output-dir", type=str, required=True, help="Output directory for calibration files"
    )
    parser.add_argument("--fiber-id", type=str, required=True, help="Fiber identifier")
    parser.add_argument(
        "--section", type=str, default="default", help="Section name (from fibers.yaml)"
    )

    # Threshold parameters
    parser.add_argument(
        "--threshold-method",
        type=str,
        default="MAD",
        choices=["MAD", "percentile"],
        help="Threshold method (default: MAD)",
    )
    parser.add_argument(
        "--threshold-multiplier",
        type=float,
        default=5.0,
        help="Threshold = baseline + multiplier * noise (default: 5.0)",
    )

    # GLRT parameters
    parser.add_argument("--glrt-window", type=int, default=20, help="GLRT sliding window size")

    # Optional: use DTAN model for aligned GLRT
    parser.add_argument(
        "--model-path", type=str, default=None, help="Path to DTAN model .pt file (if available)"
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load preprocessed data
    data_path = Path(args.data_dir)
    chunk_files = sorted(data_path.glob(f"{args.section}_chunk*.npy"))
    if not chunk_files:
        raise FileNotFoundError(f"No chunk files for section '{args.section}' in {args.data_dir}")

    logger.info(f"Loading {len(chunk_files)} chunks for {args.fiber_id}/{args.section}")
    chunks = [np.load(str(f)) for f in chunk_files]
    data = np.concatenate(chunks, axis=0)  # [n_samples, n_channels]
    logger.info(f"Data shape: {data.shape}")

    # Compute GLRT
    logger.info("Computing GLRT (this may take a while)...")
    glrt = compute_glrt_simple(data, window_size=args.glrt_window)
    logger.info(f"GLRT shape: {glrt.shape}")

    # Generate thresholds
    logger.info(
        f"Generating thresholds (method={args.threshold_method}, multiplier={args.threshold_multiplier})"
    )
    threshold_curve, baseline, noise_estimate = generate_threshold_curve(
        glrt, method=args.threshold_method, multiplier=args.threshold_multiplier
    )

    logger.info(
        f"Threshold curve: range [{threshold_curve.min():.2f}, {threshold_curve.max():.2f}], "
        f"mean={threshold_curve.mean():.2f}"
    )

    # Generate coupling corrections
    logger.info("Computing coupling correction factors...")
    correction_factors, median_glrt = generate_coupling_corrections(glrt)

    logger.info(
        f"Coupling corrections: range [{correction_factors.min():.3f}, {correction_factors.max():.3f}], "
        f"median_glrt={median_glrt:.4f}"
    )

    # Save calibration files (compatible with CalibrationManager)
    date_str = datetime.now().strftime("%Y%m%d")

    # Threshold file
    threshold_data = {
        "date": date_str,
        "n_sections": len(threshold_curve),
        "threshold_curve": threshold_curve,
        "baseline": baseline,
        "noise_estimate": noise_estimate,
        "method": args.threshold_method,
    }
    threshold_path = output_dir / f"{args.fiber_id}_{date_str}_threshold.npz"
    np.savez(str(threshold_path), **threshold_data)
    logger.info(f"Saved threshold file: {threshold_path}")

    # Coupling file
    coupling_data = {
        "correction_factors": correction_factors,
        "median_glrt": np.array(median_glrt),
    }
    coupling_path = output_dir / f"{args.fiber_id}_{date_str}_coupling.npz"
    np.savez(str(coupling_path), **coupling_data)
    logger.info(f"Saved coupling file: {coupling_path}")

    # Generate diagnostic plot
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(14, 12))

    # GLRT noise floor per section
    ax = axes[0]
    ax.plot(baseline, label="Baseline (median)", linewidth=1)
    ax.plot(threshold_curve, label="Threshold", linewidth=1, linestyle="--")
    ax.fill_between(
        range(len(baseline)),
        baseline - noise_estimate,
        baseline + noise_estimate,
        alpha=0.2,
        label="Noise estimate (MAD)",
    )
    ax.set_title(f"Per-Section GLRT Noise Floor — {args.fiber_id}/{args.section}")
    ax.set_xlabel("Section index")
    ax.set_ylabel("GLRT value")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Coupling correction factors
    ax = axes[1]
    ax.plot(correction_factors, linewidth=1)
    ax.axhline(y=1.0, color="r", linestyle="--", alpha=0.5)
    ax.set_title("Coupling Correction Factors")
    ax.set_xlabel("Section index")
    ax.set_ylabel("Correction factor")
    ax.grid(True, alpha=0.3)

    # GLRT time series for a few sections
    ax = axes[2]
    n_sections_to_plot = min(5, glrt.shape[0])
    for i in range(0, glrt.shape[0], max(1, glrt.shape[0] // n_sections_to_plot)):
        ax.plot(glrt[i, :500], alpha=0.5, linewidth=0.5, label=f"Section {i}")
    ax.set_title("GLRT Time Series (first 500 samples)")
    ax.set_xlabel("Time sample")
    ax.set_ylabel("GLRT")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(str(output_dir / f"calibration_{args.fiber_id}_{args.section}.png"), dpi=150)
    plt.close()
    logger.info("Saved calibration diagnostic plot")

    logger.info(f"\nCalibration complete for {args.fiber_id}/{args.section}")
    logger.info(f"  Files saved to: {output_dir}")
    logger.info("  To use in pipeline: set use_calibration: true in fibers.yaml")
    logger.info(f"  and ensure calibration files are in /app/calibration/{args.fiber_id}/")


if __name__ == "__main__":
    main()
