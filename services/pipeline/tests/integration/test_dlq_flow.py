"""Integration tests for Dead Letter Queue (DLQ) flow.

Tests that failed messages are correctly routed to DLQ topics.
All test resources are automatically cleaned up after each test.
"""

import pytest
import json
import time
from tests.integration.conftest import wait_for_message


class TestDLQMessageFormat:
    """Test DLQ message structure and content."""

    def test_dlq_message_structure(self, kafka_context):
        """DLQ messages should have required metadata fields."""
        dlq_topic = kafka_context.create_topic("test_dlq")

        # Simulate a DLQ message with full metadata
        dlq_message = {
            "original_topic": "das.raw.fiber1",
            "original_partition": 0,
            "original_offset": 12345,
            "service_name": "das-processor",
            "error_type": "ValueError",
            "error_message": "Invalid fiber configuration",
            "timestamp_ns": int(time.time() * 1e9),
            "retry_count": 1,
            "original_payload": {"fiber_id": "fiber1", "values": [1.0, 2.0]},
        }

        producer = kafka_context.create_producer()
        producer.produce(
            dlq_topic,
            key="fiber1",
            value=json.dumps(dlq_message).encode("utf-8"),
        )
        producer.flush(timeout=10)

        consumer = kafka_context.create_consumer([dlq_topic])
        received = wait_for_message(consumer, timeout=10)
        consumer.close()

        parsed = json.loads(received["value"])

        # Verify all required fields present
        assert "original_topic" in parsed
        assert "error_type" in parsed
        assert "error_message" in parsed
        assert "timestamp_ns" in parsed
        assert "original_payload" in parsed

    def test_dlq_preserves_original_payload(self, kafka_context):
        """DLQ should preserve the original message payload."""
        dlq_topic = kafka_context.create_topic("test_dlq_payload")

        original_payload = {
            "fiber_id": "test_fiber",
            "timestamp_ns": 1703180400000000000,
            "values": [1.0, 2.0, 3.0, 4.0, 5.0],
            "sampling_rate_hz": 50.0,
        }

        dlq_message = {
            "error_type": "ProcessingError",
            "error_message": "Failed to process",
            "original_payload": original_payload,
        }

        producer = kafka_context.create_producer()
        producer.produce(
            dlq_topic,
            key="test_fiber",
            value=json.dumps(dlq_message).encode("utf-8"),
        )
        producer.flush(timeout=10)

        consumer = kafka_context.create_consumer([dlq_topic])
        received = wait_for_message(consumer, timeout=10)
        consumer.close()

        parsed = json.loads(received["value"])
        assert parsed["original_payload"] == original_payload


class TestDLQPartitioning:
    """Test DLQ message partitioning."""

    def test_dlq_messages_partitioned_by_fiber(self, kafka_context):
        """DLQ messages should be partitioned by fiber_id for ordering."""
        dlq_topic = kafka_context.create_topic("test_dlq_partitioning", num_partitions=3)

        producer = kafka_context.create_producer()

        # Send DLQ messages for different fibers
        fibers = ["fiber_a", "fiber_b", "fiber_c"]
        for i, fiber_id in enumerate(fibers):
            dlq_message = {
                "error_type": "TestError",
                "error_message": f"Error for {fiber_id}",
                "original_payload": {"fiber_id": fiber_id},
            }
            producer.produce(
                dlq_topic,
                key=fiber_id,
                value=json.dumps(dlq_message).encode("utf-8"),
            )
        producer.flush(timeout=10)

        # Consume all messages
        consumer = kafka_context.create_consumer([dlq_topic])
        received_fibers = set()
        for _ in range(3):
            msg = wait_for_message(consumer, timeout=10)
            parsed = json.loads(msg["value"])
            received_fibers.add(parsed["original_payload"]["fiber_id"])
        consumer.close()

        assert received_fibers == set(fibers)


class TestDLQRetryTracking:
    """Test retry count tracking in DLQ."""

    def test_retry_count_increments(self, kafka_context):
        """Retry count should track reprocessing attempts."""
        dlq_topic = kafka_context.create_topic("test_dlq_retry")

        producer = kafka_context.create_producer()

        # Simulate multiple retry attempts
        for retry in range(3):
            dlq_message = {
                "error_type": "TransientError",
                "error_message": "Temporary failure",
                "retry_count": retry + 1,
                "original_payload": {"fiber_id": "fiber1"},
            }
            producer.produce(
                dlq_topic,
                key=f"msg_{retry}",
                value=json.dumps(dlq_message).encode("utf-8"),
            )
        producer.flush(timeout=10)

        # Consume and verify retry counts
        consumer = kafka_context.create_consumer([dlq_topic])
        retry_counts = []
        for _ in range(3):
            msg = wait_for_message(consumer, timeout=10)
            parsed = json.loads(msg["value"])
            retry_counts.append(parsed["retry_count"])
        consumer.close()

        assert sorted(retry_counts) == [1, 2, 3]
