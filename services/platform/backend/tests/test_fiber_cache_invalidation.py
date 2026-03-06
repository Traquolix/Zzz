"""
Tests for FiberAssignment cache invalidation — channel layer signal to bridge.

When a FiberAssignment is created/deleted, the bridge should be notified
to reload its fiber_org_map immediately (rather than waiting for the
periodic 300s refresh).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.test import TestCase

from apps.fibers.models import FiberAssignment
from tests.factories import OrganizationFactory


@pytest.mark.django_db
class TestFiberCacheInvalidationSignal(TestCase):
    """Signal handler sends bridge_control refresh on FiberAssignment change."""

    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()

    @patch("apps.fibers.apps.get_channel_layer")
    def test_fiber_assignment_create_sends_bridge_refresh(self, mock_get_layer):
        """When a FiberAssignment is created, a refresh_fiber_map
        message should be sent to the bridge_control group via channel layer."""
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        FiberAssignment.objects.create(fiber_id="test-fiber", organization=self.org)

        mock_layer.group_send.assert_called_with(
            "bridge_control",
            {"type": "refresh_fiber_map"},
        )

    @patch("apps.fibers.apps.get_channel_layer")
    def test_fiber_assignment_delete_sends_bridge_refresh(self, mock_get_layer):
        """When a FiberAssignment is deleted, a refresh signal should be sent."""
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        assignment = FiberAssignment.objects.create(
            fiber_id="test-fiber-del", organization=self.org
        )
        mock_layer.reset_mock()

        assignment.delete()

        mock_layer.group_send.assert_called_with(
            "bridge_control",
            {"type": "refresh_fiber_map"},
        )

    @patch("apps.fibers.apps.get_channel_layer")
    def test_signal_failure_does_not_break_save(self, mock_get_layer):
        """If channel layer signal fails, the FiberAssignment save should still succeed."""
        mock_layer = MagicMock()
        mock_layer.group_send.side_effect = Exception("Redis down")
        mock_get_layer.return_value = mock_layer

        # Should not raise — signal failure is non-critical
        assignment = FiberAssignment.objects.create(
            fiber_id="test-fiber-err", organization=self.org
        )
        assert assignment.pk is not None
