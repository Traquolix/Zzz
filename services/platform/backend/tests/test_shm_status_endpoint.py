"""
Tests for the SHM status endpoint.
"""
import json
from unittest.mock import patch, MagicMock
import pytest
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.monitoring.models import Infrastructure
from apps.monitoring.shm_intelligence import SHMBaseline, FrequencyShift
from apps.organizations.models import Organization


User = get_user_model()


class SHMStatusViewTestCase(TestCase):
    """Test the SHM status endpoint."""

    def setUp(self):
        """Set up test client and authentication."""
        # Create an organization first
        self.org = Organization.objects.create(
            name='Test Organization',
            slug='test-org',
        )
        # Create a user with the organization
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_active=True,
            organization=self.org,
        )
        # Create infrastructure record for org-scope check
        Infrastructure.objects.create(
            id='test-infra-1',
            organization=self.org,
            type='bridge',
            name='Test Bridge',
            fiber_id='test-fiber',
            start_channel=0,
            end_channel=100,
        )

    def _get_authenticated_client(self):
        """Get an authenticated API client."""
        client = APIClient()
        client.force_authenticate(user=self.user)
        return client

    def test_endpoint_returns_correct_shape(self):
        """Test that the endpoint returns the correct response shape."""
        client = self._get_authenticated_client()
        infrastructure_id = 'test-infra-1'
        url = reverse('shm-status', kwargs={'infrastructure_id': infrastructure_id})

        with patch('apps.monitoring.shm_intelligence.compute_baseline') as mock_baseline, \
             patch('apps.monitoring.shm_intelligence.detect_frequency_shift') as mock_shift:

            # Mock baseline computation
            mock_baseline.return_value = SHMBaseline(
                mean_freq=1.10,
                std_freq=0.02,
                sample_count=20,
            )

            # Mock frequency shift detection
            mock_shift.return_value = FrequencyShift(
                current_mean=1.12,
                baseline_mean=1.10,
                deviation_sigma=1.0,
                direction='increase',
                is_anomalous=False,
                severity='normal',
            )

            response = client.get(url)

        assert response.status_code == 200
        data = json.loads(response.content)

        # Check response has all required keys
        assert 'status' in data
        assert 'currentMean' in data
        assert 'baselineMean' in data
        assert 'deviationSigma' in data
        assert 'direction' in data
        assert 'severity' in data

    def test_status_is_valid_value(self):
        """Test that status is one of the valid values."""
        client = self._get_authenticated_client()
        infrastructure_id = 'test-infra-1'
        url = reverse('shm-status', kwargs={'infrastructure_id': infrastructure_id})

        valid_statuses = {'nominal', 'warning', 'critical'}

        severities = ['normal', 'warning', 'alert', 'critical']

        for severity in severities:
            with patch('apps.monitoring.shm_intelligence.compute_baseline') as mock_baseline, \
                 patch('apps.monitoring.shm_intelligence.detect_frequency_shift') as mock_shift:

                mock_baseline.return_value = SHMBaseline(
                    mean_freq=1.10,
                    std_freq=0.02,
                    sample_count=20,
                )

                # Test all severity classifications map correctly
                mock_shift.return_value = FrequencyShift(
                    current_mean=1.12,
                    baseline_mean=1.10,
                    deviation_sigma=2.5 if severity != 'normal' else 1.0,
                    direction='increase',
                    is_anomalous=severity != 'normal',
                    severity=severity,
                )

                response = client.get(url)
                assert response.status_code == 200
                data = json.loads(response.content)
                assert data['status'] in valid_statuses

    def test_severity_mapping(self):
        """Test that severity classifications are mapped correctly."""
        client = self._get_authenticated_client()
        infrastructure_id = 'test-infra-1'
        url = reverse('shm-status', kwargs={'infrastructure_id': infrastructure_id})

        severity_map = {
            'normal': 'nominal',
            'warning': 'warning',
            'alert': 'warning',
            'critical': 'critical',
        }

        for severity, expected_status in severity_map.items():
            with patch('apps.monitoring.shm_intelligence.compute_baseline') as mock_baseline, \
                 patch('apps.monitoring.shm_intelligence.detect_frequency_shift') as mock_shift:

                mock_baseline.return_value = SHMBaseline(
                    mean_freq=1.10,
                    std_freq=0.02,
                    sample_count=20,
                )

                mock_shift.return_value = FrequencyShift(
                    current_mean=1.12,
                    baseline_mean=1.10,
                    deviation_sigma=2.5,
                    direction='increase',
                    is_anomalous=True,
                    severity=severity,
                )

                response = client.get(url)
                assert response.status_code == 200
                data = json.loads(response.content)
                assert data['status'] == expected_status, \
                    f"Severity {severity} should map to status {expected_status}"

    def test_numeric_values_are_rounded(self):
        """Test that numeric values are properly rounded."""
        client = self._get_authenticated_client()
        infrastructure_id = 'test-infra-1'
        url = reverse('shm-status', kwargs={'infrastructure_id': infrastructure_id})

        with patch('apps.monitoring.shm_intelligence.compute_baseline') as mock_baseline, \
             patch('apps.monitoring.shm_intelligence.detect_frequency_shift') as mock_shift:

            mock_baseline.return_value = SHMBaseline(
                mean_freq=1.1,
                std_freq=0.02,
                sample_count=20,
            )

            mock_shift.return_value = FrequencyShift(
                current_mean=1.123456789,
                baseline_mean=1.110987654,
                deviation_sigma=1.567890123,
                direction='increase',
                is_anomalous=False,
                severity='normal',
            )

            response = client.get(url)
            assert response.status_code == 200
            data = json.loads(response.content)

            # currentMean and baselineMean should be rounded to 4 decimals
            assert data['currentMean'] == round(1.123456789, 4)
            assert data['baselineMean'] == round(1.110987654, 4)
            # deviationSigma should be rounded to 2 decimals
            assert data['deviationSigma'] == round(1.567890123, 2)

    def test_direction_field_increase(self):
        """Test that direction field 'increase' is returned correctly."""
        client = self._get_authenticated_client()
        infrastructure_id = 'test-infra-1'
        url = reverse('shm-status', kwargs={'infrastructure_id': infrastructure_id})

        with patch('apps.monitoring.shm_intelligence.compute_baseline') as mock_baseline, \
             patch('apps.monitoring.shm_intelligence.detect_frequency_shift') as mock_shift:

            mock_baseline.return_value = SHMBaseline(
                mean_freq=1.10,
                std_freq=0.02,
                sample_count=20,
            )

            mock_shift.return_value = FrequencyShift(
                current_mean=1.12,
                baseline_mean=1.10,
                deviation_sigma=1.0,
                direction='increase',
                is_anomalous=False,
                severity='normal',
            )

            response = client.get(url)
            assert response.status_code == 200
            data = json.loads(response.content)
            assert data['direction'] == 'increase'

    def test_direction_field_decrease(self):
        """Test that direction field 'decrease' is returned correctly."""
        client = self._get_authenticated_client()
        infrastructure_id = 'test-infra-1'
        url = reverse('shm-status', kwargs={'infrastructure_id': infrastructure_id})

        with patch('apps.monitoring.shm_intelligence.compute_baseline') as mock_baseline, \
             patch('apps.monitoring.shm_intelligence.detect_frequency_shift') as mock_shift:

            mock_baseline.return_value = SHMBaseline(
                mean_freq=1.10,
                std_freq=0.02,
                sample_count=20,
            )

            mock_shift.return_value = FrequencyShift(
                current_mean=1.08,
                baseline_mean=1.10,
                deviation_sigma=1.0,
                direction='decrease',
                is_anomalous=False,
                severity='normal',
            )

            response = client.get(url)
            assert response.status_code == 200
            data = json.loads(response.content)
            assert data['direction'] == 'decrease'

    def test_direction_field_stable(self):
        """Test that direction field 'stable' is returned correctly."""
        client = self._get_authenticated_client()
        infrastructure_id = 'test-infra-1'
        url = reverse('shm-status', kwargs={'infrastructure_id': infrastructure_id})

        with patch('apps.monitoring.shm_intelligence.compute_baseline') as mock_baseline, \
             patch('apps.monitoring.shm_intelligence.detect_frequency_shift') as mock_shift:

            mock_baseline.return_value = SHMBaseline(
                mean_freq=1.10,
                std_freq=0.02,
                sample_count=20,
            )

            mock_shift.return_value = FrequencyShift(
                current_mean=1.10,
                baseline_mean=1.10,
                deviation_sigma=0.0,
                direction='stable',
                is_anomalous=False,
                severity='normal',
            )

            response = client.get(url)
            assert response.status_code == 200
            data = json.loads(response.content)
            assert data['direction'] == 'stable'

    def test_requires_authentication(self):
        """Test that endpoint requires authentication."""
        client = APIClient()
        infrastructure_id = 'test-infra-1'
        url = reverse('shm-status', kwargs={'infrastructure_id': infrastructure_id})

        response = client.get(url)
        # Should return 401 Unauthorized
        assert response.status_code == 401
