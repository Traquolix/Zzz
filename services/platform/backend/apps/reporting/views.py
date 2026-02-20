"""
Reporting views — generate, list, view, and send reports.

All endpoints are org-scoped: non-superusers only see their org's reports.
"""

import logging

from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.utils import get_org_fiber_ids
from apps.reporting.models import Report
from apps.reporting.report_builder import build_report_html
from apps.reporting.serializers import (
    GenerateReportSerializer,
    ReportSerializer,
    SendReportSerializer,
)
from apps.shared.permissions import IsActiveUser

logger = logging.getLogger('sequoia.reporting')


def _get_org_reports(user):
    """Return queryset of reports scoped to the user's org."""
    qs = Report.objects.select_related('created_by')
    if not user.is_superuser:
        qs = qs.filter(organization=user.organization)
    return qs


class ReportListView(APIView):
    """GET /api/reports — list reports for current org."""
    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: ReportSerializer(many=True)},
        tags=['reports'],
    )
    def get(self, request):
        reports = _get_org_reports(request.user)[:50]
        serializer = ReportSerializer(reports, many=True)
        return Response(serializer.data)


class ReportGenerateView(APIView):
    """POST /api/reports/generate — create and generate a report."""
    permission_classes = [IsActiveUser]

    @extend_schema(
        request=GenerateReportSerializer,
        responses={201: ReportSerializer},
        tags=['reports'],
    )
    def post(self, request):
        serializer = GenerateReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Verify requested fibers belong to user's org
        if not request.user.is_superuser:
            allowed = set(get_org_fiber_ids(request.user.organization))
            requested = set(data['fiberIds'])
            if not requested.issubset(allowed):
                return Response(
                    {'detail': 'One or more fiber IDs are not accessible.', 'code': 'fiber_access_denied'},
                    status=403,
                )

        org = request.user.organization if not request.user.is_superuser else None
        if org is None:
            # Superuser: use the org of the first fiber or a fallback
            from apps.fibers.models import FiberAssignment
            assignment = FiberAssignment.objects.filter(
                fiber_id=data['fiberIds'][0]
            ).first()
            if assignment:
                org = assignment.organization
            else:
                return Response(
                    {'detail': 'Cannot determine organization for these fibers.', 'code': 'org_unknown'},
                    status=400,
                )

        report = Report.objects.create(
            organization=org,
            title=data['title'],
            created_by=request.user,
            start_time=data['startTime'],
            end_time=data['endTime'],
            fiber_ids=data['fiberIds'],
            sections=data['sections'],
            recipients=data.get('recipients', []),
            status='generating',
        )

        try:
            report.html_content = build_report_html(report)
            report.status = 'completed'
        except Exception as e:
            logger.error('Report generation failed: %s', e)
            report.status = 'failed'

        report.save()

        out = ReportSerializer(report)
        return Response(out.data, status=201)


class ReportDetailView(APIView):
    """GET /api/reports/<uuid> — get report with HTML content."""
    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: ReportSerializer},
        tags=['reports'],
    )
    def get(self, request, report_id):
        try:
            report = _get_org_reports(request.user).get(pk=report_id)
        except Report.DoesNotExist:
            return Response({'detail': 'Report not found', 'code': 'report_not_found'}, status=404)

        data = ReportSerializer(report).data
        data['htmlContent'] = report.html_content
        return Response(data)


class ReportSendView(APIView):
    """POST /api/reports/<uuid>/send — email the report to recipients."""
    permission_classes = [IsActiveUser]

    @extend_schema(
        request=SendReportSerializer,
        responses={200: {'type': 'object', 'properties': {'sent': {'type': 'boolean'}}}},
        tags=['reports'],
    )
    def post(self, request, report_id):
        try:
            report = _get_org_reports(request.user).get(pk=report_id)
        except Report.DoesNotExist:
            return Response({'detail': 'Report not found', 'code': 'report_not_found'}, status=404)

        if report.status != 'completed':
            return Response({'detail': 'Report is not ready to send.', 'code': 'report_not_ready'}, status=400)

        serializer = SendReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recipients = serializer.validated_data.get('recipients') or report.recipients

        if not recipients:
            return Response({'detail': 'No recipients specified.', 'code': 'no_recipients'}, status=400)

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@sequoia.local')

        try:
            send_mail(
                subject=f'SequoIA Report: {report.title}',
                message='Please view the attached HTML report.',
                from_email=from_email,
                recipient_list=recipients,
                html_message=report.html_content,
                fail_silently=False,
            )
            report.sent_at = timezone.now()
            report.save(update_fields=['sent_at'])
            logger.info('Report %s sent to %s', report.id, recipients)
        except Exception as e:
            logger.error('Failed to send report %s: %s', report.id, e)
            return Response({'detail': f'Email sending failed: {e}', 'code': 'email_failed'}, status=500)

        return Response({'sent': True})
