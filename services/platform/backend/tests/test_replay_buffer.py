"""
Tests for the time-shifted replay buffer and Kafka bridge transforms.
"""

import asyncio
import time

import pytest

from apps.realtime.kafka_bridge import (
    _parse_detection_message,
    transform_detection_message,
)
from apps.realtime.replay_buffer import ReplayBuffer

# ============================================================================
# transform_detection_message tests
# ============================================================================


class TestTransformDetectionMessage:
    """Test unified detection message transformation (dict input)."""

    def test_basic_detection_forward(self):
        """Direction 1 (forward) from AI engine maps to 0 for frontend."""
        data = {
            "fiber_id": "carros",
            "timestamp_ns": 1706000000_000_000_000,
            "channel": 100,
            "speed_kmh": 85.5,
            "direction": 1,  # AI engine forward
            "vehicle_count": 2.0,
            "n_cars": 1.0,
            "n_trucks": 1.0,
            "glrt_max": 15000.0,
            "engine_version": "1.0",
        }

        detections = transform_detection_message(data)
        assert len(detections) == 1

        d0 = detections[0]
        assert d0["fiberLine"] == "carros:0"  # direction 1 -> 0
        assert d0["channel"] == 100
        assert d0["speed"] == 85.5
        assert d0["direction"] == 0
        assert d0["count"] == 2.0
        assert d0["nCars"] == 1.0
        assert d0["nTrucks"] == 1.0
        assert d0["timestamp"] == 1706000000_000

    def test_basic_detection_reverse(self):
        """Direction 2 (reverse) from AI engine maps to 1 for frontend."""
        data = {
            "fiber_id": "carros",
            "timestamp_ns": 1706000000_000_000_000,
            "channel": 200,
            "speed_kmh": 62.3,
            "direction": 2,  # AI engine reverse
            "vehicle_count": 1.0,
            "n_cars": 1.0,
            "n_trucks": 0.0,
        }

        detections = transform_detection_message(data)
        assert len(detections) == 1

        d0 = detections[0]
        assert d0["fiberLine"] == "carros:1"  # direction 2 -> 1
        assert d0["channel"] == 200
        assert d0["speed"] == 62.3
        assert d0["direction"] == 1

    def test_direction_zero_treated_as_forward(self):
        """Direction 0 (unknown/legacy) maps to 0."""
        data = {
            "fiber_id": "carros",
            "timestamp_ns": 1706000000_000_000_000,
            "channel": 100,
            "speed_kmh": 80.0,
            "direction": 0,
        }
        detections = transform_detection_message(data)
        assert detections[0]["direction"] == 0

    def test_defaults_for_missing_fields(self):
        """Missing fields should use sensible defaults."""
        data = {
            "fiber_id": "carros",
            "timestamp_ns": 1706000000_000_000_000,
        }
        detections = transform_detection_message(data)
        assert len(detections) == 1
        d0 = detections[0]
        assert d0["channel"] == 0
        assert d0["speed"] == 0.0
        assert d0["count"] == 1.0  # default vehicle_count
        assert d0["nCars"] == 0.0
        assert d0["nTrucks"] == 0.0

    def test_parse_detection_message_valid(self):
        """_parse_detection_message expects Avro-deserialized dict, not bytes."""
        data = {"fiber_id": "test", "channel": 100}
        result = _parse_detection_message(data)
        assert result is not None
        assert result["fiber_id"] == "test"

    def test_parse_detection_message_invalid(self):
        # bytes are rejected (Avro deserializer yields dicts, not bytes)
        assert _parse_detection_message(b"not json") is None
        assert _parse_detection_message(None) is None


# ============================================================================
# ReplayBuffer tests
# ============================================================================


class TestReplayBuffer:
    """Test the time-shifted replay buffer."""

    def test_ingest_detection_creates_batch(self):
        buf = ReplayBuffer()
        buf.ingest_detection(
            section_key="carros:0",
            timestamp_ns=1000_000_000_000,
            detections=[{"fiberLine": "carros", "channel": 100}],
        )
        assert buf.queue_size == 1
        assert buf.active_batches == 1

    def test_ingest_detection_empty_detections_ignored(self):
        buf = ReplayBuffer()
        buf.ingest_detection("carros:0", 1000_000_000_000, [])
        assert buf.queue_size == 0

    def test_replay_ordering(self):
        """Messages should be ordered by timestamp within a batch."""
        buf = ReplayBuffer()
        base_ns = 1000_000_000_000

        # Ingest 3 messages at 100ms intervals
        for i in range(3):
            buf.ingest_detection(
                section_key="carros:0",
                timestamp_ns=base_ns + i * 100_000_000,  # 100ms apart
                detections=[{"channel": i}],
            )

        assert buf.queue_size == 3

        # The queue should have items ordered by replay_time
        items = sorted(buf._queue)
        assert items[0].replay_time < items[1].replay_time
        assert items[1].replay_time < items[2].replay_time

        # Spacing should be ~100ms
        spacing = items[1].replay_time - items[0].replay_time
        assert abs(spacing - 0.1) < 0.01

    def test_new_batch_on_large_timestamp_gap(self):
        """Timestamp >35s from batch start should create new batch."""
        buf = ReplayBuffer()
        base_ns = 1000_000_000_000

        buf.ingest_detection("carros:0", base_ns, [{"x": 1}])
        first_wall = buf._batches["carros:0"].wall_start

        time.sleep(0.05)

        # Message with timestamp 40s later (> 35s threshold)
        buf.ingest_detection("carros:0", base_ns + 40_000_000_000, [{"x": 2}])
        assert buf._batches["carros:0"].wall_start > first_wall

    def test_same_batch_within_window(self):
        """Messages within 35s should stay in the same batch."""
        buf = ReplayBuffer()
        base_ns = 1000_000_000_000

        buf.ingest_detection("carros:0", base_ns, [{"x": 1}])
        first_batch = buf._batches["carros:0"]
        first_wall = first_batch.wall_start

        # Message 30s later (< 35s threshold) — same batch
        buf.ingest_detection("carros:0", base_ns + 30_000_000_000, [{"x": 2}])
        assert buf._batches["carros:0"].wall_start == first_wall

    def test_concurrent_sections(self):
        """Multiple sections should maintain separate batch trackers."""
        buf = ReplayBuffer()
        base_ns = 1000_000_000_000

        buf.ingest_detection("carros:0", base_ns, [{"x": 1}])
        buf.ingest_detection("mathis:0", base_ns + 5_000_000_000, [{"x": 2}])

        assert buf.active_batches == 2
        assert "carros:0" in buf._batches
        assert "mathis:0" in buf._batches

    def test_cleanup_stale_batches(self):
        """Stale batch trackers should be removed."""
        buf = ReplayBuffer()
        base_ns = 1000_000_000_000

        buf.ingest_detection("carros:0", base_ns, [{"x": 1}])

        # Force the batch to be old
        buf._batches["carros:0"].last_seen = time.time() - 120

        buf.cleanup_stale_batches(max_age_s=60)
        assert buf.active_batches == 0

    @pytest.mark.asyncio
    async def test_drain_broadcasts_detections(self):
        """Drain should broadcast accumulated detections."""
        buf = ReplayBuffer()
        broadcasts = []

        async def mock_broadcast(channel, data):
            broadcasts.append((channel, data))

        # Ingest a detection that's due immediately
        now_ns = int(time.time() * 1e9)
        buf.ingest_detection("carros:0", now_ns, [{"fiberLine": "carros", "channel": 100}])

        # Run drain briefly
        drain_task = asyncio.create_task(buf.drain(mock_broadcast))
        await asyncio.sleep(0.3)  # Let drain process
        buf.stop()
        try:
            await drain_task
        except asyncio.CancelledError:
            pass

        # Should have broadcast at least one detection batch
        detection_broadcasts = [b for b in broadcasts if b[0] == "detections"]
        assert len(detection_broadcasts) >= 1
        assert detection_broadcasts[0][1][0]["channel"] == 100
