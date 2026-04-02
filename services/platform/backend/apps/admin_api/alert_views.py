"""
Admin API views — Alert Rules, Alert Logs, and test webhook endpoint.

Permission model:
- Alert rule management: org admin (scoped to own org) or superuser (all)
"""

import logging

from django.db.models import Q
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.alerting.dispatch import validate_webhook_url
from apps.alerting.models import DISPATCH_CHANNELS, RULE_TYPES, AlertRule
from apps.organizations.models import Organization
from apps.shared.admin_permissions import IsAdminOrSuperuser
from apps.shared.utils import add_cache_control, org_filter_queryset, paginate_queryset

logger = logging.getLogger("sequoia.admin_api.alert_views")


# ---------------------------------------------------------------------------
# Alert Rules (admin + superuser)
# ---------------------------------------------------------------------------


class AlertRuleListView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    @add_cache_control()
    def get(self, request: Request) -> Response:
        search = request.GET.get("search", "").strip()
        rules = org_filter_queryset(AlertRule.objects.all(), request.user)

        # Apply search filter
        if search:
            rules = rules.filter(Q(name__icontains=search) | Q(rule_type__icontains=search))

        # Apply pagination
        page, pagination_data = paginate_queryset(request, rules)

        results = []
        for rule in page:
            results.append(
                {
                    "id": str(rule.pk),
                    "name": rule.name,
                    "ruleType": rule.rule_type,
                    "threshold": rule.threshold,
                    "isActive": rule.is_active,
                    "dispatchChannel": rule.dispatch_channel,
                    "organizationId": str(rule.organization_id),
                }
            )
        return Response(
            {
                "results": results,
                "hasMore": pagination_data["hasMore"],
                "limit": pagination_data["limit"],
                "offset": pagination_data["offset"],
                "total": pagination_data["total"],
            }
        )

    def post(self, request: Request) -> Response:
        data = request.data
        name = data.get("name")
        rule_type = data.get("ruleType")

        if not name or not rule_type:
            return Response(
                {"detail": "name and ruleType are required", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate rule_type and dispatch_channel against allowed choices
        valid_rule_types = [c[0] for c in RULE_TYPES]
        if rule_type not in valid_rule_types:
            return Response(
                {
                    "detail": f"Invalid ruleType. Must be one of: {', '.join(valid_rule_types)}",
                    "code": "validation_error",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        dispatch_channel = data.get("dispatchChannel", "log")
        valid_channels = [c[0] for c in DISPATCH_CHANNELS]
        if dispatch_channel not in valid_channels:
            return Response(
                {
                    "detail": f"Invalid dispatchChannel. Must be one of: {', '.join(valid_channels)}",
                    "code": "validation_error",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # SSRF check on webhook URL
        webhook_url = data.get("webhookUrl", "")
        if dispatch_channel == "webhook" and webhook_url:
            ssrf_error = validate_webhook_url(webhook_url)
            if ssrf_error:
                return Response(
                    {"detail": f"Webhook URL rejected: {ssrf_error}", "code": "validation_error"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        org = request.user.organization if not request.user.is_superuser else None
        if request.user.is_superuser:
            org_id = data.get("organizationId")
            if org_id:
                try:
                    org = Organization.objects.get(pk=org_id)
                except Organization.DoesNotExist:
                    return Response(
                        {"detail": "Organization not found", "code": "org_invalid"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                return Response(
                    {"detail": "organizationId required for superuser", "code": "org_required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        rule = AlertRule.objects.create(
            organization=org,
            name=name,
            rule_type=rule_type,
            threshold=data.get("threshold"),
            incident_type_filter=data.get("incidentTypeFilter", []),
            tags_filter=data.get("tagsFilter", []),
            fiber_id_filter=data.get("fiberIdFilter", []),
            channel_start=data.get("channelStart"),
            channel_end=data.get("channelEnd"),
            dispatch_channel=data.get("dispatchChannel", "log"),
            webhook_url=data.get("webhookUrl", ""),
            webhook_secret=data.get("webhookSecret", ""),
            email_recipients=data.get("emailRecipients", []),
            cooldown_seconds=data.get("cooldownSeconds", 300),
            is_active=data.get("isActive", True),
        )
        return Response(
            {
                "id": str(rule.pk),
                "name": rule.name,
                "ruleType": rule.rule_type,
                "threshold": rule.threshold,
                "isActive": rule.is_active,
                "dispatchChannel": rule.dispatch_channel,
            },
            status=status.HTTP_201_CREATED,
        )


class AlertRuleDetailView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def _get_rule(self, request: Request, rule_id: str) -> tuple[AlertRule | None, Response | None]:
        try:
            return org_filter_queryset(AlertRule.objects.all(), request.user).get(pk=rule_id), None
        except AlertRule.DoesNotExist:
            return None, Response(
                {"detail": "Not found", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

    def patch(self, request: Request, rule_id: str) -> Response:
        rule, error = self._get_rule(request, rule_id)
        if error:
            return error
        assert rule is not None

        data = request.data
        if "name" in data:
            rule.name = data["name"]
        if "threshold" in data:
            rule.threshold = data["threshold"]
        if "isActive" in data:
            rule.is_active = data["isActive"]
        if "dispatchChannel" in data:
            valid_channels = [c[0] for c in DISPATCH_CHANNELS]
            if data["dispatchChannel"] not in valid_channels:
                return Response(
                    {
                        "detail": f"Invalid dispatchChannel. Must be one of: {', '.join(valid_channels)}"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            rule.dispatch_channel = data["dispatchChannel"]
        if "webhookUrl" in data:
            webhook_url = data["webhookUrl"]
            if webhook_url:
                ssrf_error = validate_webhook_url(webhook_url)
                if ssrf_error:
                    return Response(
                        {
                            "detail": f"Webhook URL rejected: {ssrf_error}",
                            "code": "validation_error",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            rule.webhook_url = webhook_url
        if "webhookSecret" in data:
            rule.webhook_secret = data["webhookSecret"]
        if "cooldownSeconds" in data:
            rule.cooldown_seconds = data["cooldownSeconds"]
        if "incidentTypeFilter" in data:
            rule.incident_type_filter = data["incidentTypeFilter"]
        if "tagsFilter" in data:
            rule.tags_filter = data["tagsFilter"]
        if "fiberIdFilter" in data:
            rule.fiber_id_filter = data["fiberIdFilter"]
        if "channelStart" in data:
            rule.channel_start = data["channelStart"]
        if "channelEnd" in data:
            rule.channel_end = data["channelEnd"]
        rule.save()

        return Response(
            {
                "id": str(rule.pk),
                "name": rule.name,
                "ruleType": rule.rule_type,
                "threshold": rule.threshold,
                "isActive": rule.is_active,
                "dispatchChannel": rule.dispatch_channel,
            }
        )

    def delete(self, request: Request, rule_id: str) -> Response:
        rule, error = self._get_rule(request, rule_id)
        if error:
            return error
        assert rule is not None
        rule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Alert Logs (admin + superuser)
# ---------------------------------------------------------------------------


class AlertLogListView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    @add_cache_control()
    def get(self, request: Request) -> Response:
        from apps.alerting.models import AlertLog

        search = request.GET.get("search", "").strip()

        if request.user.is_superuser:
            logs = AlertLog.objects.select_related("rule").all()
        else:
            logs = AlertLog.objects.select_related("rule").filter(
                rule__organization=request.user.organization
            )

        # Apply search filter
        if search:
            logs = logs.filter(Q(rule__name__icontains=search) | Q(detail__icontains=search))

        # Apply pagination
        page, pagination_data = paginate_queryset(request, logs)

        results = [
            {
                "id": str(log.pk),
                "ruleName": log.rule.name,
                "fiberId": log.fiber_id,
                "channel": log.channel,
                "detail": log.detail,
                "dispatchedAt": log.dispatched_at.isoformat(),
            }
            for log in page
        ]
        return Response(
            {
                "results": results,
                "hasMore": pagination_data["hasMore"],
                "limit": pagination_data["limit"],
                "offset": pagination_data["offset"],
                "total": pagination_data["total"],
            }
        )


# ---------------------------------------------------------------------------
# Alert Rule Test (admin + superuser)
# ---------------------------------------------------------------------------


class AlertRuleTestView(APIView):
    """Send a test webhook payload for an alert rule."""

    permission_classes = [IsAdminOrSuperuser]

    def post(self, request: Request, rule_id: str) -> Response:
        try:
            rule = org_filter_queryset(AlertRule.objects.all(), request.user).get(pk=rule_id)
        except AlertRule.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        from apps.alerting.dispatch import _dispatch_webhook

        _dispatch_webhook(
            rule, "test-incident-id", "test-fiber", 0, "Test alert from SequoIA", test=True
        )
        return Response({"detail": "Test payload sent."})
