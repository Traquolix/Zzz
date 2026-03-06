"""
Tests for Kafka bridge watchdog — auto-restart on crash with exponential backoff.

The bridge management command should:
1. Restart after an exception (not die silently)
2. Stop immediately on KeyboardInterrupt
3. Give up after max retries
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from django.test import TestCase

from apps.realtime.management.commands.run_kafka_bridge import Command


@pytest.mark.django_db
class TestKafkaWatchdog(TestCase):
    @patch("apps.realtime.management.commands.run_kafka_bridge.run_kafka_bridge_loop")
    @patch("time.sleep")
    def test_bridge_restarts_on_exception(self, mock_sleep, mock_loop):
        """_run_kafka should retry after an exception, not die silently."""
        # First call raises, second succeeds (then KeyboardInterrupt to exit loop)
        mock_loop.side_effect = [ConnectionError("Kafka down"), KeyboardInterrupt()]

        cmd = Command()
        cmd._load_infrastructure = Mock(return_value=[])
        cmd.stdout = MagicMock()
        cmd.stderr = MagicMock()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda x: x
        cmd.style.WARNING = lambda x: x
        cmd.style.ERROR = lambda x: x

        cmd.handle()
        assert mock_loop.call_count == 2  # Called twice: crash + retry

    @patch("apps.realtime.management.commands.run_kafka_bridge.run_kafka_bridge_loop")
    @patch("time.sleep")
    def test_keyboard_interrupt_stops(self, mock_sleep, mock_loop):
        """KeyboardInterrupt stops immediately — no retry."""
        mock_loop.side_effect = KeyboardInterrupt()

        cmd = Command()
        cmd._load_infrastructure = Mock(return_value=[])
        cmd.stdout = MagicMock()
        cmd.stderr = MagicMock()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda x: x
        cmd.style.WARNING = lambda x: x
        cmd.style.ERROR = lambda x: x

        cmd.handle()
        assert mock_loop.call_count == 1

    @patch("apps.realtime.management.commands.run_kafka_bridge.run_kafka_bridge_loop")
    @patch("time.sleep")
    def test_gives_up_after_max_retries(self, mock_sleep, mock_loop):
        """After MAX_RETRIES consecutive failures, stop trying."""
        mock_loop.side_effect = RuntimeError("persistent failure")

        cmd = Command()
        cmd._load_infrastructure = Mock(return_value=[])
        cmd.stdout = MagicMock()
        cmd.stderr = MagicMock()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda x: x
        cmd.style.WARNING = lambda x: x
        cmd.style.ERROR = lambda x: x

        cmd.handle()
        assert mock_loop.call_count == 10  # MAX_RETRIES = 10

    @patch("apps.realtime.management.commands.run_kafka_bridge.run_kafka_bridge_loop")
    @patch("time.sleep")
    def test_backoff_increases(self, mock_sleep, mock_loop):
        """Sleep time should increase with exponential backoff."""
        mock_loop.side_effect = RuntimeError("fail")

        cmd = Command()
        cmd._load_infrastructure = Mock(return_value=[])
        cmd.stdout = MagicMock()
        cmd.stderr = MagicMock()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda x: x
        cmd.style.WARNING = lambda x: x
        cmd.style.ERROR = lambda x: x

        cmd.handle()

        # Verify backoff increases
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert sleep_calls[0] == 5  # base delay
        assert sleep_calls[1] == 10  # 5 * 2^1
        assert sleep_calls[2] == 20  # 5 * 2^2
        # Capped at 120
        assert all(s <= 120 for s in sleep_calls)
