"""Shared fixtures for AI engine tests.

All fixtures use deterministic seeds so tests are reproducible across runs.
The DTAN model is loaded once per session (expensive) and shared across tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import torch

# Disable torch.compile for tests — CPAB has dtype mismatches that
# torch.compile's strict tracing exposes. The fixes in transformer.py/expm.py
# handle eager mode; full torch.compile compatibility requires deeper CPAB work.
torch._dynamo.config.disable = True

# Ensure pipeline root is on sys.path
_pipeline_root = Path(__file__).resolve().parents[2]
if str(_pipeline_root) not in sys.path:
    sys.path.insert(0, str(_pipeline_root))

from ai_engine.model_vehicle.model_T import Args_NN_model_all_channels  # noqa: E402
from ai_engine.model_vehicle.vehicle_speed import VehicleSpeedEstimator  # noqa: E402

# ---------------------------------------------------------------------------
# Constants matching fibers.yaml model_defaults
# ---------------------------------------------------------------------------
SAMPLING_RATE_HZ = 10.4167
WINDOW_SECONDS = 30
SAMPLES_PER_WINDOW = int(WINDOW_SECONDS * SAMPLING_RATE_HZ)  # 312
CHANNELS_PER_SECTION = 9
GAUGE_METERS = 15.3846
OVERLAP_SPACE = CHANNELS_PER_SECTION - 1  # 8 → step=1
GLRT_WINDOW = 20
CORR_THRESHOLD = 300.0
MIN_SPEED = 20.0
MAX_SPEED = 120.0
TIME_OVERLAP_RATIO = 0.25


# ---------------------------------------------------------------------------
# Model fixtures (session-scoped — loaded once)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def model_args() -> Args_NN_model_all_channels:
    """Model arguments matching production config."""
    return Args_NN_model_all_channels(
        data_window_length=SAMPLES_PER_WINDOW,
        gauge=GAUGE_METERS,
        Nch=CHANNELS_PER_SECTION,
        N_channels=OVERLAP_SPACE,
        fs=SAMPLING_RATE_HZ,
        exp_name="allignment_parameters_3_03_2026_30s_windows",
        version="best",
        bidirectional_rnn=True,
    )


@pytest.fixture(scope="session")
def estimator(model_args) -> VehicleSpeedEstimator:
    """Fully initialized VehicleSpeedEstimator matching production config."""
    return VehicleSpeedEstimator(
        model_args=model_args,
        ovr_time=TIME_OVERLAP_RATIO,
        glrt_win=GLRT_WINDOW,
        min_speed=MIN_SPEED,
        max_speed=MAX_SPEED,
        corr_threshold=CORR_THRESHOLD,
        bidirectional_detection=True,
    )


# ---------------------------------------------------------------------------
# Synthetic data fixtures (deterministic)
# ---------------------------------------------------------------------------
@pytest.fixture
def rng() -> np.random.Generator:
    """Deterministic numpy RNG for reproducible tests."""
    return np.random.default_rng(seed=42)


@pytest.fixture
def synthetic_section_data(rng) -> np.ndarray:
    """Single section of synthetic DAS data: (50 channels, 312 time samples).

    50 channels with Nch=9 and step=1 produces 42 spatial windows,
    matching a typical small section.
    """
    return rng.standard_normal((50, SAMPLES_PER_WINDOW)).astype(np.float64)


@pytest.fixture
def synthetic_wide_data(rng) -> np.ndarray:
    """Wider section: (100 channels, 312 time samples) → 92 spatial windows."""
    return rng.standard_normal((100, SAMPLES_PER_WINDOW)).astype(np.float64)


@pytest.fixture
def synthetic_timestamps() -> np.ndarray:
    """Timestamp array matching SAMPLES_PER_WINDOW."""
    return np.arange(SAMPLES_PER_WINDOW, dtype=np.float64)


@pytest.fixture
def synthetic_timestamps_ns() -> np.ndarray:
    """Nanosecond timestamps matching SAMPLES_PER_WINDOW."""
    sample_duration_ns = int(1e9 / SAMPLING_RATE_HZ)
    base = 1_700_000_000_000_000_000  # arbitrary epoch
    return np.arange(SAMPLES_PER_WINDOW, dtype=np.int64) * sample_duration_ns + base


# ---------------------------------------------------------------------------
# Helper for torch determinism
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def torch_deterministic():
    """Set torch to deterministic mode for reproducible results."""
    torch.manual_seed(42)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(42)
    torch.use_deterministic_algorithms(False)  # CPAB uses non-deterministic ops
    yield
