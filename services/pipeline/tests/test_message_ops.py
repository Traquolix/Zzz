"""Tests for MessageOpsMixin: _on_delivery cross-thread safety."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.service_config import ServiceConfig


@pytest.fixture
async def transformer_service():
    """Create a Transformer service with mocked Kafka."""
    from shared.service_base import ServiceBase
    from shared.transformer import Transformer

    class StubTransformer(Transformer):
        async def transform(self, message):
            return message

    config = ServiceConfig(
        input_topic="test.in",
        output_topic="test.out",
    )

    with patch.object(ServiceBase, '_load_required_schemas'):
        svc = StubTransformer("test-svc", config)

    svc.producer = MagicMock()
    svc._loop = asyncio.get_running_loop()
    return svc


class TestOnDelivery:
    """Test _on_delivery callback thread safety."""

    @pytest.mark.asyncio
    async def test_on_delivery_success_clears_pending(self, transformer_service):
        """Successful delivery should clean up pending deliveries."""
        svc = transformer_service
        svc._pending_deliveries["msg-1"] = MagicMock()

        kafka_msg = MagicMock()
        kafka_msg.headers.return_value = [("message_id", b"msg-1")]
        svc._on_delivery(None, kafka_msg)
        assert "msg-1" not in svc._pending_deliveries

    @pytest.mark.asyncio
    async def test_on_delivery_error_with_dlq_disabled(self, transformer_service):
        """Error delivery with DLQ disabled should log but not crash."""
        svc = transformer_service
        svc.config.enable_dlq = False

        err = MagicMock()
        err.str.return_value = "Delivery failed"
        kafka_msg = MagicMock()
        kafka_msg.headers.return_value = [("message_id", b"msg-1")]

        # Should not raise
        svc._on_delivery(err, kafka_msg)

    @pytest.mark.asyncio
    async def test_on_delivery_error_with_dlq_uses_call_soon_threadsafe(self, transformer_service):
        """Error delivery with DLQ enabled should schedule via call_soon_threadsafe."""
        svc = transformer_service
        svc.config.enable_dlq = True
        svc._pending_deliveries["msg-1"] = MagicMock()

        svc._loop = MagicMock()
        svc._loop.is_running.return_value = True

        err = MagicMock()
        err.str.return_value = "Delivery failed"
        kafka_msg = MagicMock()
        kafka_msg.headers.return_value = [("message_id", b"msg-1")]

        svc._on_delivery(err, kafka_msg)

        svc._loop.call_soon_threadsafe.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_delivery_error_with_loop_not_running(self, transformer_service):
        """Error delivery when loop not running should log error."""
        svc = transformer_service
        svc.config.enable_dlq = True
        svc._pending_deliveries["msg-1"] = MagicMock()

        svc._loop = MagicMock()
        svc._loop.is_running.return_value = False

        err = MagicMock()
        err.str.return_value = "Delivery failed"
        kafka_msg = MagicMock()
        kafka_msg.headers.return_value = [("message_id", b"msg-1")]

        # Should not crash
        svc._on_delivery(err, kafka_msg)
        svc._loop.call_soon_threadsafe.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_delivery_error_no_loop(self, transformer_service):
        """Error delivery with no loop attribute should log error."""
        svc = transformer_service
        svc.config.enable_dlq = True
        svc._pending_deliveries["msg-1"] = MagicMock()
        svc._loop = None

        err = MagicMock()
        err.str.return_value = "Delivery failed"
        kafka_msg = MagicMock()
        kafka_msg.headers.return_value = [("message_id", b"msg-1")]

        # Should not crash
        svc._on_delivery(err, kafka_msg)
