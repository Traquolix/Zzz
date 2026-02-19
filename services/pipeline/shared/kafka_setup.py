"""Kafka client setup and configuration for service patterns."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from confluent_kafka import Consumer, Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer, AvroSerializer

if TYPE_CHECKING:
    from .service_base import ServiceBase

logger = logging.getLogger(__name__)


class KafkaSetupMixin:
    """Mixin providing Kafka client setup functionality."""

    async def _setup_kafka_clients(self: "ServiceBase") -> None:
        """Initialize Kafka consumer/producer based on pattern type."""
        from .service_base import ServiceType

        if self.config.schema_registry_url:
            self.schema_registry_client = SchemaRegistryClient(
                {"url": self.config.schema_registry_url}
            )

        security_config = self._build_security_config()

        # Create consumer for consuming services
        if self.service_type in [
            ServiceType.CONSUMER,
            ServiceType.TRANSFORMER,
            ServiceType.MULTI_TRANSFORMER,
            ServiceType.BUFFERED_TRANSFORMER,
        ]:
            self._setup_consumer(security_config)

        # Create producer for producing services
        if self.service_type in [
            ServiceType.PRODUCER,
            ServiceType.TRANSFORMER,
            ServiceType.MULTI_TRANSFORMER,
            ServiceType.BUFFERED_TRANSFORMER,
        ]:
            self._setup_producer(security_config)

    def _setup_consumer(self: "ServiceBase", security_config: dict) -> None:
        """Setup Kafka consumer with deserializers."""
        consumer_config = {
            "bootstrap.servers": self.config.kafka_bootstrap_servers,
            "group.id": self.config.kafka_group_id or f"{self.service_name}-group",
            "auto.offset.reset": self.config.consumer_auto_offset_reset,
            "enable.auto.commit": False,
            "session.timeout.ms": self.config.consumer_session_timeout_ms,
            "heartbeat.interval.ms": self.config.consumer_heartbeat_interval_ms,
            "max.poll.interval.ms": self.config.consumer_max_poll_interval_ms,
            "fetch.min.bytes": self.config.consumer_fetch_min_bytes,
            "fetch.wait.max.ms": self.config.consumer_fetch_max_wait_ms,
            "isolation.level": self.config.consumer_isolation_level,
            **security_config,
        }

        self.consumer = Consumer(consumer_config)

        if self.config.input_topic_pattern:
            self.consumer.subscribe([self.config.input_topic_pattern])
            self.logger.info(f"Subscribed to topic pattern: {self.config.input_topic_pattern}")
        else:
            self.consumer.subscribe([self.config.input_topic])
            self.logger.info(f"Subscribed to topic: {self.config.input_topic}")

        # Setup deserializers
        if hasattr(self, "schema_registry_client"):
            self.key_deserializer = AvroDeserializer(
                self.schema_registry_client,
                self.input_key_schema if self.input_key_schema else None,
            )
            self.value_deserializer = AvroDeserializer(
                self.schema_registry_client,
                self.input_value_schema if self.input_value_schema else None,
            )

    def _setup_producer(self: "ServiceBase", security_config: dict) -> None:
        """Setup Kafka producer with serializers."""
        producer_config = {
            "bootstrap.servers": self.config.kafka_bootstrap_servers,
            "acks": self.config.producer_acks,
            "retries": self.config.producer_retries,
            "compression.type": self.config.producer_compression_type,
            "linger.ms": self.config.producer_linger_ms,
            "batch.size": self.config.producer_batch_size,
            "request.timeout.ms": self.config.producer_request_timeout_ms,
            "delivery.timeout.ms": self.config.producer_delivery_timeout_ms,
            "max.in.flight.requests.per.connection": self.config.producer_max_in_flight_requests,
            "enable.idempotence": self.config.producer_enable_idempotence,
            "queue.buffering.max.kbytes": self.config.producer_buffer_memory // 1024,
            **security_config,
        }

        self.producer = Producer(producer_config)

        # Setup serializers for all outputs
        self.output_serializers = {}
        if hasattr(self, "schema_registry_client") and self.outputs_config:
            for output_id, config in self.outputs_config.items():
                key_serializer = None
                value_serializer = None

                if config["key_schema"]:
                    key_serializer = AvroSerializer(
                        self.schema_registry_client, config["key_schema"]
                    )
                if config["value_schema"]:
                    value_serializer = AvroSerializer(
                        self.schema_registry_client, config["value_schema"]
                    )

                self.output_serializers[output_id] = {
                    "key": key_serializer,
                    "value": value_serializer,
                    "topic": config["topic"],
                }

            self.logger.info(
                f"Initialized serializers for {len(self.output_serializers)} output(s)"
            )

        # Backward compatibility
        if "default" in self.output_serializers:
            self.key_serializer = self.output_serializers["default"]["key"]
            self.value_serializer = self.output_serializers["default"]["value"]

    def _build_security_config(self: "ServiceBase") -> dict:
        """Build Kafka security config from SSL/SASL settings."""
        security_config = {}

        if self.config.ssl_enabled and self.config.sasl_mechanism:
            security_config["security.protocol"] = "SASL_SSL"
        elif self.config.ssl_enabled:
            security_config["security.protocol"] = "SSL"
        elif self.config.sasl_mechanism:
            security_config["security.protocol"] = "SASL_PLAINTEXT"

        if self.config.ssl_enabled:
            if self.config.ssl_ca_location:
                security_config["ssl.ca.location"] = self.config.ssl_ca_location
            if self.config.ssl_certificate_location:
                security_config["ssl.certificate.location"] = self.config.ssl_certificate_location
            if self.config.ssl_key_location:
                security_config["ssl.key.location"] = self.config.ssl_key_location

        if self.config.sasl_mechanism:
            security_config["sasl.mechanism"] = self.config.sasl_mechanism
            if self.config.sasl_username:
                security_config["sasl.username"] = self.config.sasl_username
            if self.config.sasl_password:
                security_config["sasl.password"] = self.config.sasl_password

        return security_config

    async def _close_kafka_clients(self: "ServiceBase") -> None:
        """Close Kafka clients with configurable timeouts."""
        try:
            if self.consumer:
                self.logger.info("Closing Kafka consumer...")
                await asyncio.wait_for(
                    asyncio.to_thread(self.consumer.close),
                    timeout=self.config.consumer_close_timeout,
                )
                self.logger.info("Kafka consumer closed")

            if self.producer:
                self.logger.info("Flushing and closing Kafka producer...")
                await asyncio.wait_for(
                    asyncio.to_thread(self.producer.flush, self.config.producer_flush_timeout),
                    timeout=self.config.producer_flush_timeout + 1.0,
                )
                self.logger.info("Kafka producer flushed and closed")

        except asyncio.TimeoutError:
            self.logger.warning("Timeout while closing Kafka clients, continuing shutdown")
        except Exception as e:
            self.logger.error(f"Error closing Kafka clients: {e}")
