"""Shared fixtures for processor preprocessing tests.

Deterministic synthetic data, production-matching constants, and reusable
measurement dicts for all processor step and chain tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure pipeline root is on sys.path (mirrors ai_engine/conftest.py)
_pipeline_root = Path(__file__).resolve().parents[2]
if str(_pipeline_root) not in sys.path:
    sys.path.insert(0, str(_pipeline_root))

# ---------------------------------------------------------------------------
# Constants matching fibers.yaml production config
# ---------------------------------------------------------------------------
ORIGINAL_SAMPLING_RATE_HZ = 125.0
TEMPORAL_DECIMATION_FACTOR = 12
POST_DECIMATION_RATE_HZ = ORIGINAL_SAMPLING_RATE_HZ / TEMPORAL_DECIMATION_FACTOR  # 10.4167
SPATIAL_DECIMATION_FACTOR = 3
SCALE_FACTOR = 213.05
BANDPASS_LOW_HZ = 0.3
BANDPASS_HIGH_HZ = 2.0
CMR_WARMUP_SECONDS = 5.0

# Carros section "202Bis" — production channel bounds
SECTION_CHANNEL_START = 1200
SECTION_CHANNEL_STOP = 2748
SECTION_RAW_CHANNELS = SECTION_CHANNEL_STOP - SECTION_CHANNEL_START  # 1548
SECTION_DECIMATED_CHANNELS = len(range(0, SECTION_RAW_CHANNELS, SPATIAL_DECIMATION_FACTOR))  # 516

# Typical raw batch shape from DAS instrument
TOTAL_FIBER_CHANNELS = 5427
RAW_BATCH_SAMPLES = 24  # samples per raw Kafka message at 125 Hz


# ---------------------------------------------------------------------------
# Deterministic RNG
# ---------------------------------------------------------------------------
@pytest.fixture
def rng() -> np.random.Generator:
    """Deterministic numpy RNG for reproducible tests."""
    return np.random.default_rng(seed=42)


# ---------------------------------------------------------------------------
# Synthetic data fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def raw_batch(rng) -> np.ndarray:
    """Simulated raw DAS batch: (24 samples, 5427 channels) float64."""
    return rng.standard_normal((RAW_BATCH_SAMPLES, TOTAL_FIBER_CHANNELS)).astype(np.float64)


@pytest.fixture
def section_batch(rng) -> np.ndarray:
    """Post-spatial-decimation batch: (24 samples, 516 channels) float64."""
    return rng.standard_normal((RAW_BATCH_SAMPLES, SECTION_DECIMATED_CHANNELS)).astype(np.float64)


@pytest.fixture
def small_batch(rng) -> np.ndarray:
    """Small batch for fast tests: (24 samples, 20 channels) float64."""
    return rng.standard_normal((RAW_BATCH_SAMPLES, 20)).astype(np.float64)


@pytest.fixture
def timestamps_ns() -> list[int]:
    """Nanosecond timestamps for RAW_BATCH_SAMPLES at 125 Hz."""
    base = 1_700_000_000_000_000_000
    interval = int(1e9 / ORIGINAL_SAMPLING_RATE_HZ)
    return [base + i * interval for i in range(RAW_BATCH_SAMPLES)]


def make_measurement(
    values: np.ndarray,
    *,
    fiber_id: str = "test_fiber",
    sampling_rate_hz: float = ORIGINAL_SAMPLING_RATE_HZ,
    channel_start: int = 0,
    timestamps_ns: list[int] | None = None,
) -> dict:
    """Build a measurement dict matching what ProcessingChain steps expect."""
    m = {
        "fiber_id": fiber_id,
        "values": values,
        "sampling_rate_hz": sampling_rate_hz,
        "channel_start": channel_start,
    }
    if timestamps_ns is not None:
        m["timestamps_ns"] = timestamps_ns
    return m
