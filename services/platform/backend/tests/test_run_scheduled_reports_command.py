"""
Tests for the run_scheduled_reports management command.
"""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase


class RunScheduledReportsCommandTestCase(TestCase):
    """Test the run_scheduled_reports management command."""

    @patch("apps.reporting.task_runner.run_scheduled_reports")
    def test_command_calls_run_scheduled_reports(self, mock_run):
        """Test that the command calls run_scheduled_reports()."""
        mock_run.return_value = 3

        out = StringIO()
        call_command("run_scheduled_reports", stdout=out)

        mock_run.assert_called_once()
        assert "Triggered 3 scheduled reports" in out.getvalue()

    @patch("apps.reporting.task_runner.run_scheduled_reports")
    def test_command_outputs_correct_count(self, mock_run):
        """Test that the command outputs the correct count."""
        mock_run.return_value = 5

        out = StringIO()
        call_command("run_scheduled_reports", stdout=out)

        assert "Triggered 5 scheduled reports" in out.getvalue()

    @patch("apps.reporting.task_runner.run_scheduled_reports")
    def test_command_with_zero_reports(self, mock_run):
        """Test that the command handles zero triggered reports."""
        mock_run.return_value = 0

        out = StringIO()
        call_command("run_scheduled_reports", stdout=out)

        assert "Triggered 0 scheduled reports" in out.getvalue()
