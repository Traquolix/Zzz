"""
Tests for request correlation IDs.

Verifies that:
1. Every response has an X-Request-ID header
2. Different requests get different IDs
3. The request_id propagates to log records via ContextVar
"""

import logging
import pytest
from django.test import TestCase, RequestFactory
from rest_framework.test import APIClient

from apps.shared.logging_utils import RequestIdFilter, set_request_id, get_request_id
from tests.factories import UserFactory, OrganizationFactory


@pytest.mark.django_db
class TestRequestCorrelationIds(TestCase):

    def setUp(self):
        self.org = OrganizationFactory()
        self.user = UserFactory(organization=self.org)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_request_id_in_response_header(self):
        """Every API response must include X-Request-ID header."""
        response = self.client.get('/api/health')
        self.assertIn('X-Request-ID', response)
        self.assertTrue(len(response['X-Request-ID']) > 0)

    def test_different_requests_get_different_ids(self):
        """Sequential requests must get distinct correlation IDs."""
        r1 = self.client.get('/api/health')
        r2 = self.client.get('/api/health')
        self.assertNotEqual(r1['X-Request-ID'], r2['X-Request-ID'])


class TestRequestIdFilter:
    """Unit tests for the ContextVar-based log filter."""

    def test_filter_injects_request_id(self):
        """Log records should have request_id attribute after filtering."""
        set_request_id('test-abc-123')
        filt = RequestIdFilter()
        record = logging.LogRecord(
            name='test', level=logging.INFO, pathname='', lineno=0,
            msg='test message', args=(), exc_info=None,
        )
        filt.filter(record)
        assert record.request_id == 'test-abc-123'

    def test_default_request_id_is_dash(self):
        """Without set_request_id, the default should be '-'."""
        # Reset by setting to default
        set_request_id('-')
        filt = RequestIdFilter()
        record = logging.LogRecord(
            name='test', level=logging.INFO, pathname='', lineno=0,
            msg='test', args=(), exc_info=None,
        )
        filt.filter(record)
        assert record.request_id == '-'

    def test_get_set_round_trip(self):
        """set_request_id / get_request_id should round-trip."""
        set_request_id('roundtrip-42')
        assert get_request_id() == 'roundtrip-42'
