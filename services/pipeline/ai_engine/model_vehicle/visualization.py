"""Waterfall plot generation for AI engine monitoring."""

import logging
import os
from pathlib import Path
from typing import Optional, List, Tuple
import numpy as np
import matplotlib

matplotlib.use("Agg")  # Non-interactive backend for server use
import matplotlib.pyplot as plt
from datetime import datetime

from .calibration import CalibrationData

logger = logging.getLogger(__name__)


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
        """Generate six-panel waterfall visualization.

        Creates six plots:
        1. Original GLRT data (viridis colormap, time on y-axis)
        2. GLRT with detection overlay
        3. Detection zones only, colored by speed (all GLRT detections)
        4. Post-filtered detections (only 20-120 km/h speeds sent to Kafka)
        5. Direction 1 (positive speeds, from filtered 20-120 km/h)
        6. Direction 2 (negative speeds, from filtered 20-120 km/h)

        Args:
            glrt_res: GLRT correlation matrix (n_sections, time_samples)
            filtered_speed: Speed values (n_sections, channels, time_samples)
            intervals_list: Detection intervals per section [(starts, ends), ...]
            date_window: Timestamps for time axis
            calibration_data: Optional calibration for variable thresholds
            min_speed_kmh: Minimum speed for final filter (default: 20.0)
            max_speed_kmh: Maximum speed for final filter (default: 120.0)
            count_data: Optional tuple of (counts, intervals, timestamps) from SimpleIntervalCounter

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
            cbar1 = plt.colorbar(im1, ax=ax1, label="GLRT Value")

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
            cbar2 = plt.colorbar(im2, ax=ax2, label="GLRT Value")

            # Overlay detection zones as rectangles
            for section_idx, (starts, ends) in enumerate(intervals_list):
                for start, end in zip(starts, ends):
                    # Draw rectangle (note: coords are (x, y) = (section, time))
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

            # === PLOT 3: Detection zones colored by speed ===
            # Create masked array with only detection zones visible
            # Initialize with NaN (will be masked)
            speed_data = np.full((n_samples, n_sections), np.nan)

            # Fill detection zones with speed values
            for section_idx, (starts, ends) in enumerate(intervals_list):
                for start, end in zip(starts, ends):
                    # Get median speed for this detection zone
                    speed_slice = filtered_speed[section_idx, :, start:end]
                    median_speed = np.nanmedian(speed_slice)

                    if not np.isnan(median_speed):
                        # Fill the detection zone with the speed value
                        speed_data[start:end, section_idx] = abs(median_speed)

            # Mask NaN values
            speed_masked = np.ma.masked_invalid(speed_data)

            im3 = ax3.imshow(
                speed_masked,
                aspect="auto",
                cmap="viridis",
                interpolation="nearest",
                origin="lower",
                extent=[0, n_sections, 0, n_samples],
                vmin=20,  # min_speed_kmh
                vmax=120,  # max_speed_kmh
            )
            ax3.set_xlabel("Section Index")
            ax3.set_title(f"3. Detections Colored by Speed\n(20-120 km/h)")
            cbar3 = plt.colorbar(im3, ax=ax3, label="Speed (km/h)")

            # === PLOT 4: Post-filtered speeds (only speeds sent to Kafka) ===
            speed_data_postfilter = np.full((n_samples, n_sections), np.nan)

            # Fill detection zones with speeds that pass min/max filter
            for section_idx, (starts, ends) in enumerate(intervals_list):
                for start, end in zip(starts, ends):
                    # Get median speed for this detection zone
                    speed_slice = filtered_speed[section_idx, :, start:end]
                    median_speed = np.nanmedian(speed_slice)

                    # Only show if speed passes the min/max filter (same as Kafka messages)
                    abs_speed = abs(median_speed) if not np.isnan(median_speed) else np.nan
                    if not np.isnan(abs_speed) and min_speed_kmh <= abs_speed <= max_speed_kmh:
                        speed_data_postfilter[start:end, section_idx] = abs_speed

            speed_masked_postfilter = np.ma.masked_invalid(speed_data_postfilter)

            im4 = ax4.imshow(
                speed_masked_postfilter,
                aspect="auto",
                cmap="viridis",
                interpolation="nearest",
                origin="lower",
                extent=[0, n_sections, 0, n_samples],
                vmin=20,
                vmax=120,
            )
            ax4.set_xlabel("Section Index")
            ax4.set_title(f"4. Post-Filtered (Sent to Kafka)\n({min_speed_kmh:.0f}-{max_speed_kmh:.0f} km/h only)")
            cbar4 = plt.colorbar(im4, ax=ax4, label="Speed (km/h)")

            # === PLOT 5: Direction 1 from post-filtered (Positive speeds) ===
            speed_data_positive = np.full((n_samples, n_sections), np.nan)

            # Fill detection zones with POSITIVE speed values that pass min/max filter
            for section_idx, (starts, ends) in enumerate(intervals_list):
                for start, end in zip(starts, ends):
                    # Get median speed for this detection zone (KEEP SIGN)
                    speed_slice = filtered_speed[section_idx, :, start:end]
                    median_speed = np.nanmedian(speed_slice)

                    # Only show if positive speed AND passes min/max filter
                    if not np.isnan(median_speed) and median_speed > 0:
                        abs_speed = abs(median_speed)
                        if min_speed_kmh <= abs_speed <= max_speed_kmh:
                            speed_data_positive[start:end, section_idx] = median_speed

            speed_masked_positive = np.ma.masked_invalid(speed_data_positive)

            im5 = ax5.imshow(
                speed_masked_positive,
                aspect="auto",
                cmap="viridis",
                interpolation="nearest",
                origin="lower",
                extent=[0, n_sections, 0, n_samples],
                vmin=20,
                vmax=120,
            )
            ax5.set_xlabel("Section Index")
            ax5.set_title(f"5. Direction 1 (Filtered Positive)\n({min_speed_kmh:.0f}-{max_speed_kmh:.0f} km/h)")
            cbar5 = plt.colorbar(im5, ax=ax5, label="Speed (km/h)")

            # === PLOT 6: Direction 2 from post-filtered (Negative speeds) ===
            speed_data_negative = np.full((n_samples, n_sections), np.nan)

            # Fill detection zones with NEGATIVE speed values that pass min/max filter
            for section_idx, (starts, ends) in enumerate(intervals_list):
                for start, end in zip(starts, ends):
                    # Get median speed for this detection zone (KEEP SIGN)
                    speed_slice = filtered_speed[section_idx, :, start:end]
                    median_speed = np.nanmedian(speed_slice)

                    # Only show if negative speed AND passes min/max filter (display as positive for visibility)
                    if not np.isnan(median_speed) and median_speed < 0:
                        abs_speed = abs(median_speed)
                        if min_speed_kmh <= abs_speed <= max_speed_kmh:
                            speed_data_negative[start:end, section_idx] = abs_speed

            speed_masked_negative = np.ma.masked_invalid(speed_data_negative)

            im6 = ax6.imshow(
                speed_masked_negative,
                aspect="auto",
                cmap="viridis",
                interpolation="nearest",
                origin="lower",
                extent=[0, n_sections, 0, n_samples],
                vmin=20,
                vmax=120,
            )
            ax6.set_xlabel("Section Index")
            ax6.set_title(f"6. Direction 2 (Filtered Negative)\n({min_speed_kmh:.0f}-{max_speed_kmh:.0f} km/h)")
            cbar6 = plt.colorbar(im6, ax=ax6, label="Speed (km/h)")

            # === Overlay count detections if available ===
            if count_data is not None:
                counts, count_intervals, count_timestamps = count_data
                logger.info(f"Count overlay: {len(counts)} sections, viz window: {n_samples} samples")

                # Detect if intervals are already aligned with viz window or need offset
                # Check max interval index across all sections
                max_interval_idx = 0
                for section_intervals in count_intervals:
                    if isinstance(section_intervals, tuple) and len(section_intervals) == 2:
                        starts, ends = section_intervals
                        if len(ends) > 0:
                            max_interval_idx = max(max_interval_idx, max(ends))

                viz_window_samples = n_samples

                # If max index is close to viz window size, intervals are already aligned
                # Otherwise they're from 6-minute window and need offset
                if max_interval_idx <= n_samples * 1.5:  # Allow some tolerance
                    # TEMPORARY: Intervals already match visualization window (no offset needed)
                    count_time_offset = 0
                    logger.info(f"Count intervals pre-aligned with viz window (max_idx={max_interval_idx})")
                else:
                    # Original: Count data from 6-minute window, need to extract tail
                    counting_window_samples = 3600  # 6 minutes at 10Hz
                    count_time_offset = counting_window_samples - viz_window_samples
                    logger.info(f"Count intervals from 6-min window (max_idx={max_interval_idx}, offset={count_time_offset})")

                total_count_markers = 0
                filtered_too_old = 0

                # Overlay on all relevant panels
                for ax, panel_name in [(ax2, "Detection"), (ax3, "All"), (ax4, "Filtered"),
                                       (ax5, "Dir1"), (ax6, "Dir2")]:
                    for section_idx, (section_counts, section_intervals) in enumerate(zip(counts, count_intervals)):
                        if section_counts is None or len(section_counts) == 0:
                            continue

                        if len(section_intervals) != 2:
                            continue

                        starts, ends = section_intervals

                        for count, start, end in zip(section_counts, starts, ends):
                            if count <= 0:
                                continue

                            # Only show counts that fall within the visualization time window
                            # Map from 6-minute buffer indices to 30-second viz indices
                            if start < count_time_offset:
                                filtered_too_old += 1
                                continue

                            viz_start = start - count_time_offset
                            viz_end = end - count_time_offset

                            if viz_start >= viz_window_samples:
                                continue

                            # Place marker at center of interval
                            time_center = (viz_start + viz_end) / 2
                            section_center = section_idx + 0.5

                            # Size marker by count value (clamp to reasonable range)
                            marker_size = min(max(count * 100, 50), 500)

                            # Color: yellow for visibility
                            ax.scatter(
                                section_center,
                                time_center,
                                s=marker_size,
                                c='yellow',
                                marker='*',
                                edgecolors='black',
                                linewidths=1,
                                alpha=0.8,
                                zorder=10
                            )
                            total_count_markers += 1

                logger.info(f"Count overlay: {filtered_too_old} filtered (outside viz window), {total_count_markers} markers shown")
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

            # Set secure permissions (owner read/write only)
            try:
                os.chmod(filepath, 0o644)  # Owner read/write, group/other read-only
            except Exception as e:
                logger.warning(f"Could not set permissions on {filepath}: {e}")

            logger.info(f"Saved waterfall visualization: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"Failed to generate waterfall plot: {e}", exc_info=True)
            if "fig" in locals():
                plt.close(fig)
            raise
