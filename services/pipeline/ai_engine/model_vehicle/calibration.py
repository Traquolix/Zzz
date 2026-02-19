"""Calibration management for variable GLRT thresholds and coupling correction.

This module provides loading, caching, and application of per-fiber calibration data
for the AI engine. Calibration files are loaded from a mounted volume and applied
to GLRT results before thresholding.
"""

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


def _load_data_file(filepath: Path) -> dict:
    """Load calibration data from .npz (preferred) or .pkl (legacy fallback).

    Args:
        filepath: Path to calibration file (.pkl or .npz)

    Returns:
        Dictionary of calibration data
    """
    npz_path = filepath.with_suffix('.npz')
    if npz_path.exists():
        data = np.load(str(npz_path), allow_pickle=False)
        return dict(data)
    # Fallback to pickle with deprecation warning
    logger.warning(
        "Loading calibration from pickle file %s. "
        "Convert to .npz format for security. "
        "Pickle files will be unsupported in a future release.",
        filepath,
    )
    with open(filepath, 'rb') as f:
        return pickle.load(f)


@dataclass
class CalibrationData:
    """Container for per-fiber calibration data.

    This class holds threshold curves and coupling correction factors
    derived from calibration analysis. It provides methods to apply
    these calibrations to GLRT (Generalized Likelihood Ratio Test) results.

    Attributes:
        fiber_id: Fiber identifier (e.g., "carros")
        date: Calibration date string (YYYYMMDD)
        n_sections: Number of spatial sections
        threshold_curve: Per-section GLRT thresholds, shape (n_sections,)
        baseline: Per-section baseline GLRT (median), shape (n_sections,)
        noise_estimate: Per-section noise estimate (MAD), shape (n_sections,)
        threshold_method: Method used for threshold generation (e.g., "MAD")
        correction_factors: Optional per-section coupling corrections, shape (n_sections,)
        median_glrt: Optional reference GLRT from coupling calibration
    """

    fiber_id: str
    date: str
    n_sections: int
    threshold_curve: np.ndarray
    baseline: np.ndarray
    noise_estimate: np.ndarray
    threshold_method: str
    correction_factors: Optional[np.ndarray] = None
    median_glrt: Optional[float] = None

    def apply_coupling_correction(self, glrt: np.ndarray) -> np.ndarray:
        """Apply coupling correction to GLRT results.

        Multiplies each section's GLRT values by its coupling correction factor.
        This normalizes signal strength across sections to compensate for
        fiber physical variations (bends, splices, coupling differences).

        Args:
            glrt: GLRT array with shape (n_sections, n_samples)

        Returns:
            Corrected GLRT array with same shape, or original if no correction available
        """
        if self.correction_factors is None:
            return glrt

        # Broadcasting: correction_factors (n_sections,) × glrt (n_sections, n_samples)
        return glrt * self.correction_factors[:, np.newaxis]

    def get_threshold(self, section_idx: int) -> float:
        """Get threshold for a specific section.

        Args:
            section_idx: Section index (0-based)

        Returns:
            Threshold value for this section

        Raises:
            IndexError: If section_idx is out of range
        """
        if section_idx < 0 or section_idx >= self.n_sections:
            raise IndexError(
                f"Section {section_idx} out of range [0, {self.n_sections})"
            )
        return float(self.threshold_curve[section_idx])

    def apply_variable_threshold(self, glrt: np.ndarray) -> np.ndarray:
        """Apply per-section variable thresholds to GLRT.

        Creates a binary mask where GLRT values exceeding their section's
        threshold are marked as 1 (vehicle detected), others as 0.

        Args:
            glrt: GLRT array with shape (n_sections, n_samples)

        Returns:
            Binary detection mask with shape (n_sections, n_samples)
        """
        # Broadcasting: threshold_curve (n_sections,) vs glrt (n_sections, n_samples)
        threshold_broadcast = self.threshold_curve[:, np.newaxis]
        return (glrt >= threshold_broadcast).astype(np.float64)


class CalibrationManager:
    """Manages loading and caching of calibration data for multiple fibers.

    This class handles:
    - Loading threshold and coupling calibration from pickle files
    - Caching loaded calibrations in memory
    - Automatic selection of latest calibration files
    - Graceful handling of missing calibration data

    Calibration files are expected in this structure:
        {calibration_base_path}/{fiber_id}/{fiber_id}_{YYYYMMDD}_threshold.pkl
        {calibration_base_path}/{fiber_id}/{fiber_id}_{YYYYMMDD}_coupling.pkl

    The manager automatically selects the most recent files by modification time.

    Attributes:
        calibration_base_path: Root directory for calibration files
    """

    def __init__(self, calibration_base_path: str = "/app/calibration"):
        """Initialize calibration manager.

        Args:
            calibration_base_path: Root path to calibration directory
        """
        self.calibration_base_path = Path(calibration_base_path)
        self._cache: Dict[str, CalibrationData] = {}
        logger.info(f"CalibrationManager initialized: path={calibration_base_path}")

    def load_calibration(self, fiber_id: str) -> Optional[CalibrationData]:
        """Load calibration data for a fiber.

        Checks cache first, then loads from disk if not cached.
        Threshold calibration is required; coupling calibration is optional.

        Args:
            fiber_id: Fiber identifier (e.g., "carros")

        Returns:
            CalibrationData if threshold file found, None otherwise
        """
        # Check cache first
        if fiber_id in self._cache:
            logger.debug(f"Using cached calibration for '{fiber_id}'")
            return self._cache[fiber_id]

        # Look for calibration directory
        fiber_dir = self.calibration_base_path / fiber_id
        if not fiber_dir.exists():
            logger.warning(
                f"No calibration directory for fiber '{fiber_id}' at {fiber_dir}"
            )
            return None

        # Find latest calibration files
        threshold_file = self._find_latest_file(fiber_dir, "*_threshold.pkl")
        coupling_file = self._find_latest_file(fiber_dir, "*_coupling.pkl")

        if threshold_file is None:
            logger.warning(
                f"No threshold calibration file found for fiber '{fiber_id}' in {fiber_dir}"
            )
            return None

        try:
            # Load threshold calibration (required)
            threshold_data = _load_data_file(threshold_file)

            # Load coupling calibration (optional)
            coupling_data = None
            if coupling_file is not None:
                try:
                    coupling_data = _load_data_file(coupling_file)
                except Exception as e:
                    logger.warning(
                        f"Failed to load coupling calibration from {coupling_file}: {e}"
                    )

            # Build CalibrationData
            calibration = CalibrationData(
                fiber_id=fiber_id,
                date=threshold_data.get("date", "unknown"),
                n_sections=threshold_data["n_sections"],
                threshold_curve=np.array(
                    threshold_data["threshold_curve"], dtype=np.float64
                ),
                baseline=np.array(threshold_data["baseline"], dtype=np.float64),
                noise_estimate=np.array(
                    threshold_data["noise_estimate"], dtype=np.float64
                ),
                threshold_method=threshold_data.get("method", "unknown"),
                correction_factors=(
                    np.array(coupling_data["correction_factors"], dtype=np.float64)
                    if coupling_data
                    else None
                ),
                median_glrt=(
                    float(coupling_data["median_glrt"]) if coupling_data else None
                ),
            )

            # Cache and return
            self._cache[fiber_id] = calibration

            logger.info(
                f"Loaded calibration for '{fiber_id}': "
                f"threshold={threshold_file.name} ({calibration.n_sections} sections, "
                f"range [{calibration.threshold_curve.min():.1f}, {calibration.threshold_curve.max():.1f}]), "
                f"coupling={'Yes' if coupling_data else 'No'}"
            )

            return calibration

        except Exception as e:
            logger.error(f"Failed to load calibration for '{fiber_id}': {e}")
            return None

    def _find_latest_file(self, directory: Path, pattern: str) -> Optional[Path]:
        """Find the most recent file matching pattern.

        Args:
            directory: Directory to search
            pattern: Glob pattern for filename

        Returns:
            Path to most recent file, or None if no matches
        """
        files = list(directory.glob(pattern))
        if not files:
            return None

        # Sort by modification time, most recent first
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files[0]

    def clear_cache(self) -> None:
        """Clear the calibration cache.

        Useful for testing or if calibration files are updated at runtime.
        """
        self._cache.clear()
        logger.info("Calibration cache cleared")

    def get_cached_fiber_ids(self) -> list[str]:
        """Get list of fiber IDs currently cached.

        Returns:
            List of fiber IDs with loaded calibrations
        """
        return list(self._cache.keys())
