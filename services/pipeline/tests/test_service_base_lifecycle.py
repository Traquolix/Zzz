"""Tests for ServiceBase lifecycle: startup order, shutdown drain, capability sets."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.circuit_breaker import CircuitBreakerState
from shared.service_base import ServiceBase, ServiceType, _NEEDS_CONSUMER, _NEEDS_PRODUCER
from shared.service_config import OutputConfig, ServiceConfig


class TestCapabilitySets:
    """Test _NEEDS_CONSUMER and _NEEDS_PRODUCER frozensets."""

    def test_consumer_needs_consumer(self):
        assert ServiceType.CONSUMER in _NEEDS_CONSUMER

    def test_producer_not_in_needs_consumer(self):
        assert ServiceType.PRODUCER not in _NEEDS_CONSUMER

    def test_producer_needs_producer(self):
        assert ServiceType.PRODUCER in _NEEDS_PRODUCER

    def test_consumer_not_in_needs_producer(self):
        assert ServiceType.CONSUMER not in _NEEDS_PRODUCER

    def test_transformer_needs_both(self):
        assert ServiceType.TRANSFORMER in _NEEDS_CONSUMER
        assert ServiceType.TRANSFORMER in _NEEDS_PRODUCER

    def test_buffered_transformer_needs_both(self):
        assert ServiceType.BUFFERED_TRANSFORMER in _NEEDS_CONSUMER
        assert ServiceType.BUFFERED_TRANSFORMER in _NEEDS_PRODUCER

    def test_multi_transformer_needs_both(self):
        assert ServiceType.MULTI_TRANSFORMER in _NEEDS_CONSUMER
        assert ServiceType.MULTI_TRANSFORMER in _NEEDS_PRODUCER


class TestConfigValidation:
    """Test _validate_config_for_service_type."""

    def test_empty_bootstrap_servers_raises(self):
        config = ServiceConfig(
            kafka_bootstrap_servers="",
            input_topic="test",
            output_topic="test",
        )
        with pytest.raises(ValueError, match="kafka_bootstrap_servers"):
            _create_stub_transformer("test", config)

    def test_zero_concurrent_messages_raises(self):
        config = ServiceConfig(
            input_topic="test",
            output_topic="test",
            max_concurrent_messages=0,
        )
        with pytest.raises(ValueError, match="max_concurrent_messages"):
            _create_stub_transformer("test", config)

    def test_producer_without_output_raises(self):
        config = ServiceConfig(
            kafka_bootstrap_servers="localhost:9092",
        )
        with pytest.raises(ValueError, match="output_topic"):
            _create_stub_producer("test", config)

    def test_consumer_without_input_raises(self):
        config = ServiceConfig(
            kafka_bootstrap_servers="localhost:9092",
        )
        with pytest.raises(ValueError, match="input_topic"):
            _create_stub_consumer("test", config)


class TestCircuitBreakerWiring:
    """Test that circuit breaker callbacks are wired."""

    def test_consumer_cb_has_callback(self):
        config = ServiceConfig(
            input_topic="test.in",
            output_topic="test.out",
        )
        svc = _create_stub_transformer("test", config)
        assert svc.consumer_circuit_breaker._on_state_change is not None

    def test_producer_cb_has_callback(self):
        config = ServiceConfig(
            input_topic="test.in",
            output_topic="test.out",
        )
        svc = _create_stub_transformer("test", config)
        assert svc.producer_circuit_breaker._on_state_change is not None


# --- Helpers ---

def _create_stub_transformer(name, config):
    """Create a minimal Transformer subclass for testing ServiceBase init."""
    from shared.transformer import Transformer

    class StubTransformer(Transformer):
        async def transform(self, message):
            return message

    with patch.object(ServiceBase, '_load_required_schemas'):
        return StubTransformer(name, config)


def _create_stub_producer(name, config):
    from shared.producer import Producer

    class StubProducer(Producer):
        async def generate(self):
            return None

    with patch.object(ServiceBase, '_load_required_schemas'):
        return StubProducer(name, config)


def _create_stub_consumer(name, config):
    from shared.consumer import Consumer

    class StubConsumer(Consumer):
        async def consume(self, message):
            pass

    with patch.object(ServiceBase, '_load_required_schemas'):
        return StubConsumer(name, config)
