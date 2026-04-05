"""Base class for all Kafka service patterns.

Framework Architecture:
    Services implement 1-2 business logic methods, framework handles all infrastructure:
    - Kafka producer/consumer lifecycle and configuration
    - Avro serialization/deserialization with Schema Registry
    - Circuit breaker + exponential backoff retry logic
    - Dead letter queue for permanently failed messages
    - OpenTelemetry metrics and periodic health checks
    - Graceful shutdown with timeout protection
    - Multi-output routing to different topics
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
from abc import ABC
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from typing import Any

from aiohttp import web
from opentelemetry import trace

from shared.circuit_breaker import CircuitBreaker
from shared.message_metrics import MessageMetrics
from shared.persistent_dlq import PersistentDLQ
from shared.retry_handler import RetryHandler
from shared.service_config import ServiceConfig

from .health import HealthMixin
from .kafka_setup import KafkaSetupMixin
from .message_ops import MessageOpsMixin


class ServiceType(Enum):
    """Pattern types dictate which infrastructure components get initialized."""

    PRODUCER = "producer"
    TRANSFORMER = "transformer"
    MULTI_TRANSFORMER = "multi_transformer"
    BUFFERED_TRANSFORMER = "buffered_transformer"
    CONSUMER = "consumer"


_NEEDS_CONSUMER = frozenset(
    {
        ServiceType.CONSUMER,
        ServiceType.TRANSFORMER,
        ServiceType.MULTI_TRANSFORMER,
        ServiceType.BUFFERED_TRANSFORMER,
    }
)

_NEEDS_PRODUCER = frozenset(
    {
        ServiceType.PRODUCER,
        ServiceType.TRANSFORMER,
        ServiceType.MULTI_TRANSFORMER,
        ServiceType.BUFFERED_TRANSFORMER,
    }
)


class ServiceBase(ABC, KafkaSetupMixin, HealthMixin, MessageOpsMixin):
    """Base class for all Kafka service patterns.

    Pattern classes (Producer, Consumer, Transformer, etc.) inherit from this
    and add their specific abstract methods for business logic.
    """

    def __init__(self, service_name: str, config: ServiceConfig | None = None):
        self.service_name = service_name
        self._running = False
        self.config = config or ServiceConfig()

        self.logger = logging.getLogger(f"sequoia.pipeline.{service_name}")
        self.tracer = trace.get_tracer(__name__)

        self.service_type = self._detect_service_type()
        self._validate_config_for_service_type()
        self._initialize_components()

        self._tasks: list[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()
        self._graceful_shutdown_timeout = self.config.graceful_shutdown_timeout

        self._health_app: web.Application | None = None
        self._health_runner: web.AppRunner | None = None

        self._load_required_schemas()
        self._initialize_service_infrastructure()

        self.logger.info(f"Service {service_name} initialized as {self.service_type.value}")

    def _detect_service_type(self) -> ServiceType:
        """Auto-detect pattern type from inheritance."""
        from .consumer import Consumer
        from .producer import Producer
        from .transformer import (
            BufferedTransformer,
            MultiTransformer,
            RollingBufferedTransformer,
            Transformer,
        )

        if isinstance(self, Producer):
            return ServiceType.PRODUCER
        elif isinstance(self, RollingBufferedTransformer | BufferedTransformer):
            return ServiceType.BUFFERED_TRANSFORMER
        elif isinstance(self, MultiTransformer):
            return ServiceType.MULTI_TRANSFORMER
        elif isinstance(self, Transformer):
            return ServiceType.TRANSFORMER
        elif isinstance(self, Consumer):
            return ServiceType.CONSUMER
        else:
            raise ValueError(
                f"Service {self.service_name} must inherit from a service pattern class"
            )

    def _validate_config_for_service_type(self) -> None:
        """Validate required config fields based on pattern type."""
        if self.service_type == ServiceType.PRODUCER:
            if not self.config.output_topic and not self.config.outputs:
                raise ValueError("Producer services require output_topic or outputs configuration")
        elif self.service_type == ServiceType.CONSUMER:
            if not self.config.input_topic and not self.config.input_topic_pattern:
                raise ValueError(
                    "Consumer services require input_topic or input_topic_pattern configuration"
                )
        else:
            if not self.config.input_topic and not self.config.input_topic_pattern:
                raise ValueError(
                    "Transformer services require input_topic or input_topic_pattern configuration"
                )
            if not self.config.output_topic and not self.config.outputs:
                raise ValueError(
                    "Transformer services require output_topic or outputs configuration"
                )

        if not self.config.kafka_bootstrap_servers:
            raise ValueError("kafka_bootstrap_servers cannot be empty")
        if self.config.max_concurrent_messages <= 0:
            raise ValueError("max_concurrent_messages must be positive")

    def _initialize_components(self) -> None:
        """Initialize infrastructure components based on service type."""
        # Circuit breakers
        if self.service_type in _NEEDS_CONSUMER:
            self.consumer_circuit_breaker = CircuitBreaker(
                self.config.circuit_breaker_failure_threshold,
                self.config.circuit_breaker_recovery_timeout,
                on_state_change=lambda old, new: self.metrics.update_circuit_breaker_state(
                    "consumer", new
                ),
            )

        if self.service_type in _NEEDS_PRODUCER:
            self.producer_circuit_breaker = CircuitBreaker(
                self.config.circuit_breaker_failure_threshold,
                self.config.circuit_breaker_recovery_timeout,
                on_state_change=lambda old, new: self.metrics.update_circuit_breaker_state(
                    "producer", new
                ),
            )

        # Retry handler and DLQ
        self.retry_handler = RetryHandler(self.config)
        self.dead_letter_queue: PersistentDLQ | None = None
        if self.config.enable_dlq:
            self.dead_letter_queue = PersistentDLQ(
                kafka_bootstrap_servers=self.config.kafka_bootstrap_servers,
                schema_registry_url=self.config.schema_registry_url,
                service_name=self.service_name,
                dlq_topic=self.config.dlq_topic,
            )
            self.logger.info(f"DLQ enabled → {self.config.dlq_topic}")

        # Concurrency control and metrics
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_messages)
        self.metrics = MessageMetrics(self.service_name)

        # Thread pools
        cpu_count = os.cpu_count() or 4
        self._kafka_executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix=f"{self.service_name}-kafka"
        )
        self._serialization_executor = ThreadPoolExecutor(
            max_workers=cpu_count * 2, thread_name_prefix=f"{self.service_name}-avro"
        )

        self.logger.info(f"Thread pools initialized: Kafka=4, Serialization={cpu_count * 2}")

        # Kafka clients placeholders
        self.consumer: Any = None
        self.producer: Any = None

    def _load_required_schemas(self) -> None:
        """Load Avro schemas for inputs/outputs."""
        self.input_key_schema: str | None = None
        self.input_value_schema: str | None = None
        self.output_key_schema: str | None = None
        self.output_value_schema: str | None = None
        self.outputs_config: dict[str, dict[str, Any]] = {}

        try:
            # Load input schemas
            if self.service_type in _NEEDS_CONSUMER:
                self.input_key_schema = self._load_schema(self.config.input_key_schema_file)
                self.input_value_schema = self._load_schema(self.config.input_value_schema_file)

            # Load output schemas
            if self.service_type in _NEEDS_PRODUCER:
                self._setup_output_schemas()

        except FileNotFoundError as e:
            raise ValueError(f"Schema file not found: {e.filename}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to load Avro schema: Invalid JSON - {e}") from e
        except Exception as e:
            raise ValueError(f"Failed to load Avro schema: {e}") from e

    def _load_schema(self, schema_file: str | None) -> str | None:
        """Load and validate a schema file."""
        if not schema_file:
            return None
        with open(schema_file) as f:
            schema_text = f.read()
            json.loads(schema_text)  # Validate JSON
            return schema_text

    def _setup_output_schemas(self) -> None:
        """Setup output schema configurations."""
        # Backward compatibility: migrate legacy single output
        if self.config.output_topic and not self.config.outputs:
            from shared.service_config import OutputConfig

            self.config.outputs = {
                "default": OutputConfig(
                    topic=self.config.output_topic,
                    key_schema_file=self.config.output_key_schema_file,
                    value_schema_file=self.config.output_value_schema_file,
                )
            }
            self.logger.info(
                f"Auto-migrated single output to outputs['default']: {self.config.output_topic}"
            )

        # Load all configured outputs
        if self.config.outputs:
            for output_id, output_cfg in self.config.outputs.items():
                key_schema = self._load_schema(output_cfg.key_schema_file)
                value_schema = self._load_schema(output_cfg.value_schema_file)

                self.outputs_config[output_id] = {
                    "topic": output_cfg.topic,
                    "key_schema": key_schema,
                    "value_schema": value_schema,
                }

                if output_id == "default":
                    self.output_key_schema = key_schema
                    self.output_value_schema = value_schema

            self.logger.info(
                f"Loaded {len(self.outputs_config)} output(s): {list(self.outputs_config.keys())}"
            )

    def _initialize_service_infrastructure(self) -> None:
        """Initialize pattern-specific infrastructure."""
        self._message_batch: list[Any] = []
        self._last_flush_time: float = time.time()
        self._pending_deliveries: dict[str, Any] = {}

    def _setup_signal_handlers(self) -> None:
        """Register SIGTERM/SIGINT for graceful shutdown."""
        loop = asyncio.get_running_loop()

        def signal_handler(signum):
            self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            loop.call_soon_threadsafe(self._shutdown_event.set)

        try:
            loop.add_signal_handler(signal.SIGTERM, signal_handler, signal.SIGTERM)
            loop.add_signal_handler(signal.SIGINT, signal_handler, signal.SIGINT)
        except NotImplementedError:
            # add_signal_handler is not supported on Windows; fall back to
            # signal.signal which works cross-platform for SIGINT at least
            self.logger.warning(
                "asyncio signal handlers not supported on this platform, "
                "falling back to signal.signal for SIGINT"
            )
            signal.signal(
                signal.SIGINT, lambda s, f: loop.call_soon_threadsafe(self._shutdown_event.set)
            )

    async def start(self) -> None:
        """Start the service and wait for shutdown signal."""
        self.logger.info(f"Starting {self.service_type.value} service: {self.service_name}")

        # Store reference to event loop for cross-thread callbacks (e.g., Kafka delivery)
        self._loop = asyncio.get_running_loop()

        self._setup_signal_handlers()

        self.logger.info("Setting up Kafka clients...")
        await self._setup_kafka_clients()
        self.logger.info("Kafka clients ready")

        self._running = True

        self.logger.info("Starting HTTP health check server...")
        await self._start_health_server()
        self.logger.info("Health check server ready on port 8080")

        self._tasks.append(asyncio.create_task(self._health_check_loop()))

        if self.service_type in _NEEDS_CONSUMER:
            self.logger.info("Starting consumer lag monitoring...")
            self._tasks.append(asyncio.create_task(self._monitor_consumer_lag()))

        await self._start_service_loops()
        self.logger.info(f"Service started with {len(self._tasks)} background tasks")

        try:
            await self._shutdown_event.wait()
            self.logger.info("Shutdown signal received, beginning graceful shutdown...")
        except KeyboardInterrupt:
            self.logger.info("KeyboardInterrupt received, shutting down...")
        finally:
            await self.shutdown()

    async def _start_service_loops(self) -> None:
        """Override in pattern classes to start specific loops."""
        pass

    async def shutdown(self) -> None:
        """Graceful shutdown with configurable timeouts."""
        self.logger.info("Beginning graceful shutdown sequence...")

        self._running = False
        self.logger.info("Stopped accepting new messages")

        # Drain in-flight messages
        if hasattr(self, "_semaphore"):
            try:
                drain_timeout = self._graceful_shutdown_timeout * 0.6
                self.logger.info(
                    f"Draining {self._semaphore._value}/{self.config.max_concurrent_messages} in-flight messages..."
                )

                async def wait_for_drain():
                    while self._semaphore._value < self.config.max_concurrent_messages:
                        await asyncio.sleep(0.1)

                await asyncio.wait_for(wait_for_drain(), timeout=drain_timeout)
                self.logger.info("All in-flight messages processed")
            except asyncio.TimeoutError:
                in_flight = self.config.max_concurrent_messages - self._semaphore._value
                self.logger.warning(
                    f"Drain timeout: {in_flight} messages still in-flight, forcing shutdown"
                )
            except Exception as e:
                self.logger.error(f"Error during message drain: {e}")

        # Cancel background tasks
        self.logger.info(f"Cancelling {len(self._tasks)} background tasks...")
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            try:
                task_timeout = self._graceful_shutdown_timeout * 0.2
                await asyncio.wait_for(
                    asyncio.gather(*self._tasks, return_exceptions=True), timeout=task_timeout
                )
                self.logger.info("All background tasks completed")
            except asyncio.TimeoutError:
                self.logger.warning("Task shutdown timeout, forcing cleanup")
            except Exception as e:
                self.logger.error(f"Error during task shutdown: {e}")

        # Close Kafka clients
        await self._close_kafka_clients()

        # Shutdown DLQ
        if self.dead_letter_queue:
            self.logger.info("Shutting down DLQ...")
            try:
                await self.dead_letter_queue.shutdown()
                self.logger.info("DLQ shut down successfully")
            except Exception as e:
                self.logger.error(f"Error shutting down DLQ: {e}")

        # Shutdown thread pools
        if hasattr(self, "_kafka_executor"):
            self._kafka_executor.shutdown(wait=True, cancel_futures=False)
        if hasattr(self, "_serialization_executor"):
            self._serialization_executor.shutdown(wait=True, cancel_futures=False)
        self.logger.info("Thread pools shut down")

        if self._health_runner:
            self.logger.info("Shutting down health check server...")
            await self._health_runner.cleanup()
            self.logger.info("Health check server shut down")

        self.logger.info(f"Service {self.service_name} shut down")
        await self._log_final_metrics()

    async def _poll_loop(self, loop_name: str) -> None:
        """Shared poll-dispatch-error loop for all consuming service patterns.

        Messages are dispatched concurrently up to max_concurrent_messages
        (controlled by the semaphore in _execute_with_protection). The poll
        loop fires tasks without awaiting each one, allowing the event loop
        to interleave processing of multiple messages.
        """
        dispatch_tasks: set[asyncio.Task] = set()

        while self._running:
            try:
                # Back-pressure: if at concurrency limit, wait for a slot
                if self._semaphore.locked():
                    await asyncio.sleep(0.001)
                    continue

                message = await self._get_next_message()
                if message:
                    task = asyncio.create_task(self._safe_dispatch(message, loop_name))
                    dispatch_tasks.add(task)
                    task.add_done_callback(dispatch_tasks.discard)
                else:
                    await asyncio.sleep(self.config.consumer_idle_delay)
            except Exception as e:
                self.logger.error(f"Error in {loop_name} loop: {e}")
                self.metrics.record_error(f"{loop_name}_loop")
                await asyncio.sleep(self.config.error_backoff_delay)

        # Drain in-flight tasks on shutdown
        if dispatch_tasks:
            await asyncio.gather(*dispatch_tasks, return_exceptions=True)

    async def _safe_dispatch(self, message: Any, loop_name: str) -> None:
        """Dispatch a single message with error handling."""
        try:
            await self._dispatch(message)
        except Exception as e:
            self.logger.error(f"Error dispatching in {loop_name}: {e}")
            self.metrics.record_error(f"{loop_name}_dispatch")

    async def _dispatch(self, message: Any) -> None:
        """Override in pattern classes to handle a single polled message."""
        raise NotImplementedError

    async def _execute_with_protection(self, func, message: Any, *args) -> Any | None:
        """Shared semaphore + timeout + circuit-breaker + retry + DLQ wrapper."""
        from shared.message import KafkaMessage

        async with self._semaphore:
            start_time = time.time()
            try:
                result = await asyncio.wait_for(
                    self.consumer_circuit_breaker.call(
                        self.retry_handler.retry_with_backoff, func, *args
                    ),
                    timeout=self.config.message_timeout,
                )
                processing_time = time.time() - start_time
                self.metrics.record_message_processed(processing_time)
                if isinstance(message, KafkaMessage):
                    await self._commit_message(message)
                return result
            except asyncio.TimeoutError:
                self.logger.error(
                    f"Message {message.id} timed out after {self.config.message_timeout}s"
                )
                self.metrics.record_error("message_timeout")
                if self.config.enable_dlq:
                    await self.handle_dead_letter(
                        message, f"Timeout after {self.config.message_timeout}s"
                    )
            except Exception as e:
                self.logger.error(f"Failed to process message {message.id}: {e}")
                self.metrics.record_error("message_processing")
                if self.config.enable_dlq:
                    await self.handle_dead_letter(message, str(e))
        return None
