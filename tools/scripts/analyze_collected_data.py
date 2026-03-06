#!/usr/bin/env python3
"""Analyze collected DAS data and experiment with preprocessing parameters.

This script loads collected data and allows you to:
1. Visualize raw vs processed data
2. Experiment with different preprocessing parameters
3. Compare GLRT detection results with different thresholds
4. Export optimized parameters for fibers.yaml

Usage:
    python scripts/analyze_collected_data.py data/collected/raw_carros_*.npz

Requirements:
    pip install numpy matplotlib scipy
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

try:
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not installed. Visualization disabled.")
    print("Install with: pip install matplotlib")

try:
    from scipy import signal as scipy_signal
    from scipy.ndimage import median_filter
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("Warning: scipy not installed. Some preprocessing disabled.")
    print("Install with: pip install scipy")


class DASDataAnalyzer:
    """Analyze and experiment with DAS data preprocessing."""

    def __init__(self, filepath: str | Path):
        self.filepath = Path(filepath)
        self.data = np.load(filepath, allow_pickle=True)

        self.values = self.data["values"]  # (samples, channels)
        self.timestamps = self.data["timestamps"]
        self.fiber_id = str(self.data.get("fiber_id", "unknown"))

        # Parse metadata
        metadata_str = str(self.data.get("metadata", "{}"))
        self.metadata = json.loads(metadata_str) if metadata_str else {}

        self.sampling_rate = self.metadata.get("sampling_rate_hz", 50.0)
        self.channel_start = self.metadata.get("channel_start", 0)

        print(f"Loaded: {filepath}")
        print(f"  Fiber: {self.fiber_id}")
        print(f"  Shape: {self.values.shape} (samples x channels)")
        print(f"  Sampling rate: {self.sampling_rate} Hz")
        print(f"  Duration: {len(self.values) / self.sampling_rate:.1f} seconds")

    def apply_bandpass(
        self,
        data: np.ndarray,
        low_freq: float = 0.1,
        high_freq: float = 2.0,
        order: int = 4,
        sampling_rate: float | None = None,
    ) -> np.ndarray:
        """Apply bandpass filter to data."""
        if not SCIPY_AVAILABLE:
            print("scipy not available, skipping bandpass filter")
            return data

        fs = sampling_rate or self.sampling_rate
        nyquist = fs / 2.0

        if high_freq >= nyquist:
            high_freq = nyquist * 0.95
            print(f"Warning: Adjusted high_freq to {high_freq:.2f} Hz (below Nyquist)")

        sos = scipy_signal.butter(order, [low_freq, high_freq], btype="band", fs=fs, output="sos")
        return scipy_signal.sosfiltfilt(sos, data, axis=0)

    def apply_common_mode_removal(self, data: np.ndarray, method: str = "median") -> np.ndarray:
        """Remove common mode noise (spatial median/mean per sample)."""
        if method == "median":
            common_mode = np.median(data, axis=1, keepdims=True)
        else:
            common_mode = np.mean(data, axis=1, keepdims=True)
        return data - common_mode

    def apply_temporal_decimation(self, data: np.ndarray, factor: int = 5) -> np.ndarray:
        """Decimate temporally by selecting every Nth sample."""
        return data[::factor, :]

    def apply_spatial_decimation(self, data: np.ndarray, factor: int = 2) -> np.ndarray:
        """Decimate spatially by selecting every Nth channel."""
        return data[:, ::factor]

    def apply_channel_mean_subtraction(self, data: np.ndarray) -> np.ndarray:
        """Subtract mean from each channel (per-channel temporal centering).

        This is what the thesis describes: "centered the data by subtracting
        the mean from each channel".
        """
        channel_means = np.mean(data, axis=0, keepdims=True)
        return data - channel_means

    def normalize_zscore(self, data: np.ndarray, epsilon: float = 1e-8) -> np.ndarray:
        """Apply z-score normalization."""
        mean = np.mean(data)
        std = np.std(data) + epsilon
        return (data - mean) / std

    def compute_glrt(
        self,
        aligned_data: np.ndarray,
        window_size: int = 20,
    ) -> np.ndarray:
        """Compute GLRT test statistic.

        Args:
            aligned_data: 2D array (channels, time) - aligned sensor data
            window_size: GLRT window size

        Returns:
            1D array of GLRT values
        """
        n_channels, n_samples = aligned_data.shape

        # Product of adjacent channels
        products = aligned_data[:-1, :] * aligned_data[1:, :]

        # Sum over channels and sliding window
        glrt = np.zeros(n_samples - window_size)
        for i in range(n_samples - window_size):
            glrt[i] = np.sum(products[:, i:i + window_size])

        return glrt

    def preprocess_thesis_style(
        self,
        low_freq: float = 0.1,
        high_freq: float = 2.0,
        temporal_decimation: int = 5,
        spatial_decimation: int = 1,  # Thesis used 1 (no spatial decimation)
    ) -> np.ndarray:
        """Apply preprocessing matching the thesis methodology.

        Thesis preprocessing (Section 2.6):
        1. Band-pass filter 0.1-2 Hz
        2. Center data by subtracting mean from each channel
        3. Downsample (250Hz -> 10Hz in thesis, we do 50Hz -> 10Hz)
        """
        data = self.values.copy()

        # 1. Bandpass filter
        print(f"  Applying bandpass filter ({low_freq}-{high_freq} Hz)...")
        data = self.apply_bandpass(data, low_freq, high_freq)

        # 2. Per-channel mean subtraction (thesis style)
        print("  Applying per-channel mean subtraction...")
        data = self.apply_channel_mean_subtraction(data)

        # 3. Temporal decimation
        if temporal_decimation > 1:
            print(f"  Applying temporal decimation (factor {temporal_decimation})...")
            data = self.apply_temporal_decimation(data, temporal_decimation)

        # 4. Spatial decimation (optional, thesis didn't use)
        if spatial_decimation > 1:
            print(f"  Applying spatial decimation (factor {spatial_decimation})...")
            data = self.apply_spatial_decimation(data, spatial_decimation)

        return data

    def preprocess_current_pipeline(
        self,
        low_freq: float = 0.1,
        high_freq: float = 2.0,
        temporal_decimation: int = 5,
        spatial_decimation: int = 2,
    ) -> np.ndarray:
        """Apply preprocessing matching current pipeline in fibers.yaml.

        Current preprocessing:
        1. Common mode removal (spatial median)
        2. Band-pass filter 0.1-2 Hz
        3. Spatial decimation (factor 2)
        4. Temporal decimation (factor 5)
        """
        data = self.values.copy()

        # 1. Common mode removal (current pipeline does this first)
        print("  Applying common mode removal (spatial median)...")
        data = self.apply_common_mode_removal(data, method="median")

        # 2. Bandpass filter
        print(f"  Applying bandpass filter ({low_freq}-{high_freq} Hz)...")
        data = self.apply_bandpass(data, low_freq, high_freq)

        # 3. Spatial decimation
        if spatial_decimation > 1:
            print(f"  Applying spatial decimation (factor {spatial_decimation})...")
            data = self.apply_spatial_decimation(data, spatial_decimation)

        # 4. Temporal decimation
        if temporal_decimation > 1:
            print(f"  Applying temporal decimation (factor {temporal_decimation})...")
            data = self.apply_temporal_decimation(data, temporal_decimation)

        return data

    def visualize_comparison(
        self,
        channel_range: tuple[int, int] = (0, 100),
        time_range: tuple[float, float] | None = None,
        save_path: str | None = None,
    ):
        """Visualize raw vs preprocessed data."""
        if not MATPLOTLIB_AVAILABLE:
            print("matplotlib not available, cannot visualize")
            return

        # Slice data
        ch_start, ch_end = channel_range
        raw_slice = self.values[:, ch_start:ch_end]

        if time_range:
            t_start = int(time_range[0] * self.sampling_rate)
            t_end = int(time_range[1] * self.sampling_rate)
            raw_slice = raw_slice[t_start:t_end, :]

        # Preprocess both ways
        print("\nPreprocessing with thesis methodology...")
        thesis_data = self.preprocess_thesis_style()
        thesis_slice = thesis_data[:, ch_start:ch_end // 1]  # No spatial decimation

        print("\nPreprocessing with current pipeline...")
        current_data = self.preprocess_current_pipeline()
        current_slice = current_data[:, ch_start // 2:ch_end // 2]  # With spatial decimation

        # Create figure
        fig, axes = plt.subplots(3, 1, figsize=(14, 10))

        # Time axes
        raw_time = np.arange(raw_slice.shape[0]) / self.sampling_rate
        thesis_time = np.arange(thesis_slice.shape[0]) / (self.sampling_rate / 5)
        current_time = np.arange(current_slice.shape[0]) / (self.sampling_rate / 5)

        # Raw data
        ax = axes[0]
        vmax = np.percentile(np.abs(raw_slice), 99)
        im = ax.imshow(
            raw_slice.T,
            aspect="auto",
            cmap="seismic",
            vmin=-vmax,
            vmax=vmax,
            extent=[raw_time[0], raw_time[-1], ch_end, ch_start],
        )
        ax.set_ylabel("Channel")
        ax.set_title(f"Raw Data ({self.fiber_id}) - {self.sampling_rate} Hz")
        plt.colorbar(im, ax=ax, label="Amplitude")

        # Thesis preprocessing
        ax = axes[1]
        vmax = np.percentile(np.abs(thesis_slice), 99)
        im = ax.imshow(
            thesis_slice.T,
            aspect="auto",
            cmap="seismic",
            vmin=-vmax,
            vmax=vmax,
            extent=[thesis_time[0], thesis_time[-1], ch_end, ch_start],
        )
        ax.set_ylabel("Channel")
        ax.set_title("Thesis Preprocessing (bandpass + per-channel mean, no spatial decimation)")
        plt.colorbar(im, ax=ax, label="Amplitude")

        # Current preprocessing
        ax = axes[2]
        vmax = np.percentile(np.abs(current_slice), 99)
        im = ax.imshow(
            current_slice.T,
            aspect="auto",
            cmap="seismic",
            vmin=-vmax,
            vmax=vmax,
            extent=[current_time[0], current_time[-1], ch_end // 2, ch_start // 2],
        )
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Channel")
        ax.set_title("Current Pipeline (CMR + bandpass + spatial decimation)")
        plt.colorbar(im, ax=ax, label="Amplitude")

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            print(f"\nSaved figure to {save_path}")
        else:
            plt.show()

    def analyze_threshold_sensitivity(
        self,
        thresholds: list[float] = [100, 130, 200, 300, 400, 500],
        channel_range: tuple[int, int] = (0, 9),
        window_seconds: float = 30.0,
    ):
        """Analyze how detection threshold affects results.

        This helps determine the optimal threshold for your data.
        """
        if not MATPLOTLIB_AVAILABLE:
            print("matplotlib not available, cannot visualize")
            return

        # Preprocess data
        print("Preprocessing data...")
        data = self.preprocess_thesis_style()

        # Extract a window
        window_samples = int(window_seconds * (self.sampling_rate / 5))  # After decimation
        ch_start, ch_end = channel_range

        if data.shape[0] < window_samples:
            window_samples = data.shape[0]

        window = data[:window_samples, ch_start:ch_end]

        # Normalize
        window = self.normalize_zscore(window)

        # Compute simple GLRT approximation
        print("Computing GLRT...")
        glrt = self.compute_glrt(window.T)

        # Plot threshold analysis
        fig, axes = plt.subplots(len(thresholds) + 1, 1, figsize=(14, 3 * (len(thresholds) + 1)))

        time_axis = np.arange(len(glrt)) / (self.sampling_rate / 5)

        # GLRT values
        ax = axes[0]
        ax.plot(time_axis, glrt, "b-", linewidth=0.5)
        ax.set_ylabel("GLRT")
        ax.set_title(f"GLRT Test Statistic ({self.fiber_id}, channels {ch_start}-{ch_end})")
        ax.grid(True, alpha=0.3)

        # Add threshold lines
        for thresh in thresholds:
            ax.axhline(y=thresh, color="r", linestyle="--", alpha=0.5, label=f"δ={thresh}")

        ax.legend(loc="upper right", fontsize=8)

        # Detection results for each threshold
        for i, thresh in enumerate(thresholds):
            ax = axes[i + 1]
            detections = (glrt >= thresh).astype(float)
            detection_count = np.sum(np.diff(detections) > 0)  # Count rising edges

            ax.fill_between(time_axis, 0, detections, alpha=0.5, label=f"Detections")
            ax.plot(time_axis, glrt / np.max(glrt), "b-", linewidth=0.5, alpha=0.5)
            ax.set_ylabel(f"δ={thresh}")
            ax.set_title(f"Threshold {thresh}: {detection_count} vehicle intervals detected")
            ax.set_ylim(-0.1, 1.1)
            ax.grid(True, alpha=0.3)

        axes[-1].set_xlabel("Time (s)")

        plt.tight_layout()
        plt.savefig(f"threshold_analysis_{self.fiber_id}.png", dpi=150, bbox_inches="tight")
        print(f"\nSaved threshold analysis to threshold_analysis_{self.fiber_id}.png")
        plt.show()

    def print_statistics(self):
        """Print data statistics for debugging."""
        print("\n" + "=" * 60)
        print("Data Statistics")
        print("=" * 60)

        print(f"\nRaw data:")
        print(f"  Min: {np.min(self.values):.4f}")
        print(f"  Max: {np.max(self.values):.4f}")
        print(f"  Mean: {np.mean(self.values):.4f}")
        print(f"  Std: {np.std(self.values):.4f}")

        # Per-channel statistics
        channel_stds = np.std(self.values, axis=0)
        print(f"\nPer-channel std dev:")
        print(f"  Min: {np.min(channel_stds):.4f}")
        print(f"  Max: {np.max(channel_stds):.4f}")
        print(f"  Mean: {np.mean(channel_stds):.4f}")

        # Check for dead channels
        dead_channels = np.where(channel_stds < 1e-6)[0]
        if len(dead_channels) > 0:
            print(f"\nWarning: {len(dead_channels)} potentially dead channels detected")
            print(f"  Indices: {dead_channels[:10]}{'...' if len(dead_channels) > 10 else ''}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze collected DAS data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "filepath",
        type=str,
        help="Path to collected .npz file",
    )
    parser.add_argument(
        "--channels",
        type=str,
        default="0:100",
        help="Channel range to analyze (start:end, default: 0:100)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print data statistics",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare preprocessing methods",
    )
    parser.add_argument(
        "--threshold",
        action="store_true",
        help="Analyze threshold sensitivity",
    )

    args = parser.parse_args()

    # Parse channel range
    ch_parts = args.channels.split(":")
    channel_range = (int(ch_parts[0]), int(ch_parts[1]))

    # Load and analyze
    analyzer = DASDataAnalyzer(args.filepath)

    if args.stats:
        analyzer.print_statistics()

    if args.compare:
        analyzer.visualize_comparison(channel_range=channel_range)

    if args.threshold:
        analyzer.analyze_threshold_sensitivity(channel_range=(channel_range[0], min(channel_range[0] + 9, channel_range[1])))

    # Default: show stats and comparison
    if not any([args.stats, args.compare, args.threshold]):
        analyzer.print_statistics()
        analyzer.visualize_comparison(channel_range=channel_range)


if __name__ == "__main__":
    main()
