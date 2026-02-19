"""Persistent Dead Letter Queue backed by Kafka topic."""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext, StringSerializer

from shared.message import Message
from shared.otel_setup import get_correlation_id


class PersistentDLQ:
    """Kafka-backed dead letter queue for failed messages."""

    def __init__(
        self,
        kafka_bootstrap_servers: str,
        schema_registry_url: str,
        service_name: str,
        dlq_topic: str = "das.dlq.all_services",
    ):
        self.service_name = service_name
        self.dlq_topic = dlq_topic
        self.logger = logging.getLogger(f"dlq.{service_name}")

        self.producer = Producer(
            {
                "bootstrap.servers": kafka_bootstrap_servers,
                "client.id": f"{service_name}-dlq-producer",
                "acks": "all",
                "retries": 3,
                "max.in.flight.requests.per.connection": 1,
                "compression.type": "lz4",
            }
        )

        schema_client = SchemaRegistryClient({"url": schema_registry_url})
        schema_path = Path(__file__).parent / "schema" / "das_dlq_message.avsc"
        with open(schema_path, "r") as f:
            schema_str = f.read()

        self.value_serializer = AvroSerializer(schema_client, schema_str)
        self.key_serializer = StringSerializer("utf-8")
        self._messages_written = 0
        self._write_failures = 0
        self.logger.info(f"PersistentDLQ initialized for {service_name} → {dlq_topic}")

    async def add_message(
        self,
        message: Message,
        error: str,
        original_topic: str = "unknown",
        original_partition: int = -1,
        original_offset: int = -1,
        stack_trace: Optional[str] = None,
    ):
        """Send failed message to DLQ topic."""
        try:
            correlation_id = get_correlation_id()

            if isinstance(error, Exception):
                error_type = type(error).__name__
                error_message = str(error)
            else:
                error_type = "ProcessingError"
                error_message = str(error)

            if len(error_message) > 1000:
                error_message = error_message[:997] + "..."

            try:
                original_payload = json.dumps(message.to_dict()).encode("utf-8")
            except Exception as e:
                self.logger.warning(f"Failed to serialize original message: {e}")
                original_payload = b"{}"

            dlq_payload = {
                "original_topic": original_topic,
                "original_partition": original_partition,
                "original_offset": original_offset,
                "service_name": self.service_name,
                "error_type": error_type,
                "error_message": error_message,
                "stack_trace": stack_trace,
                "timestamp_ns": time.time_ns(),
                "retry_count": getattr(message, "retry_count", 0),
                "correlation_id": correlation_id,
                "original_message_payload": original_payload,
            }

            serialization_context = SerializationContext(self.dlq_topic, MessageField.VALUE)
            serialized_value = self.value_serializer(dlq_payload, serialization_context)

            key_context = SerializationContext(self.dlq_topic, MessageField.KEY)
            serialized_key = self.key_serializer(self.service_name, key_context)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._produce_message, serialized_key, serialized_value
            )

            self._messages_written += 1

            self.logger.warning(
                f"DLQ: Failed message sent to {self.dlq_topic} | "
                f"Original: {original_topic}[{original_partition}]@{original_offset} | "
                f"Error: {error_type}: {error_message[:100]}"
            )

        except Exception as e:
            self._write_failures += 1
            self.logger.error(f"Failed to write to DLQ: {e} | Message: {message.id}")

    def _produce_message(self, key: bytes, value: bytes):
        self.producer.produce(
            topic=self.dlq_topic, key=key, value=value, callback=self._delivery_callback
        )
        self.producer.poll(0)

    def _delivery_callback(self, err, msg):
        if err is not None:
            self._write_failures += 1
            self.logger.error(
                f"DLQ delivery failed: {err} | " f"Topic: {msg.topic() if msg else 'unknown'}"
            )
        else:
            self.logger.debug(
                f"DLQ message delivered: {msg.topic()}[{msg.partition()}]@{msg.offset()}"
            )

    async def shutdown(self):
        """Flush pending messages and close producer."""
        try:
            self.logger.info("Shutting down DLQ...")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.producer.flush, 10.0)

            self.logger.info(
                f"DLQ shutdown complete | "
                f"Written: {self._messages_written} | "
                f"Failures: {self._write_failures}"
            )
        except Exception as e:
            self.logger.error(f"Error during DLQ shutdown: {e}")

    def get_stats(self) -> dict:
        return {
            "messages_written": self._messages_written,
            "write_failures": self._write_failures,
            "service_name": self.service_name,
            "dlq_topic": self.dlq_topic,
        }
