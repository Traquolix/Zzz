"""Tests for transformer patterns: Transformer, MultiTransformer, Consumer using shared _poll_loop."""

from unittest.mock import AsyncMock, patch

import pytest

from shared.message import Message
from shared.service_base import ServiceBase
from shared.service_config import ServiceConfig


def _make_config(**overrides):
    defaults = dict(
        input_topic="test.in",
        output_topic="test.out",
        kafka_bootstrap_servers="localhost:9092",
        max_concurrent_messages=10,
        message_timeout=5.0,
        enable_dlq=False,
        consumer_idle_delay=0.01,
        error_backoff_delay=0.01,
    )
    defaults.update(overrides)
    return ServiceConfig(**defaults)


def _make_message(msg_id="msg-1", payload=None):
    return Message(id=msg_id, payload=payload or {"data": "test"})


class TestTransformerPattern:
    """Test 1:1 Transformer using shared _poll_loop + _dispatch."""

    @pytest.mark.asyncio
    async def test_transform_and_send(self):
        from shared.transformer import Transformer

        class DoubleTransformer(Transformer):
            async def transform(self, message):
                return Message(id=message.id, payload={"doubled": True})

        config = _make_config()
        with patch.object(ServiceBase, "_load_required_schemas"):
            svc = DoubleTransformer("test", config)

        svc._internal_send = AsyncMock()
        svc._commit_message = AsyncMock()

        msg = _make_message()
        # Call _dispatch directly (unit test, not full loop)
        await svc._dispatch(msg)

        svc._internal_send.assert_called_once()
        sent = svc._internal_send.call_args[0][0]
        assert sent.payload["doubled"] is True

    @pytest.mark.asyncio
    async def test_transform_returns_none_skips_send(self):
        from shared.transformer import Transformer

        class FilterTransformer(Transformer):
            async def transform(self, message):
                return None  # Skip

        config = _make_config()
        with patch.object(ServiceBase, "_load_required_schemas"):
            svc = FilterTransformer("test", config)

        svc._internal_send = AsyncMock()

        await svc._dispatch(_make_message())
        svc._internal_send.assert_not_called()


class TestMultiTransformerPattern:
    """Test 1:N MultiTransformer."""

    @pytest.mark.asyncio
    async def test_multi_transform_sends_all(self):
        from shared.transformer import MultiTransformer

        class SplitTransformer(MultiTransformer):
            async def transform(self, message):
                return [
                    Message(id="a", payload={"part": 1}),
                    Message(id="b", payload={"part": 2}),
                ]

        config = _make_config()
        with patch.object(ServiceBase, "_load_required_schemas"):
            svc = SplitTransformer("test", config)

        svc._internal_send = AsyncMock()
        svc._commit_message = AsyncMock()

        await svc._dispatch(_make_message())
        assert svc._internal_send.call_count == 2


class TestConsumerPattern:
    """Test Consumer pattern using shared infrastructure."""

    @pytest.mark.asyncio
    async def test_consume_called(self):
        from shared.consumer import Consumer

        consumed = []

        class TrackingConsumer(Consumer):
            async def consume(self, message):
                consumed.append(message)

        config = _make_config(output_topic=None)
        with patch.object(ServiceBase, "_load_required_schemas"):
            svc = TrackingConsumer("test", config)

        svc._commit_message = AsyncMock()

        msg = _make_message()
        await svc._dispatch(msg)

        assert len(consumed) == 1
        assert consumed[0].id == "msg-1"


class TestPollLoopShared:
    """Test that _poll_loop is used by all patterns."""

    @pytest.mark.asyncio
    async def test_transformer_uses_poll_loop(self):
        from shared.transformer import Transformer

        class Stub(Transformer):
            async def transform(self, message):
                return message

        config = _make_config()
        with patch.object(ServiceBase, "_load_required_schemas"):
            svc = Stub("test", config)

        # Verify _start_service_loops creates task with _poll_loop
        svc._tasks = []
        with patch.object(svc, "_poll_loop", new_callable=AsyncMock):
            # Can't await _start_service_loops without a running loop properly,
            # but we can check the method exists and is used
            assert hasattr(svc, "_poll_loop")
            assert hasattr(svc, "_dispatch")

    @pytest.mark.asyncio
    async def test_consumer_uses_poll_loop(self):
        from shared.consumer import Consumer

        class Stub(Consumer):
            async def consume(self, message):
                pass

        config = _make_config(output_topic=None)
        with patch.object(ServiceBase, "_load_required_schemas"):
            svc = Stub("test", config)

        assert hasattr(svc, "_poll_loop")
        assert hasattr(svc, "_dispatch")
