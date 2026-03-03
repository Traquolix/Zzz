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
from apps.organizations.models import Organization
from apps.reporting.models import Report, ReportSchedule
from apps.reporting.task_runner import enqueue_report_generation
from apps.reporting.serializers import (
    GenerateReportSerializer,
    ReportSerializer,
    SendReportSerializer,
    ReportScheduleSerializer,
    CreateScheduleSerializer,
)
from apps.shared.permissions import IsActiveUser, IsNotViewer

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
        try:
            limit = min(int(request.query_params.get('limit', 50)), 200)
        except (ValueError, TypeError):
            limit = 50
        reports = list(_get_org_reports(request.user)[:limit + 1])
        has_more = len(reports) > limit
        page = reports[:limit]
        serializer = ReportSerializer(page, many=True)
        return Response({
            'results': serializer.data,
            'hasMore': has_more,
            'limit': limit,
        })


class ReportGenerateView(APIView):
    """POST /api/reports/generate — create and generate a report."""
    permission_classes = [IsActiveUser, IsNotViewer]

    @extend_schema(
        request=GenerateReportSerializer,
        responses={201: ReportSerializer},
        tags=['reports'],
    )
    def post(self, request):
        serializer = GenerateReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Determine organization and validate fiber access
        if request.user.is_superuser:
            org_id = data.get('organizationId')
            if not org_id:
                return Response(
                    {'detail': 'organizationId required for superusers', 'code': 'org_required'},
                    status=400,
                )
            try:
                org = Organization.objects.get(pk=org_id)
            except Organization.DoesNotExist:
                return Response(
                    {'detail': 'Organization not found', 'code': 'org_invalid'},
                    status=400,
                )
            # Verify all requested fibers belong to the specified org
            allowed = set(get_org_fiber_ids(org))
            requested = set(data['fiberIds'])
            if not requested.issubset(allowed):
                return Response(
                    {'detail': 'Fibers not assigned to specified org', 'code': 'fiber_access_denied'},
                    status=403,
                )
        else:
            org = request.user.organization
            allowed = set(get_org_fiber_ids(org))
            requested = set(data['fiberIds'])
            if not requested.issubset(allowed):
                return Response(
                    {'detail': 'One or more fiber IDs are not accessible.', 'code': 'fiber_access_denied'},
                    status=403,
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
            status='pending',
        )

        # Enqueue background generation — returns immediately
        enqueue_report_generation(report.pk)

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
    permission_classes = [IsActiveUser, IsNotViewer]

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
            return Response({'detail': 'Email sending failed', 'code': 'email_failed'}, status=500)

        return Response({'sent': True})


def _get_org_schedules(user):
    """Return queryset of schedules scoped to the user's org."""
    qs = ReportSchedule.objects.select_related('created_by')
    if not user.is_superuser:
        qs = qs.filter(organization=user.organization)
    return qs


class ReportScheduleListView(APIView):
    """GET /api/reports/schedules — list schedules; POST — create new schedule."""

    def get_permissions(self):
        perms = [IsActiveUser()]
        if self.request.method == 'POST':
            perms.append(IsNotViewer())
        return perms

    @extend_schema(
        responses={200: ReportScheduleSerializer(many=True)},
        tags=['reports'],
    )
    def get(self, request):
        try:
            limit = min(int(request.query_params.get('limit', 50)), 200)
        except (ValueError, TypeError):
            limit = 50
        schedules = list(_get_org_schedules(request.user)[:limit + 1])
        has_more = len(schedules) > limit
        page = schedules[:limit]
        serializer = ReportScheduleSerializer(page, many=True)
        return Response({
            'results': serializer.data,
            'hasMore': has_more,
            'limit': limit,
        })

    @extend_schema(
        request=CreateScheduleSerializer,
        responses={201: ReportScheduleSerializer},
        tags=['reports'],
    )
    def post(self, request):
        serializer = CreateScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Determine organization and validate fiber access
        if request.user.is_superuser:
            org_id = request.data.get('organizationId')
            if not org_id:
                return Response(
                    {'detail': 'organizationId required for superusers', 'code': 'org_required'},
                    status=400,
                )
            try:
                org = Organization.objects.get(pk=org_id)
            except Organization.DoesNotExist:
                return Response(
                    {'detail': 'Organization not found', 'code': 'org_invalid'},
                    status=400,
                )
            # Verify all requested fibers belong to the specified org
            allowed = set(get_org_fiber_ids(org))
            requested = set(data['fiberIds'])
            if not requested.issubset(allowed):
                return Response(
                    {'detail': 'Fibers not assigned to specified org', 'code': 'fiber_access_denied'},
                    status=403,
                )
        else:
            org = request.user.organization
            allowed = set(get_org_fiber_ids(org))
            requested = set(data['fiberIds'])
            if not requested.issubset(allowed):
                return Response(
                    {'detail': 'One or more fiber IDs are not accessible.', 'code': 'fiber_access_denied'},
                    status=403,
                )

        schedule = ReportSchedule.objects.create(
            organization=org,
            created_by=request.user,
            title=data['title'],
            frequency=data['frequency'],
            fiber_ids=data['fiberIds'],
            sections=data['sections'],
            recipients=data.get('recipients', []),
            is_active=True,
        )

        out = ReportScheduleSerializer(schedule)
        return Response(out.data, status=201)


class ReportScheduleDetailView(APIView):
    """DELETE /api/reports/schedules/<uuid> — delete a schedule."""
    permission_classes = [IsActiveUser, IsNotViewer]

    @extend_schema(
        responses={204: None},
        tags=['reports'],
    )
    def delete(self, request, schedule_id):
        try:
            schedule = _get_org_schedules(request.user).get(pk=schedule_id)
        except ReportSchedule.DoesNotExist:
            return Response({'detail': 'Schedule not found', 'code': 'schedule_not_found'}, status=404)

        schedule.delete()
        return Response(status=204)
