from dataclasses import dataclass
from typing import Any


@dataclass
class Message:
    id: str
    payload: Any
    headers: dict[str, str] | None = None
    timestamp: float | None = None
    retry_count: int = 0
    source_topic: str | None = None
    output_id: str = "default"  # For multi-output services: which output to send to

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary for serialization (e.g., DLQ)."""
        return {
            "id": self.id,
            "payload": self.payload,
            "headers": self.headers,
            "timestamp": self.timestamp,
            "retry_count": self.retry_count,
            "source_topic": self.source_topic,
            "output_id": self.output_id,
        }


@dataclass
class KafkaMessage(Message):
    """Message with Kafka-specific metadata for commit handling."""

    _kafka_message: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary, excluding Kafka internals."""
        base = super().to_dict()
        # Don't serialize the internal Kafka message object
        return base
