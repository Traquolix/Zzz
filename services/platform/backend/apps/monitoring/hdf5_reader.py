"""
HDF5 reader utility for SHM spectral data.

Reads spectral data from HDF5 files in the format:
- spectra: 2D array (Nt x Nfreqs) of power values
- freqs: 1D array of frequency bin centers (Hz)
- t0: start timestamp (ISO format)
- t: 1D array of time offsets in seconds since t0
"""

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import h5py
import numpy as np

logger = logging.getLogger(__name__)

# Default sample data path
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "shm"
DEFAULT_SAMPLE_FILE = DATA_DIR / "sample_milo.h5"

# In-process cache for HDF5 data (static file, never changes at runtime).
# Avoids re-reading 131 MB from disk on every request.
_spectral_cache: dict[str, "SpectralData"] = {}
_peak_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
_cache_lock = threading.Lock()


@dataclass
class SpectralData:
    """Container for spectral time series data."""

    spectra: np.ndarray  # Shape: (Nt, Nfreqs)
    freqs: np.ndarray  # Shape: (Nfreqs,)
    t0: datetime  # Start timestamp
    dt: np.ndarray  # Time offsets in seconds, shape: (Nt,)

    @property
    def num_time_samples(self) -> int:
        return int(self.spectra.shape[0])

    @property
    def num_freq_bins(self) -> int:
        return int(self.spectra.shape[1])

    @property
    def freq_range(self) -> tuple[float, float]:
        return float(self.freqs[0]), float(self.freqs[-1])

    @property
    def duration_seconds(self) -> float:
        return float(self.dt[-1] - self.dt[0])

    def get_timestamps(self) -> list[datetime]:
        """Convert time offsets to absolute timestamps."""
        from datetime import timedelta

        return [self.t0 + timedelta(seconds=float(t)) for t in self.dt]

    def get_peak_frequencies(self) -> tuple[np.ndarray, np.ndarray]:
        """
        Extract the fundamental peak frequency for each time sample.

        Uses Martijn's method: scipy.signal.find_peaks to identify spectral
        peaks, then returns the first (lowest frequency) peak for each spectrum.
        This typically corresponds to the fundamental mode around ~1.15 Hz.

        Returns:
            Tuple of (peak_freqs, peak_powers) arrays.
        """
        import scipy.signal as sp

        log_spectra = np.log10(self.spectra + 1e-10)
        df = self.freqs[1] - self.freqs[0]

        # Peak finding parameters from Martijn's method
        kwargs = {"prominence": 0.4, "distance": int(0.1 / df)}

        peak_freqs = []
        peak_powers = []

        for i, spec in enumerate(log_spectra):
            peaks, _ = sp.find_peaks(spec, **kwargs)
            if len(peaks) > 0:
                # Martijn's method: take first peak (lowest frequency)
                first_peak_idx = peaks[0]
                peak_freqs.append(self.freqs[first_peak_idx])
                peak_powers.append(self.spectra[i, first_peak_idx])
            else:
                # Fallback if no peaks found: use NaN to indicate missing data
                peak_freqs.append(np.nan)
                peak_powers.append(np.nan)

        return np.array(peak_freqs), np.array(peak_powers)

    def downsample_time(self, target_samples: int) -> "SpectralData":
        """
        Downsample the time axis to reduce data size.

        Args:
            target_samples: Target number of time samples.

        Returns:
            New SpectralData with downsampled time axis.
        """
        if target_samples >= self.num_time_samples:
            return self

        # Use linear interpolation indices
        indices = np.linspace(0, self.num_time_samples - 1, target_samples, dtype=int)
        return SpectralData(
            spectra=self.spectra[indices],
            freqs=self.freqs,
            t0=self.t0,
            dt=self.dt[indices],
        )

    def downsample_freq(self, target_bins: int) -> "SpectralData":
        """
        Downsample the frequency axis to reduce data size.

        Args:
            target_bins: Target number of frequency bins.

        Returns:
            New SpectralData with downsampled frequency axis.
        """
        if target_bins >= self.num_freq_bins:
            return self

        indices = np.linspace(0, self.num_freq_bins - 1, target_bins, dtype=int)
        return SpectralData(
            spectra=self.spectra[:, indices],
            freqs=self.freqs[indices],
            t0=self.t0,
            dt=self.dt,
        )

    def slice_time(self, start_idx: int, end_idx: int) -> "SpectralData":
        """Get a time slice of the data, adjusting t0 to the new start."""
        from datetime import timedelta

        # Get the time offset at the start index
        new_start_offset = self.dt[start_idx]
        # Create new t0 at the slice start
        new_t0 = self.t0 + timedelta(seconds=float(new_start_offset))
        # Adjust dt values to be relative to new t0
        new_dt = self.dt[start_idx:end_idx] - new_start_offset

        return SpectralData(
            spectra=self.spectra[start_idx:end_idx],
            freqs=self.freqs,
            t0=new_t0,
            dt=new_dt,
        )

    def to_dict(self, log_scale: bool = True) -> dict:
        """
        Convert to JSON-serializable dictionary.

        Args:
            log_scale: If True, apply log10 to spectra values.
        """
        spectra = self.spectra
        if log_scale:
            # Avoid log(0) by adding small epsilon
            spectra = np.log10(spectra + 1e-10)

        return {
            "spectra": spectra.tolist(),
            "freqs": self.freqs.tolist(),
            "t0": self.t0.isoformat(),
            "dt": self.dt.tolist(),
            "numTimeSamples": self.num_time_samples,
            "numFreqBins": self.num_freq_bins,
            "freqRange": list(self.freq_range),
            "durationSeconds": self.duration_seconds,
        }


def load_spectral_data(filepath: Optional[Path] = None) -> SpectralData:
    """
    Load spectral data from an HDF5 file.

    Results are cached in process memory keyed by file path — the sample HDF5
    is static and never changes at runtime, so this avoids re-reading ~131 MB
    from disk on every request.

    Args:
        filepath: Path to HDF5 file. Uses default sample file if not provided.

    Returns:
        SpectralData object containing the loaded data.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        KeyError: If required datasets are missing.
    """
    if filepath is None:
        filepath = DEFAULT_SAMPLE_FILE

    cache_key = str(filepath)
    cached = _spectral_cache.get(cache_key)
    if cached is not None:
        return cached

    if not filepath.exists():
        raise FileNotFoundError(f"HDF5 file not found: {filepath}")

    with h5py.File(filepath, "r") as f:
        spectra = f["spectra"][...]
        freqs = f["freqs"][...]
        t0_str = f.attrs["t0"]
        dt = f["t"][...]

    # Parse t0 timestamp
    if isinstance(t0_str, bytes):
        t0_str = t0_str.decode("utf-8")
    t0 = datetime.fromisoformat(t0_str)

    # dt values need to be multiplied by 1e9 to get actual seconds
    dt_seconds = dt * 1e9

    result = SpectralData(spectra=spectra, freqs=freqs, t0=t0, dt=dt_seconds)

    with _cache_lock:
        _spectral_cache[cache_key] = result
        logger.info(
            "Cached HDF5 spectral data: %s (%d samples)", filepath.name, result.num_time_samples
        )

    return result


def load_peak_frequencies(filepath: Optional[Path] = None) -> tuple[np.ndarray, np.ndarray]:
    """
    Load and cache peak frequencies for the full dataset.

    Running scipy find_peaks on all ~10,754 spectra is expensive. This function
    caches the result so subsequent requests (including time-filtered comparisons)
    can slice the cached arrays instead of recomputing.

    Returns:
        Tuple of (peak_freqs, peak_powers) arrays for the full dataset.
    """
    if filepath is None:
        filepath = DEFAULT_SAMPLE_FILE

    cache_key = str(filepath)
    cached = _peak_cache.get(cache_key)
    if cached is not None:
        return cached

    data = load_spectral_data(filepath)
    peak_freqs, peak_powers = data.get_peak_frequencies()

    with _cache_lock:
        _peak_cache[cache_key] = (peak_freqs, peak_powers)
        logger.info("Cached peak frequencies: %s (%d peaks)", filepath.name, len(peak_freqs))

    return peak_freqs, peak_powers


def get_spectral_summary(filepath: Optional[Path] = None) -> dict:
    """
    Get summary statistics without loading full data.

    Args:
        filepath: Path to HDF5 file.

    Returns:
        Dictionary with summary information.
    """
    if filepath is None:
        filepath = DEFAULT_SAMPLE_FILE

    if not filepath.exists():
        raise FileNotFoundError(f"HDF5 file not found: {filepath}")

    with h5py.File(filepath, "r") as f:
        spectra_shape = f["spectra"].shape
        freqs = f["freqs"][...]
        t0_str = f.attrs["t0"]
        dt = f["t"][...]

    if isinstance(t0_str, bytes):
        t0_str = t0_str.decode("utf-8")

    # dt values need to be multiplied by 1e9 to get actual seconds
    dt_seconds = dt * 1e9

    # Parse t0 to calculate end time
    t0_dt = datetime.fromisoformat(t0_str)
    from datetime import timedelta

    end_dt = t0_dt + timedelta(seconds=float(dt_seconds[-1]))

    return {
        "numTimeSamples": spectra_shape[0],
        "numFreqBins": spectra_shape[1],
        "freqRange": [float(freqs[0]), float(freqs[-1])],
        "t0": t0_str,
        "endTime": end_dt.isoformat(),
        "durationSeconds": float(dt_seconds[-1] - dt_seconds[0]),
    }


def sample_file_exists() -> bool:
    """Check if the default sample file exists."""
    return DEFAULT_SAMPLE_FILE.exists()
