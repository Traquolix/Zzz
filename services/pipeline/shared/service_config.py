import os
from dataclasses import dataclass


@dataclass
class OutputConfig:
    """Configuration for a single output destination.

    Allows services to produce to multiple topics with different schemas.

    Example:
        outputs = {
            'default': OutputConfig(
                topic='das.detections',
                key_schema_file='shared/schema/string_key.avsc',
                value_schema_file='ai_engine/schema/das_detection.avsc'
            )
        }
    """

    topic: str
    key_schema_file: str | None = None
    value_schema_file: str | None = None


@dataclass
class ServiceConfig:
    """Configuration for Service instances.

    Groups all service configuration options including Kafka settings,
    schema files, reliability parameters, and performance tuning.

    Example:
        config = ServiceConfig(
            input_topic='raw_data',
            output_topic='processed_data',
            input_value_schema_file='schemas/input.avsc',
            output_value_schema_file='schemas/output.avsc',
            kafka_bootstrap_servers='kafka:9092',
            max_concurrent_messages=20
        )
    """

    # Retry settings
    max_retries: int = 3
    initial_retry_delay: float = 1.0
    max_retry_delay: float = 60.0
    retry_backoff_multiplier: float = 2.0

    # Circuit breaker settings
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: float = 30.0

    # Dead letter queue settings (Kafka-backed)
    enable_dlq: bool = True
    dlq_topic: str = "prod.dlq"

    # Performance settings
    max_concurrent_messages: int = 100
    message_timeout: float = 30.0

    # Buffer management (for BufferedTransformer)
    max_active_buffers: int = 10  # Limit concurrent fiber buffers (prevents OOM)
    buffer_timeout: float = 60.0  # Timeout for partial buffers

    # Timing settings
    health_check_interval: float = 30.0
    producer_flush_interval: float = 5.0
    producer_flush_threshold: int = 100
    consumer_poll_timeout: float = 1.0
    error_backoff_delay: float = 1.0
    consumer_idle_delay: float = 0.1
    producer_idle_delay: float = 0.1

    # Graceful shutdown settings
    graceful_shutdown_timeout: float = 30.0  # Overall shutdown timeout
    consumer_close_timeout: float = 5.0  # Timeout for consumer.close()
    producer_flush_timeout: float = 10.0  # Timeout for producer.flush()

    # Health monitoring
    kafka_health_check_timeout: float = 5.0
    producer_queue_threshold: int = 1000

    # Kafka settings
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_group_id: str | None = None  # Auto-generated if None
    schema_registry_url: str = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8081")

    # Security settings
    ssl_enabled: bool = False
    ssl_ca_location: str | None = None
    ssl_certificate_location: str | None = None
    ssl_key_location: str | None = None
    sasl_mechanism: str | None = None  # PLAIN, SCRAM-SHA-256, etc.
    sasl_username: str | None = None
    sasl_password: str | None = None

    # Input configuration (Consumer)
    input_topic: str | None = None
    input_topic_pattern: str | None = None  # Regex pattern for multi-topic subscription
    input_key_schema_file: str | None = None
    input_value_schema_file: str | None = None

    # Output configuration (Producer)
    output_topic: str | None = None
    output_key_schema_file: str | None = None
    output_value_schema_file: str | None = None

    # Multi-output configuration (Producer)
    # If specified, overrides single output_topic configuration
    # Services automatically migrate single output to outputs['default']
    outputs: dict[str, OutputConfig] | None = None

    # Advanced Kafka Producer Settings
    producer_acks: str = "all"  # 'all', '1', '0'
    producer_retries: int = 3
    producer_compression_type: str = "snappy"  # 'none', 'gzip', 'snappy', 'lz4', 'zstd'
    producer_linger_ms: int = 0  # Batch delay in ms
    producer_batch_size: int = 16384  # Batch size in bytes
    producer_request_timeout_ms: int = 30000  # 30 seconds
    producer_delivery_timeout_ms: int = 120000  # 2 minutes
    producer_max_in_flight_requests: int = 5  # Can reorder if > 1
    producer_enable_idempotence: bool = True  # Prevent duplicates
    producer_buffer_memory: int = 33554432  # 32MB buffer

    # Advanced Kafka Consumer Settings
    consumer_auto_offset_reset: str = "earliest"  # 'earliest', 'latest', 'none'
    consumer_session_timeout_ms: int = 10000  # 10 seconds
    consumer_heartbeat_interval_ms: int = 3000  # 3 seconds
    consumer_max_poll_interval_ms: int = 300000  # 5 minutes
    consumer_fetch_min_bytes: int = 1
    consumer_fetch_max_wait_ms: int = 500
    consumer_isolation_level: str = "read_uncommitted"  # 'read_committed', 'read_uncommitted'

    # Instrumentation Settings
    enable_profiling: bool = True  # Enable operation profiling
    enable_lag_monitoring: bool = True  # Monitor Kafka consumer lag
    enable_latency_histogram: bool = True  # Track latency distribution
    profiling_report_interval: int = (
        30  # Report profiling stats every N seconds (via health_check_interval)
    )
