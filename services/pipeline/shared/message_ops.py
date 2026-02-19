"""Message sending and receiving operations for service patterns."""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any, Optional

from confluent_kafka import KafkaError
from confluent_kafka.serialization import MessageField, SerializationContext
from opentelemetry import trace
from opentelemetry.propagate import extract, inject

from shared.message import KafkaMessage, Message
from shared.otel_setup import get_correlation_id

if TYPE_CHECKING:
    from .service_base import ServiceBase

tracer = trace.get_tracer(__name__)


class MessageOpsMixin:
    """Mixin providing message send/receive operations."""

    async def _get_next_message(self: "ServiceBase") -> Optional[Message]:
        """Poll and deserialize next Kafka message using Avro with OTEL tracing."""
        if not self.consumer:
            return None

        with self.tracer.start_as_current_span("kafka.poll") as span:
            try:
                correlation_id = get_correlation_id()
                if correlation_id:
                    span.set_attribute("correlation_id", correlation_id)
                if self.config.input_topic:
                    span.set_attribute("kafka.topic", self.config.input_topic)
                elif self.config.input_topic_pattern:
                    span.set_attribute("kafka.topic_pattern", self.config.input_topic_pattern)

                loop = asyncio.get_event_loop()
                raw_message = await loop.run_in_executor(
                    self._kafka_executor, self.consumer.poll, self.config.consumer_poll_timeout
                )

                if raw_message is None:
                    span.set_attribute("message.received", False)
                    return None

                if raw_message.error():
                    if raw_message.error().code() == KafkaError._PARTITION_EOF:
                        span.set_attribute("kafka.partition_eof", True)
                        return None
                    else:
                        span.record_exception(Exception(f"Consumer error: {raw_message.error()}"))
                        raise Exception(f"Consumer error: {raw_message.error()}")

                span.set_attribute("message.received", True)
                span.set_attribute("kafka.partition", raw_message.partition())
                span.set_attribute("kafka.offset", raw_message.offset())

                # Deserialize key
                key = await self._deserialize_key(raw_message)

                # Deserialize value
                value = await self._deserialize_value(raw_message)

                message = KafkaMessage(
                    id=key,
                    payload=value,
                    headers=dict(raw_message.headers()) if raw_message.headers() else None,
                    timestamp=(
                        raw_message.timestamp()[1] if raw_message.timestamp()[1] != -1 else None
                    ),
                    _kafka_message=raw_message,
                )

                # Extract trace context from headers
                self._extract_trace_context(message, span)

                if value and isinstance(value, dict):
                    fiber_id = value.get("fiber_id")
                    if fiber_id:
                        span.set_attribute("message.fiber_id", fiber_id)

                return message

            except Exception as e:
                import traceback

                span.record_exception(e)
                self.logger.error(f"Error consuming message: {e}")
                self.logger.error(f"Full traceback: {traceback.format_exc()}")
                return None

    async def _deserialize_key(self: "ServiceBase", raw_message) -> Optional[str]:
        """Deserialize message key."""
        if not raw_message.key():
            return None

        if hasattr(self, "key_deserializer"):
            ctx = SerializationContext(self.config.input_topic, MessageField.KEY)
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self._serialization_executor, lambda: self.key_deserializer(raw_message.key(), ctx)
            )
        return str(raw_message.key())

    async def _deserialize_value(self: "ServiceBase", raw_message) -> Any:
        """Deserialize message value."""
        if not raw_message.value():
            return None

        if hasattr(self, "value_deserializer"):
            ctx = SerializationContext(self.config.input_topic, MessageField.VALUE)
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self._serialization_executor,
                lambda: self.value_deserializer(raw_message.value(), ctx),
            )
        return raw_message.value()

    def _extract_trace_context(self: "ServiceBase", message: Message, span) -> None:
        """Extract OTEL trace context from message headers."""
        if not message.headers:
            return

        try:
            headers_dict = {}
            for header_item in message.headers:
                if isinstance(header_item, (tuple, list)) and len(header_item) == 2:
                    key, value = header_item
                    if isinstance(key, bytes):
                        key = key.decode("utf-8")
                    if isinstance(value, bytes):
                        value = value.decode("utf-8")
                    headers_dict[key] = value
            if headers_dict:
                extract(headers_dict)
        except Exception as header_err:
            self.logger.warning(f"Failed to extract trace context from headers: {header_err}")

    async def _internal_send(self: "ServiceBase", message: Message) -> bool:
        """Send message with circuit breaker and retry protection."""
        if not self.producer:
            self.logger.error("No producer configured")
            return False

        from .service_base import ServiceType

        start_time = time.time()

        try:
            success = await self.producer_circuit_breaker.call(
                self.retry_handler.retry_with_backoff, self._send_avro_message, message
            )

            send_time = time.time() - start_time

            if success:
                self.metrics.record_message_sent(send_time)
                self.logger.debug(f"Message {message.id} sent in {send_time:.3f}s")
                if self.service_type != ServiceType.PRODUCER:
                    self._message_batch.append(message)
                    await self._handle_batched_flush()
            else:
                self.metrics.record_error("message_send_failed")

            return success

        except Exception as e:
            self.metrics.record_error("message_send_error")
            self.logger.error(f"Failed to send message {message.id}: {e}")
            return False

    async def _send_avro_message(self: "ServiceBase", message: Message) -> bool:
        """Serialize and send to Kafka (multi-output routing via output_id)."""
        with self.tracer.start_as_current_span("kafka.send") as span:
            try:
                correlation_id = get_correlation_id()
                if correlation_id:
                    span.set_attribute("correlation_id", correlation_id)

                if message.id is not None:
                    span.set_attribute("message.id", message.id)
                if message.output_id is not None:
                    span.set_attribute("message.output_id", message.output_id)

                if message.output_id not in self.output_serializers:
                    self.logger.error(
                        f"Unknown output_id '{message.output_id}'. Available: {list(self.output_serializers.keys())}"
                    )
                    span.set_attribute("error.invalid_output_id", True)
                    return False

                output_config = self.output_serializers[message.output_id]
                topic = output_config["topic"]
                key_serializer = output_config["key"]
                value_serializer = output_config["value"]

                span.set_attribute("kafka.topic", topic)

                # Serialize key and value
                serialized_key = await self._serialize_key(message.id, topic, key_serializer)
                serialized_value = await self._serialize_value(
                    message.payload, topic, value_serializer
                )

                if serialized_value:
                    span.set_attribute("message.size_bytes", len(serialized_value))

                self._pending_deliveries[message.id] = message

                # Prepare headers and inject trace context
                headers = dict(message.headers) if message.headers else {}
                headers["message_id"] = message.id
                headers["output_id"] = message.output_id
                inject(headers)

                self.producer.produce(
                    topic=topic,
                    key=serialized_key,
                    value=serialized_value,
                    headers=headers,
                    callback=self._on_delivery,
                )

                span.set_attribute("message.sent", True)
                return True

            except Exception as e:
                span.record_exception(e)
                span.set_attribute("message.sent", False)
                self.logger.error(f"Failed to send message to output '{message.output_id}': {e}")
                return False

    async def _serialize_key(self: "ServiceBase", key, topic: str, serializer) -> Optional[bytes]:
        """Serialize message key."""
        if not key:
            return None

        if serializer:
            ctx = SerializationContext(topic, MessageField.KEY)
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, serializer, key, ctx)
        return str(key).encode("utf-8")

    async def _serialize_value(
        self: "ServiceBase", payload, topic: str, serializer
    ) -> Optional[bytes]:
        """Serialize message value."""
        if not payload:
            return None

        if serializer:
            ctx = SerializationContext(topic, MessageField.VALUE)
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, serializer, payload, ctx)
        return json.dumps(payload).encode("utf-8")

    async def _handle_batched_flush(self: "ServiceBase") -> None:
        """Flush when batch size or time interval threshold reached."""
        current_time = time.time()

        should_flush = (
            len(self._message_batch) >= self.config.producer_flush_threshold
            or (current_time - self._last_flush_time) >= self.config.producer_flush_interval
        )

        if should_flush and self._message_batch:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    self._kafka_executor,
                    self.producer.flush,
                    self.config.kafka_health_check_timeout,
                )

                self._message_batch.clear()
                self._last_flush_time = current_time
                self.logger.debug("Flushed producer batch")

            except Exception as e:
                self.logger.warning(f"Failed to flush producer: {e}")

    def _on_delivery(self: "ServiceBase", err, msg) -> None:
        """Kafka producer delivery callback."""
        if msg is None:
            return

        message_id = None
        try:
            if msg.headers():
                for key, value in msg.headers():
                    if key == "message_id":
                        message_id = (
                            value.decode("utf-8") if isinstance(value, bytes) else str(value)
                        )
                        break
        except (AttributeError, TypeError):
            pass

        original_message = None
        if message_id and message_id in self._pending_deliveries:
            original_message = self._pending_deliveries.pop(message_id)

        if err is not None:
            error_msg = f"Message delivery failed: {err.str()}"
            self.logger.error(f"Failed to deliver message {message_id}: {error_msg}")
            self.metrics.record_error("message_delivery_failed")

            if self.config.enable_dlq and original_message:
                asyncio.create_task(self.handle_dead_letter(original_message, error_msg))
        else:
            self.logger.debug(f"Successfully delivered message {message_id}")

    async def _commit_message(self: "ServiceBase", message: KafkaMessage) -> bool:
        """Commit with retry and rebalance-aware error handling."""
        with self.tracer.start_as_current_span("kafka.commit") as span:
            correlation_id = get_correlation_id()
            if correlation_id:
                span.set_attribute("correlation_id", correlation_id)

            if message.id is not None:
                span.set_attribute("message.id", message.id)

            if not self.consumer or not message._kafka_message:
                span.set_attribute("commit.result", "skipped_no_consumer")
                return False

            if message._kafka_message:
                span.set_attribute("kafka.topic", message._kafka_message.topic())
                span.set_attribute("kafka.partition", message._kafka_message.partition())
                span.set_attribute("kafka.offset", message._kafka_message.offset())

            commit_timeout = min(self.config.kafka_health_check_timeout, 5.0)

            async def _attempt_commit():
                await asyncio.to_thread(self.consumer.commit, message._kafka_message)

            retry_count = 0
            max_retries = self.config.max_retries
            delay = self.config.initial_retry_delay

            while retry_count <= max_retries:
                try:
                    await asyncio.wait_for(_attempt_commit(), timeout=commit_timeout)
                    self.logger.debug(f"Successfully committed message {message.id}")
                    span.set_attribute("commit.result", "success")
                    span.set_attribute("commit.retry_count", retry_count)
                    return True

                except asyncio.TimeoutError:
                    self.logger.warning(
                        f"Commit timeout for message {message.id} (attempt {retry_count + 1})"
                    )
                    span.add_event(f"commit_timeout_attempt_{retry_count + 1}")

                except Exception as e:
                    error_msg = str(e)
                    is_rebalance_error = any(
                        keyword in error_msg.lower()
                        for keyword in [
                            "illegal generation",
                            "rebalance",
                            "not assigned",
                            "coordinator",
                        ]
                    )

                    if is_rebalance_error:
                        self.logger.warning(
                            f"Rebalance during commit for message {message.id}: {error_msg}"
                        )
                        span.set_attribute("commit.result", "rebalance_error")
                        span.add_event("rebalance_detected", {"error": error_msg})
                        break
                    else:
                        self.logger.warning(
                            f"Commit failed for message {message.id} (attempt {retry_count + 1}): {error_msg}"
                        )
                        span.add_event(
                            f"commit_error_attempt_{retry_count + 1}", {"error": error_msg}
                        )

                if retry_count >= max_retries:
                    break

                if retry_count < max_retries:
                    await asyncio.sleep(delay)
                    delay = min(
                        delay * self.config.retry_backoff_multiplier, self.config.max_retry_delay
                    )
                    retry_count += 1

            final_error = f"Failed to commit message {message.id} after {retry_count + 1} attempts"
            self.logger.error(final_error)
            self.metrics.record_error("commit_failed")
            span.set_attribute("commit.result", "failed")
            span.set_attribute("commit.retry_count", retry_count)
            span.record_exception(Exception(final_error))
            return False

    async def handle_dead_letter(
        self: "ServiceBase", message: Message, error: str, kafka_message: Optional[Any] = None
    ) -> None:
        """Send failed message to DLQ if enabled."""
        if self.dead_letter_queue:
            try:
                original_topic = "unknown"
                original_partition = -1
                original_offset = -1

                if kafka_message and hasattr(kafka_message, "topic"):
                    original_topic = kafka_message.topic()
                    original_partition = kafka_message.partition()
                    original_offset = kafka_message.offset()
                elif hasattr(message, "_kafka_message") and message._kafka_message:
                    original_topic = message._kafka_message.topic()
                    original_partition = message._kafka_message.partition()
                    original_offset = message._kafka_message.offset()

                await self.dead_letter_queue.add_message(
                    message=message,
                    error=error,
                    original_topic=original_topic,
                    original_partition=original_partition,
                    original_offset=original_offset,
                )

                self.logger.error(f"Message {message.id} sent to DLQ: {error}")
            except Exception as dlq_error:
                self.logger.critical(
                    f"CRITICAL: DLQ failed for message {message.id}. "
                    f"Original error: {error}. DLQ error: {dlq_error}"
                )
                self.metrics.record_error("dlq_failure")
        else:
            self.logger.error(f"Message {message.id} failed (no DLQ configured): {error}")
