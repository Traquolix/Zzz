"""Waterfall plot generation for AI engine monitoring."""

import logging
import os
import time as _time
from pathlib import Path
from typing import Optional, List, Tuple, Callable
import numpy as np
import matplotlib

matplotlib.use("Agg")  # Non-interactive backend for server use
import matplotlib.pyplot as plt
from datetime import datetime

from .calibration import CalibrationData

logger = logging.getLogger(__name__)


def _build_speed_panel(
    ax: plt.Axes,
    intervals_list: List[Tuple[List[int], List[int]]],
    filtered_speed: np.ndarray,
    n_samples: int,
    n_sections: int,
    title: str,
    speed_filter: Callable[[float], Optional[float]],
    vmin: float = 20.0,
    vmax: float = 120.0,
) -> None:
    """Fill a single speed-based panel from detection intervals.

    Args:
        ax: Matplotlib axes to draw on
        intervals_list: Detection intervals per section [(starts, ends), ...]
        filtered_speed: Speed values (n_sections, channels, time_samples)
        n_samples: Number of time samples
        n_sections: Number of spatial sections
        title: Panel title
        speed_filter: Function that takes median_speed and returns the display
            value, or None to skip the interval.
        vmin: Colormap minimum
        vmax: Colormap maximum
    """
    speed_data = np.full((n_samples, n_sections), np.nan)

    for section_idx, (starts, ends) in enumerate(intervals_list):
        for start, end in zip(starts, ends):
            speed_slice = filtered_speed[section_idx, :, start:end]
            median_speed = np.nanmedian(speed_slice)

            if np.isnan(median_speed):
                continue

            display_value = speed_filter(median_speed)
            if display_value is not None:
                speed_data[start:end, section_idx] = display_value

    speed_masked = np.ma.masked_invalid(speed_data)

    im = ax.imshow(
        speed_masked,
        aspect="auto",
        cmap="viridis",
        interpolation="nearest",
        origin="lower",
        extent=[0, n_sections, 0, n_samples],
        vmin=vmin,
        vmax=vmax,
    )
    ax.set_xlabel("Section Index")
    ax.set_title(title)
    plt.colorbar(im, ax=ax, label="Speed (km/h)")


class VehicleVisualizer:
    """Generates waterfall plots showing GLRT detections and speeds."""

    def __init__(
        self,
        output_dir: str = "/app/visualizations",
        fiber_id: str = "unknown",
        static_threshold: float = 130.0,
    ):
        """Initialize visualizer.

        Args:
            output_dir: Directory to save visualization images
            fiber_id: Fiber identifier for subdirectory
            static_threshold: Static threshold value (fallback when no calibration)
        """
        self.output_dir = Path(output_dir) / fiber_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.fiber_id = fiber_id
        self.section = "default"  # Will be updated per buffer processing
        self.static_threshold = static_threshold
        logger.info(f"VehicleVisualizer initialized: output_dir={self.output_dir}")

    def generate_notebook_waterfall(
        self,
        raw_data: np.ndarray,
        fwd_detections: list[dict],
        rev_detections: list[dict],
        date_window: np.ndarray,
        fs: float,
        channel_start: int = 0,
        channel_step: int = 1,
        gauge: float = 15.3846,
        min_speed_kmh: float = 20.0,
        max_speed_kmh: float = 120.0,
    ) -> str:
        """Generate waterfall with detection overlay matching notebook style.

        Single large panel with viridis DAS background, forward detections as
        circles and reverse as triangles, all colored by speed (jet colormap).

        Args:
            raw_data: Raw sensor data (channels, time_samples) before splitting
            fwd_detections: Forward detection dicts with section_idx, speed_kmh
            rev_detections: Reverse detection dicts (same format)
            date_window: Timestamps for each time sample
            fs: Sampling rate in Hz
            channel_start: First channel index in the raw fiber
            channel_step: Channel step (unused, kept for API compat)
            gauge: Sensor gauge distance in meters
            min_speed_kmh: Minimum speed for colorbar
            max_speed_kmh: Maximum speed for colorbar

        Returns:
            Path to saved image file
        """
        try:
            n_channels, n_samples = raw_data.shape
            duration_s = n_samples / fs

            # Center data for display (remove DC per channel)
            display_data = raw_data - np.mean(raw_data, axis=1, keepdims=True)

            # Distance axis: channel index -> km
            dist_km = np.arange(n_channels) * gauge / 1000
            vmax_data = 2 * display_data.std()

            # Build detection arrays
            def _build_det_arrays(detections):
                if not detections:
                    return np.array([]), np.array([]), np.array([])
                d_km = []
                t_s = []
                speeds = []
                for det in detections:
                    section_idx = det["section_idx"]
                    if section_idx >= n_channels:
                        continue
                    d_km.append(section_idx * gauge / 1000)
                    if det.get("_t_mid_sample") is not None:
                        t_s.append(det["_t_mid_sample"] / fs)
                    else:
                        t_s.append(duration_s / 2)
                    speeds.append(abs(det["speed_kmh"]))
                return np.array(d_km), np.array(t_s), np.array(speeds)

            fwd_d, fwd_t, fwd_spd = _build_det_arrays(fwd_detections)
            rev_d, rev_t, rev_spd = _build_det_arrays(rev_detections)
            n_fwd = len(fwd_spd)
            n_rev = len(rev_spd)

            # Single large figure
            fig, ax = plt.subplots(figsize=(18, 10))

            ax.imshow(
                display_data.T,
                aspect="auto",
                cmap="viridis",
                vmin=-vmax_data,
                vmax=vmax_data,
                extent=[dist_km[0], dist_km[-1], duration_s, 0],
            )

            # Speed colorbar range
            all_speeds = np.concatenate([fwd_spd, rev_spd]) if n_fwd + n_rev > 0 else np.array([])
            if len(all_speeds) > 0:
                speed_vmin = max(min_speed_kmh, np.percentile(all_speeds, 2))
                speed_vmax = min(max_speed_kmh, np.percentile(all_speeds, 98))
                if speed_vmin >= speed_vmax:
                    speed_vmin, speed_vmax = min_speed_kmh, max_speed_kmh
            else:
                speed_vmin, speed_vmax = min_speed_kmh, max_speed_kmh

            sc = None
            if n_fwd > 0:
                sc = ax.scatter(
                    fwd_d,
                    fwd_t,
                    c=fwd_spd,
                    cmap="jet",
                    s=10,
                    vmin=speed_vmin,
                    vmax=speed_vmax,
                    edgecolors="none",
                    marker="o",
                    zorder=5,
                    label=f"{n_fwd} forward",
                )
            if n_rev > 0:
                sc = ax.scatter(
                    rev_d,
                    rev_t,
                    c=rev_spd,
                    cmap="jet",
                    s=10,
                    vmin=speed_vmin,
                    vmax=speed_vmax,
                    edgecolors="none",
                    marker="v",
                    zorder=5,
                    label=f"{n_rev} reverse",
                )
            if sc is not None:
                plt.colorbar(sc, ax=ax, label="Speed (km/h)", shrink=0.6, pad=0.01)

            ax.set_xlabel("Distance (km)", fontsize=12)
            ax.set_ylabel("Time (s)", fontsize=12)
            ax.legend(fontsize=11, loc="upper left")

            # Timestamp
            if hasattr(date_window[0], "strftime"):
                timestamp_str = date_window[0].strftime("%Y-%m-%d %H:%M:%S")
            else:
                timestamp_str = datetime.fromtimestamp(date_window[0]).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

            ax.set_title(
                f"DAS Vehicle Detection - {self.fiber_id}:{self.section} - "
                f"{timestamp_str} ({n_fwd + n_rev} det)",
                fontsize=14,
            )
            plt.tight_layout()

            # Save
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"waterfall_{self.section}_{ts}.png"
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=120, bbox_inches="tight")
            plt.close(fig)

            try:
                os.chmod(filepath, 0o644)
            except Exception as e:
                logger.warning(f"Could not set permissions on {filepath}: {e}")

            # Clean up old visualizations (keep last 24h)
            self._cleanup_old_visualizations()

            logger.info(
                f"Saved waterfall: {filepath} (fwd={n_fwd}, rev={n_rev})"
            )
            return str(filepath)

        except Exception as e:
            logger.error(f"Failed to generate waterfall: {e}", exc_info=True)
            if "fig" in locals():
                plt.close(fig)
            raise

    def _cleanup_old_visualizations(self, max_age_hours: float = 24.0) -> None:
        """Remove visualization PNGs older than max_age_hours."""
        cutoff = _time.time() - max_age_hours * 3600
        removed = 0
        try:
            for png in self.output_dir.glob("waterfall_*.png"):
                if png.stat().st_mtime < cutoff:
                    png.unlink()
                    removed += 1
            if removed > 0:
                logger.info(f"Cleaned up {removed} old visualizations from {self.output_dir}")
        except OSError as e:
            logger.warning(f"Visualization cleanup failed: {e}")

    def generate_waterfall(
        self,
        glrt_res: np.ndarray,
        filtered_speed: np.ndarray,
        intervals_list: List[Tuple[List[int], List[int]]],
        date_window: np.ndarray,
        calibration_data: Optional[CalibrationData] = None,
        min_speed_kmh: float = 20.0,
        max_speed_kmh: float = 120.0,
        count_data: Optional[Tuple[List, List, List]] = None,
    ) -> str:
        """Generate six-panel waterfall visualization (legacy format).

        Creates six plots:
        1. Original GLRT data (viridis colormap, time on y-axis)
        2. GLRT with detection overlay
        3. Detection zones only, colored by speed (all GLRT detections)
        4. Post-filtered detections (only min-max km/h speeds sent to Kafka)
        5. Direction 1 (positive speeds, from filtered min-max km/h)
        6. Direction 2 (negative speeds, from filtered min-max km/h)

        Args:
            glrt_res: GLRT correlation matrix (n_sections, time_samples)
            filtered_speed: Speed values (n_sections, channels, time_samples)
            intervals_list: Detection intervals per section [(starts, ends), ...]
            date_window: Timestamps for time axis
            calibration_data: Optional calibration for variable thresholds
            min_speed_kmh: Minimum speed for final filter (default: 20.0)
            max_speed_kmh: Maximum speed for final filter (default: 120.0)
            count_data: Optional tuple of (counts, intervals, timestamps) from VehicleCounter

        Returns:
            Path to saved image file
        """
        try:
            n_sections, n_samples = glrt_res.shape

            # Transpose data so time is on y-axis
            glrt_transposed = glrt_res.T  # Now (time_samples, n_sections)

            # Create figure with 6 subplots side by side
            fig, (ax1, ax2, ax3, ax4, ax5, ax6) = plt.subplots(1, 6, figsize=(38, 10), sharey=True)

            # Determine title suffix
            if calibration_data is not None:
                title_suffix = (
                    f"Variable Threshold (range: "
                    f"{calibration_data.threshold_curve.min():.0f}-"
                    f"{calibration_data.threshold_curve.max():.0f})"
                )
            else:
                title_suffix = f"Static Threshold: {self.static_threshold:.0f}"

            # === PLOT 1: Original GLRT data ===
            im1 = ax1.imshow(
                glrt_transposed,
                aspect="auto",
                cmap="viridis",
                interpolation="nearest",
                origin="lower",
                extent=[0, n_sections, 0, n_samples],
                vmin=0,
                vmax=500,
            )
            ax1.set_xlabel("Section Index")
            ax1.set_ylabel("Time Sample")
            ax1.set_title(f"1. Original GLRT Data\n{self.fiber_id}")
            plt.colorbar(im1, ax=ax1, label="GLRT Value")

            # === PLOT 2: GLRT with detection overlay ===
            im2 = ax2.imshow(
                glrt_transposed,
                aspect="auto",
                cmap="viridis",
                interpolation="nearest",
                origin="lower",
                extent=[0, n_sections, 0, n_samples],
                vmin=0,
                vmax=500,
            )
            ax2.set_xlabel("Section Index")
            ax2.set_title(f"2. With Detection Overlay\n{title_suffix}")
            plt.colorbar(im2, ax=ax2, label="GLRT Value")

            # Overlay detection zones as rectangles
            for section_idx, (starts, ends) in enumerate(intervals_list):
                for start, end in zip(starts, ends):
                    rect = plt.Rectangle(
                        (section_idx, start),
                        1,
                        end - start,
                        fill=False,
                        edgecolor="red",
                        linewidth=2,
                        linestyle="--",
                    )
                    ax2.add_patch(rect)

            # === PLOTS 3–6: Speed panels with different filters ===
            speed_range = f"{min_speed_kmh:.0f}-{max_speed_kmh:.0f} km/h"
            panel_args = dict(
                intervals_list=intervals_list,
                filtered_speed=filtered_speed,
                n_samples=n_samples,
                n_sections=n_sections,
            )

            # Plot 3: All detections, colored by absolute speed
            _build_speed_panel(
                ax3, **panel_args,
                title=f"3. Detections Colored by Speed\n(20-120 km/h)",
                speed_filter=lambda s: abs(s),
            )

            # Plot 4: Post-filtered (only speeds within min/max range)
            def _range_filter(s):
                a = abs(s)
                return a if min_speed_kmh <= a <= max_speed_kmh else None

            _build_speed_panel(
                ax4, **panel_args,
                title=f"4. Post-Filtered (Sent to Kafka)\n({speed_range} only)",
                speed_filter=_range_filter,
            )

            # Plot 5: Direction 1 (positive speeds within range)
            def _positive_filter(s):
                if s <= 0:
                    return None
                a = abs(s)
                return s if min_speed_kmh <= a <= max_speed_kmh else None

            _build_speed_panel(
                ax5, **panel_args,
                title=f"5. Direction 1 (Filtered Positive)\n({speed_range})",
                speed_filter=_positive_filter,
            )

            # Plot 6: Direction 2 (negative speeds within range, displayed as positive)
            def _negative_filter(s):
                if s >= 0:
                    return None
                a = abs(s)
                return a if min_speed_kmh <= a <= max_speed_kmh else None

            _build_speed_panel(
                ax6, **panel_args,
                title=f"6. Direction 2 (Filtered Negative)\n({speed_range})",
                speed_filter=_negative_filter,
            )

            # === Overlay count detections if available ===
            if count_data is not None:
                self._overlay_counts(
                    count_data, [ax2, ax3, ax4, ax5, ax6], n_samples,
                )
            else:
                logger.info("No count data available for visualization overlay")

            # Add timestamp annotation
            if hasattr(date_window[0], "strftime"):
                timestamp_str = date_window[0].strftime("%Y-%m-%d %H:%M:%S")
            else:
                timestamp_str = datetime.fromtimestamp(date_window[0]).strftime("%Y-%m-%d %H:%M:%S")

            fig.suptitle(f"DAS Vehicle Detection - Start: {timestamp_str}", fontsize=14, y=0.98)

            plt.tight_layout(rect=[0, 0, 1, 0.96])

            # Save figure
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"waterfall_{self.section}_{timestamp}.png"
            filepath = self.output_dir / filename
            plt.savefig(filepath, dpi=120, bbox_inches="tight")
            plt.close(fig)

            # Set secure permissions (owner read/write, group/other read-only)
            try:
                os.chmod(filepath, 0o644)
            except Exception as e:
                logger.warning(f"Could not set permissions on {filepath}: {e}")

            logger.info(f"Saved waterfall visualization: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"Failed to generate waterfall plot: {e}", exc_info=True)
            if "fig" in locals():
                plt.close(fig)
            raise

    def _overlay_counts(
        self,
        count_data: Tuple[List, List, List],
        axes: List[plt.Axes],
        n_samples: int,
    ) -> None:
        """Overlay vehicle count markers on panels.

        Args:
            count_data: (counts, intervals, timestamps) from VehicleCounter
            axes: List of axes to overlay on
            n_samples: Number of time samples in the visualization window
        """
        counts, count_intervals, count_timestamps = count_data
        logger.info(f"Count overlay: {len(counts)} sections, viz window: {n_samples} samples")

        # Detect if intervals are already aligned with viz window or need offset
        max_interval_idx = 0
        for section_intervals in count_intervals:
            if isinstance(section_intervals, tuple) and len(section_intervals) == 2:
                starts, ends = section_intervals
                if len(ends) > 0:
                    max_interval_idx = max(max_interval_idx, max(ends))

        # If max index is close to viz window size, intervals are already aligned
        # Otherwise they're from 6-minute window and need offset
        if max_interval_idx <= n_samples * 1.5:
            count_time_offset = 0
            logger.info(f"Count intervals pre-aligned with viz window (max_idx={max_interval_idx})")
        else:
            counting_window_samples = 3600  # 6 minutes at 10Hz
            count_time_offset = counting_window_samples - n_samples
            logger.info(f"Count intervals from 6-min window (max_idx={max_interval_idx}, offset={count_time_offset})")

        total_count_markers = 0
        filtered_too_old = 0

        for ax in axes:
            for section_idx, (section_counts, section_intervals) in enumerate(zip(counts, count_intervals)):
                if section_counts is None or len(section_counts) == 0:
                    continue
                if len(section_intervals) != 2:
                    continue

                starts, ends = section_intervals

                for count, start, end in zip(section_counts, starts, ends):
                    if count <= 0:
                        continue
                    if start < count_time_offset:
                        filtered_too_old += 1
                        continue

                    viz_start = start - count_time_offset
                    viz_end = end - count_time_offset

                    if viz_start >= n_samples:
                        continue

                    time_center = (viz_start + viz_end) / 2
                    section_center = section_idx + 0.5
                    marker_size = min(max(count * 100, 50), 500)

                    ax.scatter(
                        section_center,
                        time_center,
                        s=marker_size,
                        c='yellow',
                        marker='*',
                        edgecolors='black',
                        linewidths=1,
                        alpha=0.8,
                        zorder=10,
                    )
                    total_count_markers += 1

        logger.info(f"Count overlay: {filtered_too_old} filtered (outside viz window), {total_count_markers} markers shown")
