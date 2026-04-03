"""Avro schema conformance tests.

Verifies that detection messages produced by create_detection_messages
match the field names and types defined in das_detection.avsc.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ai_engine.message_utils import ProcessingContext, create_detection_messages

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "ai_engine" / "schema" / "das_detection.avsc"


@pytest.fixture
def avro_schema() -> dict:
    """Load the Avro schema definition."""
    if not _SCHEMA_PATH.exists():
        pytest.skip(f"Avro schema not found: {_SCHEMA_PATH}")
    return json.loads(_SCHEMA_PATH.read_text())


@pytest.fixture
def sample_detections() -> list[dict]:
    """Sample detections matching the full pipeline output."""
    return [
        {
            "section_idx": 0,
            "speed_kmh": 65.3,
            "direction": 0,
            "timestamp_ns": 1_700_000_000_000_000_000,
            "glrt_max": 4500.0,
            "vehicle_count": 2.0,
            "n_cars": 1.0,
            "n_trucks": 1.0,
            "strain_peak": 0.45,
            "strain_rms": 0.22,
        },
        {
            "section_idx": 5,
            "speed_kmh": 88.7,
            "direction": 1,
            "timestamp_ns": 1_700_000_005_000_000_000,
            "glrt_max": 7200.0,
            "vehicle_count": 1.0,
            "n_cars": 1.0,
            "n_trucks": 0.0,
            "strain_peak": 0.30,
            "strain_rms": 0.15,
        },
    ]


class TestAvroSchemaConformance:
    """Tests that detection messages conform to the Avro schema."""

    def test_top_level_fields_present(self, avro_schema, sample_detections):
        """Message payload must contain all top-level schema fields."""
        ctx = ProcessingContext()
        ctx.channel_start = 100
        ctx.channel_step = 3

        messages = create_detection_messages(
            fiber_id="carros",
            detections=sample_detections,
            ctx=ctx,
            service_name="ai-engine",
        )

        assert len(messages) == 1
        payload = messages[0].payload

        schema_fields = {f["name"] for f in avro_schema["fields"]}
        payload_fields = set(payload.keys())

        missing = schema_fields - payload_fields
        assert not missing, f"Missing top-level fields in payload: {missing}"

    def test_detection_fields_match_schema(self, avro_schema, sample_detections):
        """Each detection in the payload must contain all schema-defined fields."""
        ctx = ProcessingContext()
        ctx.channel_start = 100
        ctx.channel_step = 3

        messages = create_detection_messages(
            fiber_id="carros",
            detections=sample_detections,
            ctx=ctx,
            service_name="ai-engine",
        )

        # Extract Detection record schema
        detection_schema = None
        for field in avro_schema["fields"]:
            if field["name"] == "detections":
                detection_schema = field["type"]["items"]
                break

        assert detection_schema is not None, "No 'detections' field in schema"

        expected_fields = {f["name"] for f in detection_schema["fields"]}

        for det in messages[0].payload["detections"]:
            det_fields = set(det.keys())
            missing = expected_fields - det_fields
            assert not missing, f"Detection missing schema fields: {missing}"

    def test_field_types(self, avro_schema, sample_detections):
        """Detection field types must match Avro schema expectations."""
        ctx = ProcessingContext()
        ctx.channel_start = 100
        ctx.channel_step = 3

        messages = create_detection_messages(
            fiber_id="carros",
            detections=sample_detections,
            ctx=ctx,
            service_name="ai-engine",
        )

        det = messages[0].payload["detections"][0]

        # Type mapping from Avro to Python
        type_checks = {
            "timestamp_ns": (int, np.integer),
            "channel": (int, np.integer),
            "speed_kmh": (float, int, np.floating),
            "direction": (int, np.integer),
            "vehicle_count": (float, int, np.floating),
            "n_cars": (float, int, np.floating),
            "n_trucks": (float, int, np.floating),
            "glrt_max": (float, int, np.floating),
            "strain_peak": (float, int, np.floating),
            "strain_rms": (float, int, np.floating),
        }

        for field, expected_types in type_checks.items():
            assert isinstance(det[field], expected_types), (
                f"Field '{field}' has type {type(det[field])}, expected one of {expected_types}"
            )

    def test_fiber_id_preserved(self, sample_detections):
        """fiber_id in message must match what was passed."""
        ctx = ProcessingContext()
        messages = create_detection_messages(
            fiber_id="promenade",
            detections=sample_detections,
            ctx=ctx,
            service_name="ai-engine",
        )
        assert messages[0].payload["fiber_id"] == "promenade"

    def test_engine_version_present(self, sample_detections):
        """engine_version field must be present in the payload."""
        ctx = ProcessingContext()
        messages = create_detection_messages(
            fiber_id="carros",
            detections=sample_detections,
            ctx=ctx,
            service_name="ai-engine",
        )
        assert "engine_version" in messages[0].payload

    def test_channel_mapping_in_schema(self, sample_detections):
        """Detection 'channel' field must reflect physical channel mapping."""
        ctx = ProcessingContext()
        ctx.channel_start = 200
        ctx.channel_step = 3

        messages = create_detection_messages(
            fiber_id="carros",
            detections=sample_detections,
            ctx=ctx,
            service_name="ai-engine",
        )

        for det_in, det_out in zip(
            sample_detections, messages[0].payload["detections"], strict=False
        ):
            expected_channel = 200 + det_in["section_idx"] * 3
            assert det_out["channel"] == expected_channel, (
                f"Channel mapping wrong: section_idx={det_in['section_idx']}, "
                f"expected channel={expected_channel}, got {det_out['channel']}"
            )
