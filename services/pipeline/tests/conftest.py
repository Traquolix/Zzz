"""Shared test fixtures."""

import pytest
import tempfile
from pathlib import Path

from shared.service_config import ServiceConfig


@pytest.fixture
def service_config():
    """Default service config for testing."""
    return ServiceConfig(
        kafka_bootstrap_servers="localhost:9092",
        schema_registry_url="http://localhost:8081",
        input_topic="test.input",
        output_topic="test.output",
        max_retries=3,
        initial_retry_delay=0.01,
        max_retry_delay=0.1,
        retry_backoff_multiplier=2.0,
    )


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for test configs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_measurement():
    """Sample DAS measurement data for processing tests."""
    return {
        "fiber_id": "test_fiber",
        "timestamp_ns": 1000000000000,
        "sampling_rate_hz": 50.0,
        "channel_start": 0,
        "values": [0.1 * i for i in range(100)],
    }
