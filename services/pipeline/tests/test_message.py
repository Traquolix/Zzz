"""Tests for Message and KafkaMessage classes."""

from unittest.mock import MagicMock

from shared.message import KafkaMessage


class TestKafkaMessageSerialization:
    """Test KafkaMessage serialization behavior."""

    def test_to_dict_excludes_kafka_message(self):
        """to_dict should NOT include _kafka_message (non-serializable)."""
        kafka_raw = MagicMock()
        msg = KafkaMessage(
            id="test",
            payload={"key": "value"},
            _kafka_message=kafka_raw,
        )

        result = msg.to_dict()

        assert "_kafka_message" not in result
        assert "id" in result
        assert "payload" in result
