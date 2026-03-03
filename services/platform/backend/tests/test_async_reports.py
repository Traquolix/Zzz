"""
TDD tests for async report generation and scheduled reports.

Async generation:
1. POST /api/reports/generate returns immediately with status='pending'
2. Report is built in a background thread
3. GET /api/reports/<id> shows status progression (pending → generating → completed)

Scheduled reports:
1. ReportSchedule model stores cron-like config (daily/weekly/monthly)
2. run_scheduled_reports() finds due schedules and enqueues generation
3. Completed scheduled reports auto-send to configured recipients
"""

from datetime import timedelta
from unittest.mock import patch, MagicMock
import threading
import time

import pytest
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.reporting.models import Report, ReportSchedule
from apps.reporting.task_runner import generate_report_async, run_scheduled_reports


@pytest.mark.django_db
class TestAsyncReportGeneration(TestCase):

    @classmethod
    def setUpTestData(cls):
        from apps.organizations.models import Organization, OrganizationSettings
        from apps.accounts.models import User
        from apps.fibers.models import FiberAssignment

        cls.org = Organization.objects.create(name='Async Org', slug='async-org')
        OrganizationSettings.objects.create(organization=cls.org)
        cls.user = User.objects.create_user(
            username='async_user', password='pass123',
            organization=cls.org, role='operator',
        )
        FiberAssignment.objects.create(organization=cls.org, fiber_id='carros')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch('apps.reporting.report_builder.build_report_html')
    def test_generate_returns_pending(self, mock_build):
        """POST should return immediately with status='pending'."""
        mock_build.return_value = '<h1>Report</h1>'

        resp = self.client.post('/api/reports/generate', {
            'title': 'Async Test Report',
            'startTime': '2026-02-01T00:00:00Z',
            'endTime': '2026-02-28T23:59:59Z',
            'fiberIds': ['carros'],
            'sections': ['incidents'],
        }, format='json')
        assert resp.status_code == 201
        assert resp.data['status'] == 'pending'

    @patch('apps.reporting.report_builder.build_report_html')
    def test_background_thread_completes_report(self, mock_build):
        """After the background thread finishes, report status should be 'completed'."""
        mock_build.return_value = '<h1>Done</h1>'

        report = Report.objects.create(
            organization=self.org,
            title='Thread Test',
            created_by=self.user,
            start_time=timezone.now() - timedelta(hours=24),
            end_time=timezone.now(),
            fiber_ids=['carros'],
            sections=['incidents'],
            status='pending',
        )

        # Run synchronously (not in thread) for test determinism
        generate_report_async(report.pk)

        report.refresh_from_db()
        assert report.status == 'completed'
        assert '<h1>Done</h1>' in report.html_content

    @patch('apps.reporting.report_builder.build_report_html')
    def test_background_thread_marks_failed_on_error(self, mock_build):
        mock_build.side_effect = Exception('ClickHouse timeout')

        report = Report.objects.create(
            organization=self.org,
            title='Fail Test',
            created_by=self.user,
            start_time=timezone.now() - timedelta(hours=24),
            end_time=timezone.now(),
            fiber_ids=['carros'],
            sections=['incidents'],
            status='pending',
        )

        generate_report_async(report.pk)

        report.refresh_from_db()
        assert report.status == 'failed'


@pytest.mark.django_db
class TestReportScheduleModel(TestCase):

    @classmethod
    def setUpTestData(cls):
        from apps.organizations.models import Organization, OrganizationSettings
        from apps.accounts.models import User
        from apps.fibers.models import FiberAssignment

        cls.org = Organization.objects.create(name='Sched Org', slug='sched-org')
        OrganizationSettings.objects.create(organization=cls.org)
        cls.user = User.objects.create_user(
            username='sched_user', password='pass123',
            organization=cls.org, role='admin',
        )
        FiberAssignment.objects.create(organization=cls.org, fiber_id='carros')

    def test_create_daily_schedule(self):
        sched = ReportSchedule.objects.create(
            organization=self.org,
            created_by=self.user,
            title='Daily Traffic Summary',
            frequency='daily',
            fiber_ids=['carros'],
            sections=['speed', 'volume'],
            recipients=['ops@example.com'],
            is_active=True,
        )
        assert sched.pk is not None
        assert sched.frequency == 'daily'

    def test_create_weekly_schedule(self):
        sched = ReportSchedule.objects.create(
            organization=self.org,
            created_by=self.user,
            title='Weekly Incident Report',
            frequency='weekly',
            fiber_ids=['carros'],
            sections=['incidents'],
            recipients=['manager@example.com'],
        )
        assert sched.frequency == 'weekly'

    @patch('apps.reporting.report_builder.build_report_html')
    def test_run_scheduled_creates_report(self, mock_build):
        mock_build.return_value = '<h1>Scheduled</h1>'

        sched = ReportSchedule.objects.create(
            organization=self.org,
            created_by=self.user,
            title='Due Schedule',
            frequency='daily',
            fiber_ids=['carros'],
            sections=['incidents'],
            recipients=['test@example.com'],
            is_active=True,
            # Last run was 25 hours ago — due now
            last_run_at=timezone.now() - timedelta(hours=25),
        )

        count = run_scheduled_reports()
        assert count == 1

        sched.refresh_from_db()
        assert sched.last_run_at is not None
        # A report should have been created
        assert Report.objects.filter(
            organization=self.org,
            title__contains='Due Schedule',
        ).exists()

    @patch('apps.reporting.report_builder.build_report_html')
    def test_not_due_schedule_is_skipped(self, mock_build):
        """Schedule that ran recently should not trigger."""
        ReportSchedule.objects.create(
            organization=self.org,
            created_by=self.user,
            title='Recent Schedule',
            frequency='daily',
            fiber_ids=['carros'],
            sections=['incidents'],
            is_active=True,
            last_run_at=timezone.now() - timedelta(hours=1),  # just ran
        )

        count = run_scheduled_reports()
        assert count == 0

    def test_inactive_schedule_is_skipped(self):
        ReportSchedule.objects.create(
            organization=self.org,
            created_by=self.user,
            title='Inactive',
            frequency='daily',
            fiber_ids=['carros'],
            sections=['incidents'],
            is_active=False,
        )
        count = run_scheduled_reports()
        assert count == 0
