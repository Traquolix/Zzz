"""Integration tests for Kafka connectivity and basic message flow.

These tests verify that:
1. Kafka is reachable and healthy
2. Topics can be created and deleted
3. Messages can be produced and consumed
4. Cleanup works correctly

All test resources are automatically cleaned up after each test.
"""

import pytest
import json
import time
from tests.integration.conftest import wait_for_message


class TestKafkaConnectivity:
    """Test basic Kafka connectivity."""

    def test_topic_creation_and_deletion(self, kafka_context):
        """Should be able to create and delete topics."""
        topic = kafka_context.create_topic("test_crud")

        # Wait for metadata to propagate
        import time
        time.sleep(1)

        # Verify topic exists
        metadata = kafka_context.admin.list_topics(timeout=10)
        assert topic in metadata.topics

        # Cleanup happens automatically via fixture

    def test_produce_and_consume_message(self, kafka_context):
        """Should be able to produce and consume a message."""
        topic = kafka_context.create_topic("test_produce_consume")

        # Produce a message
        producer = kafka_context.create_producer()
        test_message = {"test": "data", "timestamp": time.time()}
        producer.produce(
            topic,
            key="test_key",
            value=json.dumps(test_message).encode("utf-8"),
        )
        producer.flush(timeout=10)

        # Consume the message
        consumer = kafka_context.create_consumer([topic])
        received = wait_for_message(consumer, timeout=10)
        consumer.close()

        assert received["key"] == "test_key"
        assert json.loads(received["value"]) == test_message

    def test_multiple_messages_ordering(self, kafka_context):
        """Messages should be received in order within a partition."""
        topic = kafka_context.create_topic("test_ordering")

        producer = kafka_context.create_producer()

        # Produce 10 messages with same key (same partition)
        messages = [{"seq": i, "data": f"message_{i}"} for i in range(10)]
        for msg in messages:
            producer.produce(
                topic,
                key="same_key",
                value=json.dumps(msg).encode("utf-8"),
            )
        producer.flush(timeout=10)

        # Consume and verify order
        consumer = kafka_context.create_consumer([topic])
        received = []
        for _ in range(10):
            msg = wait_for_message(consumer, timeout=10)
            received.append(json.loads(msg["value"]))
        consumer.close()

        # Verify order preserved
        for i, msg in enumerate(received):
            assert msg["seq"] == i

    def test_consumer_group_offset_tracking(self, kafka_context):
        """Consumer should track offsets correctly."""
        from confluent_kafka import Consumer, KafkaError

        topic = kafka_context.create_topic("test_offsets")

        # Produce messages
        producer = kafka_context.create_producer()
        for i in range(5):
            producer.produce(topic, value=f"msg_{i}".encode())
        producer.flush(timeout=10)

        # First consumer reads all messages and commits
        consumer1_config = {
            "bootstrap.servers": kafka_context.bootstrap_servers,
            "group.id": f"test-offsets-{kafka_context.test_id}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
        consumer1 = Consumer(consumer1_config)
        consumer1.subscribe([topic])

        messages_read = 0
        for _ in range(10):  # Try up to 10 polls
            msg = consumer1.poll(timeout=2.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                break
            messages_read += 1
            consumer1.commit(message=msg)
            if messages_read >= 5:
                break
        consumer1.close()

        assert messages_read == 5

        # Second consumer with same group should get no new messages
        consumer2 = Consumer(consumer1_config)
        consumer2.subscribe([topic])

        # Should timeout - no new messages (all committed)
        msg = consumer2.poll(timeout=3.0)
        consumer2.close()

        # Either None or partition EOF
        assert msg is None or (msg.error() and msg.error().code() == KafkaError._PARTITION_EOF)
