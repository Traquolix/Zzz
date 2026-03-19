"""
Reporting views — generate, list, view, and send reports.

All endpoints are org-scoped: non-superusers only see their org's reports.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.utils import get_org_fiber_ids
from apps.organizations.models import Organization
from apps.reporting.models import Report, ReportSchedule
from apps.reporting.serializers import (
    CreateScheduleSerializer,
    GenerateReportSerializer,
    ReportScheduleSerializer,
    ReportSerializer,
    SendReportSerializer,
)
from apps.reporting.task_runner import enqueue_report_generation
from apps.shared.permissions import IsActiveUser, IsNotViewer
from apps.shared.utils import org_filter_queryset

logger = logging.getLogger("sequoia.reporting")


class ReportListView(APIView):
    """GET /api/reports — list reports for current org."""

    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: ReportSerializer(many=True)},
        tags=["reports"],
    )
    def get(self, request: Request) -> Response:
        try:
            limit = min(int(request.query_params.get("limit", 50)), 200)
        except (ValueError, TypeError):
            limit = 50
        reports = list(
            org_filter_queryset(Report.objects.select_related("created_by"), request.user)[
                : limit + 1
            ]
        )
        has_more = len(reports) > limit
        page = reports[:limit]
        serializer = ReportSerializer(page, many=True)
        return Response(
            {
                "results": serializer.data,
                "hasMore": has_more,
                "limit": limit,
            }
        )


class ReportGenerateView(APIView):
    """POST /api/reports/generate — create and generate a report."""

    permission_classes = [IsActiveUser, IsNotViewer]

    @extend_schema(
        request=GenerateReportSerializer,
        responses={201: ReportSerializer},
        tags=["reports"],
    )
    def post(self, request: Request) -> Response:
        serializer = GenerateReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Determine organization and validate fiber access
        if request.user.is_superuser:
            org_id = data.get("organizationId")
            if not org_id:
                return Response(
                    {"detail": "organizationId required for superusers", "code": "org_required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                org = Organization.objects.get(pk=org_id)
            except Organization.DoesNotExist:
                return Response(
                    {"detail": "Organization not found", "code": "org_invalid"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Verify all requested fibers belong to the specified org
            allowed = set(get_org_fiber_ids(org))
            requested = set(data["fiberIds"])
            if not requested.issubset(allowed):
                return Response(
                    {
                        "detail": "Fibers not assigned to specified org",
                        "code": "fiber_access_denied",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            org = request.user.organization
            allowed = set(get_org_fiber_ids(org))
            requested = set(data["fiberIds"])
            if not requested.issubset(allowed):
                return Response(
                    {
                        "detail": "One or more fiber IDs are not accessible.",
                        "code": "fiber_access_denied",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        report = Report.objects.create(
            organization=org,
            title=data["title"],
            created_by=request.user,
            start_time=data["startTime"],
            end_time=data["endTime"],
            fiber_ids=data["fiberIds"],
            sections=data["sections"],
            recipients=data.get("recipients", []),
            status="pending",
        )

        # Enqueue background generation — returns immediately
        enqueue_report_generation(report.pk)

        out = ReportSerializer(report)
        return Response(out.data, status=status.HTTP_201_CREATED)


class ReportDetailView(APIView):
    """GET /api/reports/<uuid> — get report with HTML content."""

    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: ReportSerializer},
        tags=["reports"],
    )
    def get(self, request: Request, report_id: str) -> Response:
        try:
            report = org_filter_queryset(
                Report.objects.select_related("created_by"), request.user
            ).get(pk=report_id)
        except Report.DoesNotExist:
            return Response(
                {"detail": "Report not found", "code": "report_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = ReportSerializer(report).data
        data["htmlContent"] = report.html_content
        return Response(data)


class ReportSendView(APIView):
    """POST /api/reports/<uuid>/send — email the report to recipients."""

    permission_classes = [IsActiveUser, IsNotViewer]

    @extend_schema(
        request=SendReportSerializer,
        responses={200: {"type": "object", "properties": {"sent": {"type": "boolean"}}}},
        tags=["reports"],
    )
    def post(self, request: Request, report_id: str) -> Response:
        try:
            report = org_filter_queryset(
                Report.objects.select_related("created_by"), request.user
            ).get(pk=report_id)
        except Report.DoesNotExist:
            return Response(
                {"detail": "Report not found", "code": "report_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if report.status != "completed":
            return Response(
                {"detail": "Report is not ready to send.", "code": "report_not_ready"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SendReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recipients = serializer.validated_data.get("recipients") or report.recipients

        if not recipients:
            return Response(
                {"detail": "No recipients specified.", "code": "no_recipients"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@sequoia.local")

        try:
            send_mail(
                subject=f"SequoIA Report: {report.title}",
                message="Please view the attached HTML report.",
                from_email=from_email,
                recipient_list=recipients,
                html_message=report.html_content,
                fail_silently=False,
            )
            report.sent_at = timezone.now()
            report.save(update_fields=["sent_at"])
            logger.info("Report %s sent to %s", report.id, recipients)
        except Exception as e:
            logger.error("Failed to send report %s: %s", report.id, e)
            return Response(
                {"detail": "Email sending failed", "code": "email_failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"sent": True})


class ReportScheduleListView(APIView):
    """GET /api/reports/schedules — list schedules; POST — create new schedule."""

    def get_permissions(self) -> list[BasePermission]:
        perms: list[BasePermission] = [IsActiveUser()]
        if self.request.method == "POST":
            perms.append(IsNotViewer())
        return perms

    @extend_schema(
        responses={200: ReportScheduleSerializer(many=True)},
        tags=["reports"],
    )
    def get(self, request: Request) -> Response:
        try:
            limit = min(int(request.query_params.get("limit", 50)), 200)
        except (ValueError, TypeError):
            limit = 50
        schedules = list(
            org_filter_queryset(ReportSchedule.objects.select_related("created_by"), request.user)[
                : limit + 1
            ]
        )
        has_more = len(schedules) > limit
        page = schedules[:limit]
        serializer = ReportScheduleSerializer(page, many=True)
        return Response(
            {
                "results": serializer.data,
                "hasMore": has_more,
                "limit": limit,
            }
        )

    @extend_schema(
        request=CreateScheduleSerializer,
        responses={201: ReportScheduleSerializer},
        tags=["reports"],
    )
    def post(self, request: Request) -> Response:
        serializer = CreateScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Determine organization and validate fiber access
        if request.user.is_superuser:
            org_id = request.data.get("organizationId")
            if not org_id:
                return Response(
                    {"detail": "organizationId required for superusers", "code": "org_required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                org = Organization.objects.get(pk=org_id)
            except Organization.DoesNotExist:
                return Response(
                    {"detail": "Organization not found", "code": "org_invalid"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Verify all requested fibers belong to the specified org
            allowed = set(get_org_fiber_ids(org))
            requested = set(data["fiberIds"])
            if not requested.issubset(allowed):
                return Response(
                    {
                        "detail": "Fibers not assigned to specified org",
                        "code": "fiber_access_denied",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            org = request.user.organization
            allowed = set(get_org_fiber_ids(org))
            requested = set(data["fiberIds"])
            if not requested.issubset(allowed):
                return Response(
                    {
                        "detail": "One or more fiber IDs are not accessible.",
                        "code": "fiber_access_denied",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        schedule = ReportSchedule.objects.create(
            organization=org,
            created_by=request.user,
            title=data["title"],
            frequency=data["frequency"],
            fiber_ids=data["fiberIds"],
            sections=data["sections"],
            recipients=data.get("recipients", []),
            is_active=True,
        )

        out = ReportScheduleSerializer(schedule)
        return Response(out.data, status=status.HTTP_201_CREATED)


class ReportScheduleDetailView(APIView):
    """DELETE /api/reports/schedules/<uuid> — delete a schedule."""

    permission_classes = [IsActiveUser, IsNotViewer]

    @extend_schema(
        responses={204: None},
        tags=["reports"],
    )
    def delete(self, request: Request, schedule_id: str) -> Response:
        try:
            schedule = org_filter_queryset(
                ReportSchedule.objects.select_related("created_by"), request.user
            ).get(pk=schedule_id)
        except ReportSchedule.DoesNotExist:
            return Response(
                {"detail": "Schedule not found", "code": "schedule_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        schedule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
