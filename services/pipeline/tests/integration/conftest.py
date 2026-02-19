"""Fixtures for integration tests.

IMPORTANT: These tests run against real Kafka. All test resources are cleaned up
after each test to avoid polluting production data.
"""

import os
import pytest
import uuid
import time
from typing import Generator, List
from dataclasses import dataclass
from confluent_kafka import Producer, Consumer, KafkaError
from confluent_kafka.admin import AdminClient, NewTopic

# Test topic prefix - easy to identify and clean up
TEST_TOPIC_PREFIX = "_test_integration_"


@dataclass
class KafkaTestContext:
    """Context for Kafka integration tests."""
    bootstrap_servers: str
    admin: AdminClient
    created_topics: List[str]
    test_id: str

    def create_topic(self, name: str, num_partitions: int = 1) -> str:
        """Create a test topic with unique suffix. Returns full topic name."""
        full_name = f"{TEST_TOPIC_PREFIX}{name}_{self.test_id}"
        topic = NewTopic(full_name, num_partitions=num_partitions, replication_factor=1)

        futures = self.admin.create_topics([topic])
        for topic_name, future in futures.items():
            try:
                future.result(timeout=10)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    raise

        self.created_topics.append(full_name)
        return full_name

    def create_producer(self, **kwargs) -> Producer:
        """Create a producer connected to test Kafka."""
        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "client.id": f"test-producer-{self.test_id}",
            **kwargs,
        }
        return Producer(config)

    def create_consumer(self, topics: List[str], **kwargs) -> Consumer:
        """Create a consumer subscribed to topics."""
        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": f"test-consumer-{self.test_id}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            **kwargs,
        }
        consumer = Consumer(config)
        consumer.subscribe(topics)
        return consumer

    def cleanup(self):
        """Delete all test topics created during this test."""
        if not self.created_topics:
            return

        futures = self.admin.delete_topics(self.created_topics, operation_timeout=30)
        for topic, future in futures.items():
            try:
                future.result(timeout=30)
            except Exception:
                pass  # Topic may already be deleted


def _kafka_is_available(bootstrap_servers: str, timeout: float = 5.0) -> bool:
    """Check if Kafka is reachable."""
    try:
        admin = AdminClient({"bootstrap.servers": bootstrap_servers})
        # Try to list topics with a short timeout
        metadata = admin.list_topics(timeout=timeout)
        return metadata is not None
    except Exception:
        return False


@pytest.fixture
def kafka_context() -> Generator[KafkaTestContext, None, None]:
    """Provide Kafka context with automatic cleanup.

    Usage:
        def test_something(kafka_context):
            topic = kafka_context.create_topic("my_topic")
            producer = kafka_context.create_producer()
            # ... test ...
            # Cleanup happens automatically
    """
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

    if not _kafka_is_available(bootstrap_servers):
        pytest.skip(f"Kafka not available at {bootstrap_servers}")

    admin = AdminClient({"bootstrap.servers": bootstrap_servers})

    # Unique ID for this test run
    test_id = uuid.uuid4().hex[:8]

    ctx = KafkaTestContext(
        bootstrap_servers=bootstrap_servers,
        admin=admin,
        created_topics=[],
        test_id=test_id,
    )

    yield ctx

    # Cleanup: delete all topics created during test
    ctx.cleanup()


@pytest.fixture
def cleanup_stale_test_topics(kafka_context: KafkaTestContext):
    """Clean up any stale test topics from previous failed runs.

    Run this fixture once before test session to clean up orphaned topics.
    """
    metadata = kafka_context.admin.list_topics(timeout=10)
    stale_topics = [
        t for t in metadata.topics.keys()
        if t.startswith(TEST_TOPIC_PREFIX)
    ]

    if stale_topics:
        futures = kafka_context.admin.delete_topics(stale_topics, operation_timeout=30)
        for topic, future in futures.items():
            try:
                future.result(timeout=30)
            except Exception:
                pass


def wait_for_message(consumer: Consumer, timeout: float = 10.0) -> dict:
    """Wait for a message from consumer, with timeout."""
    start = time.time()
    while time.time() - start < timeout:
        msg = consumer.poll(timeout=1.0)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                continue
            raise Exception(f"Consumer error: {msg.error()}")
        return {
            "key": msg.key().decode("utf-8") if msg.key() else None,
            "value": msg.value(),
            "topic": msg.topic(),
            "partition": msg.partition(),
            "offset": msg.offset(),
        }
    raise TimeoutError(f"No message received within {timeout}s")
