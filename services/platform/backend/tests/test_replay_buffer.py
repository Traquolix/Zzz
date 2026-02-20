"""
Tests for the time-shifted replay buffer and Kafka bridge transforms.
"""

import asyncio
import json
import time

import pytest

from apps.realtime.replay_buffer import ReplayBuffer
from apps.realtime.kafka_bridge import (
    transform_speed_message,
    transform_count_message,
    _parse_speed_message,
)


# ============================================================================
# transform_speed_message tests
# ============================================================================

class TestTransformSpeedMessage:
    """Test speed message transformation (dict input)."""

    def test_basic_speed_message(self):
        data = {
            'fiber_id': 'carros',
            'timestamp_ns': 1706000000_000_000_000,
            'speeds': [
                {'channel_number': 100, 'speed': 85.5},
                {'channel_number': 200, 'speed': -62.3},
            ],
            'channel_start': 0,
            'ai_metadata': {'engine_version': '1.0', 'spatial_points': 9, 'time_index': 0},
        }

        detections = transform_speed_message(data)
        assert len(detections) == 2

        d0 = detections[0]
        assert d0['fiberLine'] == 'carros'
        assert d0['channel'] == 100
        assert d0['speed'] == 85.5
        assert d0['direction'] == 0  # positive speed
        assert d0['count'] == 1
        assert d0['timestamp'] == 1706000000_000

        d1 = detections[1]
        assert d1['channel'] == 200
        assert d1['speed'] == 62.3  # abs()
        assert d1['direction'] == 1  # negative speed

    def test_nearby_channels_grouped(self):
        data = {
            'fiber_id': 'carros',
            'timestamp_ns': 1706000000_000_000_000,
            'speeds': [
                {'channel_number': 100, 'speed': 80.0},
                {'channel_number': 103, 'speed': 85.0},
                {'channel_number': 105, 'speed': 90.0},
            ],
            'channel_start': 0,
            'ai_metadata': {},
        }

        detections = transform_speed_message(data)
        assert len(detections) == 1
        assert detections[0]['count'] == 3
        assert detections[0]['channel'] == round((100 + 103 + 105) / 3)

    def test_empty_speeds(self):
        data = {
            'fiber_id': 'carros',
            'timestamp_ns': 1706000000_000_000_000,
            'speeds': [],
            'channel_start': 0,
        }
        assert transform_speed_message(data) == []

    def test_tuple_format_speeds(self):
        """Speed entries can be [ch, spd] tuples."""
        data = {
            'fiber_id': 'carros',
            'timestamp_ns': 1706000000_000_000_000,
            'speeds': [[100, 85.5], [200, -62.3]],
            'channel_start': 0,
        }
        detections = transform_speed_message(data)
        assert len(detections) == 2

    def test_parse_speed_message_valid(self):
        raw = json.dumps({'fiber_id': 'test', 'speeds': []}).encode()
        result = _parse_speed_message(raw)
        assert result is not None
        assert result['fiber_id'] == 'test'

    def test_parse_speed_message_invalid(self):
        assert _parse_speed_message(b'not json') is None
        assert _parse_speed_message(None) is None


# ============================================================================
# transform_count_message tests
# ============================================================================

class TestTransformCountMessage:
    """Test count message transformation."""

    def test_valid_count_message(self):
        raw = json.dumps({
            'fiber_id': 'carros',
            'channel_start': 1000,
            'channel_end': 1300,
            'count_timestamp_ns': 1706000030_000_000_000,
            'vehicle_count': 3.2,
            'engine_version': '1.0',
            'model_type': 'neural_network',
        }).encode()

        result = transform_count_message(raw)
        assert result is not None

        count_data, section_key, ts_ns = result
        assert count_data['fiberLine'] == 'carros'
        assert count_data['channelStart'] == 1000
        assert count_data['channelEnd'] == 1300
        assert count_data['vehicleCount'] == 3.2
        assert count_data['timestamp'] == 1706000030_000
        assert section_key == 'carros:1000'
        assert ts_ns == 1706000030_000_000_000

    def test_invalid_json(self):
        assert transform_count_message(b'not json') is None

    def test_missing_fields_use_defaults(self):
        raw = json.dumps({'fiber_id': 'test'}).encode()
        result = transform_count_message(raw)
        assert result is not None
        count_data, _, _ = result
        assert count_data['channelStart'] == 0
        assert count_data['channelEnd'] == 0
        assert count_data['vehicleCount'] == 0.0


# ============================================================================
# ReplayBuffer tests
# ============================================================================

class TestReplayBuffer:
    """Test the time-shifted replay buffer."""

    def test_ingest_speed_creates_batch(self):
        buf = ReplayBuffer()
        buf.ingest_speed(
            section_key='carros:0',
            timestamp_ns=1000_000_000_000,
            time_index=0,
            detections=[{'fiberLine': 'carros', 'channel': 100}],
        )
        assert buf.queue_size == 1
        assert buf.active_batches == 1

    def test_ingest_speed_empty_detections_ignored(self):
        buf = ReplayBuffer()
        buf.ingest_speed('carros:0', 1000_000_000_000, 0, [])
        assert buf.queue_size == 0

    def test_replay_ordering(self):
        """Messages should be ordered by timestamp within a batch."""
        buf = ReplayBuffer()
        base_ns = 1000_000_000_000

        # Ingest 3 messages at 100ms intervals
        for i in range(3):
            buf.ingest_speed(
                section_key='carros:0',
                timestamp_ns=base_ns + i * 100_000_000,  # 100ms apart
                time_index=i,
                detections=[{'channel': i}],
            )

        assert buf.queue_size == 3

        # The queue should have items ordered by replay_time
        items = sorted(buf._queue)
        assert items[0].replay_time < items[1].replay_time
        assert items[1].replay_time < items[2].replay_time

        # Spacing should be ~100ms
        spacing = items[1].replay_time - items[0].replay_time
        assert abs(spacing - 0.1) < 0.01

    def test_new_batch_on_time_index_zero(self):
        """time_index=0 should create a new batch tracker."""
        buf = ReplayBuffer()
        base_ns = 1000_000_000_000

        # First batch
        buf.ingest_speed('carros:0', base_ns, 0, [{'x': 1}])
        first_batch = buf._batches['carros:0']
        first_wall = first_batch.wall_start

        # Simulate time passing
        time.sleep(0.05)

        # New batch (time_index=0 again)
        buf.ingest_speed('carros:0', base_ns + 30_000_000_000, 0, [{'x': 2}])
        second_batch = buf._batches['carros:0']

        assert second_batch.wall_start > first_wall
        assert second_batch.first_ts_ns == base_ns + 30_000_000_000

    def test_new_batch_on_large_timestamp_gap(self):
        """Timestamp >35s from batch start should create new batch."""
        buf = ReplayBuffer()
        base_ns = 1000_000_000_000

        buf.ingest_speed('carros:0', base_ns, 0, [{'x': 1}])
        first_wall = buf._batches['carros:0'].wall_start

        time.sleep(0.05)

        # Message with timestamp 40s later (> 35s threshold)
        buf.ingest_speed('carros:0', base_ns + 40_000_000_000, 5, [{'x': 2}])
        assert buf._batches['carros:0'].wall_start > first_wall

    def test_count_uses_speed_batch_anchor(self):
        """Count messages should use the speed batch's timing anchor."""
        buf = ReplayBuffer()
        base_ns = 1000_000_000_000

        # Establish a speed batch
        buf.ingest_speed('carros:0', base_ns, 0, [{'x': 1}])
        batch_wall = buf._batches['carros:0'].wall_start

        # Ingest count at timestamp 15s into the batch
        buf.ingest_count('carros:0', base_ns + 15_000_000_000, {'count': 3.0})

        # The count item should be scheduled 15s after batch wall_start
        count_item = [item for item in buf._queue if item.channel == 'counts'][0]
        expected_time = batch_wall + 15.0
        assert abs(count_item.replay_time - expected_time) < 0.1

    def test_count_without_batch_gets_fallback(self):
        """Count without active speed batch should broadcast soon."""
        buf = ReplayBuffer()
        now = time.time()

        buf.ingest_count('unknown:0', 1000_000_000_000, {'count': 1.0})

        assert buf.queue_size == 1
        count_item = buf._queue[0]
        # Should be scheduled ~0.5s from now
        assert abs(count_item.replay_time - (now + 0.5)) < 0.2

    def test_concurrent_sections(self):
        """Multiple sections should maintain separate batch trackers."""
        buf = ReplayBuffer()
        base_ns = 1000_000_000_000

        buf.ingest_speed('carros:0', base_ns, 0, [{'x': 1}])
        buf.ingest_speed('mathis:0', base_ns + 5_000_000_000, 0, [{'x': 2}])

        assert buf.active_batches == 2
        assert 'carros:0' in buf._batches
        assert 'mathis:0' in buf._batches

    def test_cleanup_stale_batches(self):
        """Stale batch trackers should be removed."""
        buf = ReplayBuffer()
        base_ns = 1000_000_000_000

        buf.ingest_speed('carros:0', base_ns, 0, [{'x': 1}])

        # Force the batch to be old
        buf._batches['carros:0'].last_seen = time.time() - 120

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
        buf.ingest_speed('carros:0', now_ns, 0, [{'fiberLine': 'carros', 'channel': 100}])

        # Run drain briefly
        drain_task = asyncio.create_task(buf.drain(mock_broadcast))
        await asyncio.sleep(0.3)  # Let drain process
        buf.stop()
        try:
            await drain_task
        except asyncio.CancelledError:
            pass

        # Should have broadcast at least one detection batch
        detection_broadcasts = [b for b in broadcasts if b[0] == 'detections']
        assert len(detection_broadcasts) >= 1
        assert detection_broadcasts[0][1][0]['channel'] == 100

    @pytest.mark.asyncio
    async def test_drain_broadcasts_counts(self):
        """Drain should broadcast count messages individually."""
        buf = ReplayBuffer()
        broadcasts = []

        async def mock_broadcast(channel, data):
            broadcasts.append((channel, data))

        # Ingest a count that's due soon
        buf.ingest_count('carros:0', int(time.time() * 1e9), {'vehicleCount': 5.0})

        drain_task = asyncio.create_task(buf.drain(mock_broadcast))
        await asyncio.sleep(1.0)  # Count fallback is now + 0.5s
        buf.stop()
        try:
            await drain_task
        except asyncio.CancelledError:
            pass

        count_broadcasts = [b for b in broadcasts if b[0] == 'counts']
        assert len(count_broadcasts) >= 1
        assert count_broadcasts[0][1]['vehicleCount'] == 5.0
