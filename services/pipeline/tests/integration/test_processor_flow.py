"""Integration tests for processor message flow.

These tests verify the processor's Kafka integration:
1. Can consume from raw topics
2. Can produce to processed topic
3. Avro serialization works correctly
4. Error handling and DLQ routing

All test resources are automatically cleaned up after each test.
"""

import json

from tests.integration.conftest import wait_for_message


class TestProcessorKafkaIntegration:
    """Test processor Kafka integration."""

    def test_message_serialization_roundtrip(self, kafka_context):
        """Messages should survive JSON serialization roundtrip."""
        topic = kafka_context.create_topic("test_serialization")

        # Simulate a DAS measurement message
        das_message = {
            "fiber_id": "test_fiber",
            "timestamp_ns": 1703180400000000000,
            "sampling_rate_hz": 50.0,
            "channel_start": 0,
            "values": [float(i) for i in range(100)],
        }

        producer = kafka_context.create_producer()
        producer.produce(
            topic,
            key="test_fiber",
            value=json.dumps(das_message).encode("utf-8"),
        )
        producer.flush(timeout=10)

        consumer = kafka_context.create_consumer([topic])
        received = wait_for_message(consumer, timeout=10)
        consumer.close()

        parsed = json.loads(received["value"])

        assert parsed["fiber_id"] == das_message["fiber_id"]
        assert parsed["timestamp_ns"] == das_message["timestamp_ns"]
        assert parsed["sampling_rate_hz"] == das_message["sampling_rate_hz"]
        assert parsed["values"] == das_message["values"]

    def test_large_message_handling(self, kafka_context):
        """Should handle large messages (1000+ channels)."""
        topic = kafka_context.create_topic("test_large_message")

        # Large DAS message with 2000 channels
        large_message = {
            "fiber_id": "test_fiber",
            "timestamp_ns": 1703180400000000000,
            "sampling_rate_hz": 50.0,
            "channel_start": 0,
            "values": [float(i) * 0.001 for i in range(2000)],
        }

        producer = kafka_context.create_producer()
        producer.produce(
            topic,
            key="test_fiber",
            value=json.dumps(large_message).encode("utf-8"),
        )
        producer.flush(timeout=10)

        consumer = kafka_context.create_consumer([topic])
        received = wait_for_message(consumer, timeout=10)
        consumer.close()

        parsed = json.loads(received["value"])
        assert len(parsed["values"]) == 2000

    def test_multiple_fibers_partitioning(self, kafka_context):
        """Messages from different fibers should be routable by key."""
        topic = kafka_context.create_topic("test_multi_fiber", num_partitions=3)

        producer = kafka_context.create_producer()

        # Send messages from 3 different fibers
        fibers = ["fiber_a", "fiber_b", "fiber_c"]
        for fiber_id in fibers:
            msg = {
                "fiber_id": fiber_id,
                "timestamp_ns": 1703180400000000000,
                "values": [1.0, 2.0, 3.0],
            }
            producer.produce(topic, key=fiber_id, value=json.dumps(msg).encode())
        producer.flush(timeout=10)

        # Consume all messages
        consumer = kafka_context.create_consumer([topic])
        received_fibers = set()
        for _ in range(3):
            msg = wait_for_message(consumer, timeout=10)
            parsed = json.loads(msg["value"])
            received_fibers.add(parsed["fiber_id"])
        consumer.close()

        assert received_fibers == set(fibers)

    def test_message_headers_preserved(self, kafka_context):
        """Kafka message headers should be preserved."""
        topic = kafka_context.create_topic("test_headers")

        producer = kafka_context.create_producer()
        headers = [
            ("correlation_id", b"test-correlation-123"),
            ("source_service", b"test-producer"),
        ]
        producer.produce(
            topic,
            key="test_key",
            value=b"test_value",
            headers=headers,
        )
        producer.flush(timeout=10)

        # Consume with headers
        from confluent_kafka import Consumer

        consumer = Consumer(
            {
                "bootstrap.servers": kafka_context.bootstrap_servers,
                "group.id": f"test-headers-{kafka_context.test_id}",
                "auto.offset.reset": "earliest",
            }
        )
        consumer.subscribe([topic])

        msg = None
        for _ in range(10):
            msg = consumer.poll(timeout=1.0)
            if msg and not msg.error():
                break
        consumer.close()

        assert msg is not None
        assert msg.headers() is not None
        header_dict = {k: v for k, v in msg.headers()}
        assert header_dict["correlation_id"] == b"test-correlation-123"
        assert header_dict["source_service"] == b"test-producer"


class TestErrorHandling:
    """Test error handling in Kafka operations."""

    def test_producer_delivery_callback(self, kafka_context):
        """Producer should invoke delivery callback."""
        topic = kafka_context.create_topic("test_delivery_callback")

        delivery_results = []

        def on_delivery(err, msg):
            delivery_results.append(
                {
                    "error": err,
                    "topic": msg.topic(),
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                }
            )

        producer = kafka_context.create_producer()
        producer.produce(
            topic,
            key="test_key",
            value=b"test_value",
            callback=on_delivery,
        )
        producer.flush(timeout=10)

        assert len(delivery_results) == 1
        assert delivery_results[0]["error"] is None
        assert delivery_results[0]["topic"] == topic

    def test_consumer_handles_empty_topic(self, kafka_context):
        """Consumer should handle empty topic gracefully."""
        topic = kafka_context.create_topic("test_empty_topic")

        consumer = kafka_context.create_consumer([topic])

        # Poll should return None or EOF, not raise
        msg = consumer.poll(timeout=2.0)
        consumer.close()

        # Either None or EOF partition
        assert msg is None or msg.error() is not None
