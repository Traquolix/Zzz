"""
Tests for stale report cleanup management command.

Reports stuck in 'generating' for longer than the configured max age
should be marked 'failed' to prevent zombie entries in the UI.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.reporting.models import Report
from tests.factories import OrganizationFactory, UserFactory


@pytest.mark.django_db
class TestCleanupStaleReports(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory()
        cls.user = UserFactory(organization=cls.org)

    def _create_report(self, status='generating', age_minutes=0):
        report = Report.objects.create(
            organization=self.org,
            title='Test Report',
            created_by=self.user,
            start_time=timezone.now() - timedelta(days=1),
            end_time=timezone.now(),
            status=status,
        )
        if age_minutes:
            Report.objects.filter(pk=report.pk).update(
                created_at=timezone.now() - timedelta(minutes=age_minutes)
            )
        report.refresh_from_db()
        return report

    def test_stale_generating_report_marked_failed(self):
        """Reports stuck in 'generating' for >30 min should be marked 'failed'."""
        report = self._create_report(status='generating', age_minutes=45)
        call_command('cleanup_stale_reports', max_age_minutes=30)
        report.refresh_from_db()
        assert report.status == 'failed'

    def test_recent_generating_report_unchanged(self):
        """Reports generating for <30 min should NOT be touched."""
        report = self._create_report(status='generating', age_minutes=5)
        call_command('cleanup_stale_reports', max_age_minutes=30)
        report.refresh_from_db()
        assert report.status == 'generating'

    def test_completed_reports_not_affected(self):
        """Completed reports are not affected regardless of age."""
        report = self._create_report(status='completed', age_minutes=120)
        call_command('cleanup_stale_reports', max_age_minutes=30)
        report.refresh_from_db()
        assert report.status == 'completed'

    def test_failed_reports_not_affected(self):
        """Already failed reports are not double-touched."""
        report = self._create_report(status='failed', age_minutes=120)
        call_command('cleanup_stale_reports', max_age_minutes=30)
        report.refresh_from_db()
        assert report.status == 'failed'

    def test_pending_reports_not_affected(self):
        """Pending reports should not be affected."""
        report = self._create_report(status='pending', age_minutes=120)
        call_command('cleanup_stale_reports', max_age_minutes=30)
        report.refresh_from_db()
        assert report.status == 'pending'

    def test_default_max_age(self):
        """Default max age of 30 minutes should be applied when no arg given."""
        report = self._create_report(status='generating', age_minutes=45)
        call_command('cleanup_stale_reports')
        report.refresh_from_db()
        assert report.status == 'failed'
