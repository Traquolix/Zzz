"""
Admin API views — CRUD for organizations, users, infrastructure, alert rules.

Permission model:
- Organization CRUD: superuser only
- User/Infrastructure/AlertRule: org admin (scoped to own org) or superuser (all)
"""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.db.models import Q
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.alerting.dispatch import validate_webhook_url
from apps.alerting.models import DISPATCH_CHANNELS, RULE_TYPES, AlertRule
from apps.api_keys.models import APIKey
from apps.fibers.models import FiberAssignment
from apps.fibers.utils import invalidate_fiber_org_map, invalidate_org_fiber_cache
from apps.monitoring.models import Infrastructure
from apps.organizations.models import Organization, OrganizationSettings
from apps.shared.admin_permissions import IsAdminOrSuperuser, IsSuperuser
from apps.shared.utils import org_filter_queryset, paginate_queryset

logger = logging.getLogger("sequoia.admin")


def add_cache_control(max_age: int = 300) -> Callable[..., Any]:
    """Decorator to add Cache-Control headers to response.

    Admin endpoints serve private org-scoped data, so always use
    'private' to prevent CDN/proxy caching.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(self: Any, request: Request, *args: Any, **kwargs: Any) -> Response:
            response = func(self, request, *args, **kwargs)
            if max_age > 0:
                response["Cache-Control"] = f"private, max-age={max_age}"
            else:
                response["Cache-Control"] = "private, no-store"
            return response

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Organizations (superuser only)
# ---------------------------------------------------------------------------


class OrganizationListView(APIView):
    permission_classes = [IsSuperuser]

    @add_cache_control()
    def get(self, request: Request) -> Response:
        search = request.GET.get("search", "").strip()
        orgs = Organization.objects.prefetch_related("settings", "fiber_assignments").all()

        # Apply search filter
        if search:
            orgs = orgs.filter(Q(name__icontains=search) | Q(slug__icontains=search))

        # Apply pagination
        page, pagination_data = paginate_queryset(request, orgs)

        results = []
        for org in page:
            fiber_assignments = []
            for fa in org.fiber_assignments.all():
                fiber_assignments.append(
                    {
                        "id": str(fa.pk),
                        "fiberId": fa.fiber_id,
                        "assignedAt": fa.assigned_at.isoformat(),
                    }
                )
            settings = getattr(org, "settings", None)
            results.append(
                {
                    "id": str(org.pk),
                    "name": org.name,
                    "slug": org.slug,
                    "isActive": org.is_active,
                    "createdAt": org.created_at.isoformat(),
                    "allowedWidgets": settings.allowed_widgets if settings else [],
                    "allowedLayers": settings.allowed_layers if settings else [],
                    "fiberAssignments": fiber_assignments,
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
        name = request.data.get("name")
        if not name:
            return Response(
                {"detail": "Name is required", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        org = Organization.objects.create(name=name)
        # Auto-create settings
        OrganizationSettings.objects.get_or_create(organization=org)
        return Response(
            {
                "id": str(org.pk),
                "name": org.name,
                "slug": org.slug,
                "isActive": org.is_active,
            },
            status=status.HTTP_201_CREATED,
        )


class OrganizationDetailView(APIView):
    permission_classes = [IsSuperuser]

    def patch(self, request: Request, org_id: str) -> Response:
        try:
            org = Organization.objects.get(pk=org_id)
        except Organization.DoesNotExist:
            return Response(
                {"detail": "Organization not found", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if "name" in request.data:
            org.name = request.data["name"]
        if "isActive" in request.data:
            org.is_active = request.data["isActive"]
        org.save()
        return Response(
            {
                "id": str(org.pk),
                "name": org.name,
                "slug": org.slug,
                "isActive": org.is_active,
            }
        )


class OrgSettingsView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request: Request, org_id: str) -> Response:
        # Org admin can only GET their own org's settings
        # Superuser can GET any
        if not request.user.is_superuser and str(request.user.organization_id) != str(org_id):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            settings = OrganizationSettings.objects.select_related("organization").get(
                organization_id=org_id
            )
        except OrganizationSettings.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "timezone": settings.timezone,
                "speedAlertThreshold": settings.speed_alert_threshold,
                "incidentAutoResolveMinutes": settings.incident_auto_resolve_minutes,
                "shmEnabled": settings.shm_enabled,
                "allowedWidgets": settings.allowed_widgets,
                "allowedLayers": settings.allowed_layers,
            }
        )

    def patch(self, request: Request, org_id: str) -> Response:
        if not request.user.is_superuser and str(request.user.organization_id) != str(org_id):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            settings = OrganizationSettings.objects.get(organization_id=org_id)
        except OrganizationSettings.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data

        # Fields org admin CAN edit
        if "timezone" in data:
            settings.timezone = data["timezone"]
        if "speedAlertThreshold" in data:
            settings.speed_alert_threshold = data["speedAlertThreshold"]
        if "incidentAutoResolveMinutes" in data:
            settings.incident_auto_resolve_minutes = data["incidentAutoResolveMinutes"]
        if "shmEnabled" in data:
            settings.shm_enabled = data["shmEnabled"]

        # Fields ONLY superuser can edit
        if "allowedWidgets" in data:
            if not request.user.is_superuser:
                return Response(
                    {"detail": "Only superusers can edit widget restrictions"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            widgets = data["allowedWidgets"]
            from apps.shared.constants import ALL_WIDGETS

            invalid = [w for w in widgets if w not in ALL_WIDGETS]
            if invalid:
                return Response(
                    {"detail": f"Invalid widget keys: {', '.join(invalid)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            settings.allowed_widgets = widgets

        if "allowedLayers" in data:
            if not request.user.is_superuser:
                return Response(
                    {"detail": "Only superusers can edit layer restrictions"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            layers = data["allowedLayers"]
            from apps.shared.constants import ALL_LAYERS

            invalid = [layer for layer in layers if layer not in ALL_LAYERS]
            if invalid:
                return Response(
                    {"detail": f"Invalid layer keys: {', '.join(invalid)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            settings.allowed_layers = layers

        settings.save()
        return Response(
            {
                "timezone": settings.timezone,
                "speedAlertThreshold": settings.speed_alert_threshold,
                "incidentAutoResolveMinutes": settings.incident_auto_resolve_minutes,
                "shmEnabled": settings.shm_enabled,
                "allowedWidgets": settings.allowed_widgets,
                "allowedLayers": settings.allowed_layers,
            }
        )


# ---------------------------------------------------------------------------
# Users (admin + superuser)
# ---------------------------------------------------------------------------


class UserListView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    @add_cache_control()
    def get(self, request: Request) -> Response:
        search = request.GET.get("search", "").strip()
        users = org_filter_queryset(User.objects.select_related("organization"), request.user)

        # Apply search filter
        if search:
            users = users.filter(Q(username__icontains=search) | Q(email__icontains=search))

        # Apply pagination
        page, pagination_data = paginate_queryset(request, users)

        results = []
        for u in page:
            results.append(
                {
                    "id": str(u.pk),
                    "username": u.username,
                    "email": u.email,
                    "role": u.role,
                    "isActive": u.is_active,
                    "organizationId": str(u.organization_id) if u.organization_id else None,
                    "organizationName": u.organization.name if u.organization else None,
                    "allowedWidgets": u.allowed_widgets,
                    "allowedLayers": u.allowed_layers,
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
        username = request.data.get("username")
        password = request.data.get("password")
        role = request.data.get("role", "viewer")

        if not username or not password:
            return Response(
                {"detail": "Username and password are required", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate role against allowed choices
        from apps.shared.constants import USER_ROLES

        valid_roles = [r[0] for r in USER_ROLES]
        if role not in valid_roles:
            return Response(
                {
                    "detail": f"Invalid role. Must be one of: {', '.join(valid_roles)}",
                    "code": "validation_error",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate password strength
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            validate_password(password)
        except DjangoValidationError as e:
            return Response(
                {"detail": e.messages[0], "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine org: admin creates in their own org; superuser can specify
        if request.user.is_superuser:
            org_id = request.data.get("organizationId")
            org = None
            if org_id:
                try:
                    org = Organization.objects.get(pk=org_id)
                except Organization.DoesNotExist:
                    return Response(
                        {"detail": "Organization not found", "code": "org_invalid"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        else:
            org = request.user.organization

        user = User.objects.create_user(
            username=username,
            password=password,
            email=request.data.get("email", ""),
            organization=org,
            role=role,
        )
        return Response(
            {
                "id": str(user.pk),
                "username": user.username,
                "role": user.role,
                "organizationId": str(user.organization_id) if user.organization_id else None,
            },
            status=status.HTTP_201_CREATED,
        )


class UserDetailView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def patch(self, request: Request, user_id: str) -> Response:
        try:
            user = org_filter_queryset(User.objects.all(), request.user).get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data

        # Prevent self-modification of role and active status
        if str(user.pk) == str(request.user.pk) and ("role" in data or "isActive" in data):
            return Response(
                {
                    "detail": "Cannot modify your own role or active status",
                    "code": "self_modification",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "role" in data:
            from apps.shared.constants import USER_ROLES

            valid_roles = [r[0] for r in USER_ROLES]
            if data["role"] not in valid_roles:
                return Response(
                    {"detail": f"Invalid role. Must be one of: {', '.join(valid_roles)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.role = data["role"]
        if "email" in data:
            user.email = data["email"]
        if "isActive" in data:
            user.is_active = data["isActive"]
        if "allowedWidgets" in data:
            from apps.shared.constants import ALL_WIDGETS

            invalid = [w for w in data["allowedWidgets"] if w not in ALL_WIDGETS]
            if invalid:
                return Response(
                    {"detail": f"Invalid widget keys: {', '.join(invalid)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.allowed_widgets = data["allowedWidgets"]
        if "allowedLayers" in data:
            from apps.shared.constants import ALL_LAYERS

            invalid = [layer for layer in data["allowedLayers"] if layer not in ALL_LAYERS]
            if invalid:
                return Response(
                    {"detail": f"Invalid layer keys: {', '.join(invalid)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.allowed_layers = data["allowedLayers"]

        user.save()
        return Response(
            {
                "id": str(user.pk),
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "isActive": user.is_active,
                "allowedWidgets": user.allowed_widgets,
                "allowedLayers": user.allowed_layers,
                "organizationId": str(user.organization_id) if user.organization_id else None,
            }
        )


# ---------------------------------------------------------------------------
# Infrastructure (admin + superuser)
# ---------------------------------------------------------------------------


class InfrastructureAdminListView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    @add_cache_control()
    def get(self, request: Request) -> Response:
        search = request.GET.get("search", "").strip()
        items = org_filter_queryset(Infrastructure.objects.all(), request.user)

        # Apply search filter
        if search:
            items = items.filter(Q(name__icontains=search) | Q(type__icontains=search))

        # Apply pagination
        page, pagination_data = paginate_queryset(request, items)

        results = []
        for item in page:
            results.append(
                {
                    "id": item.id,
                    "name": item.name,
                    "type": item.type,
                    "fiberId": item.fiber_id,
                    "direction": item.direction,
                    "startChannel": item.start_channel,
                    "endChannel": item.end_channel,
                    "organizationId": str(item.organization_id),
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
        required = ["id", "name", "type", "fiberId", "startChannel", "endChannel"]
        missing = [f for f in required if f not in data]
        if missing:
            return Response(
                {"detail": f"Missing fields: {', '.join(missing)}", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.shared.constants import INFRASTRUCTURE_TYPES

        valid_types = [t[0] for t in INFRASTRUCTURE_TYPES]
        if data["type"] not in valid_types:
            return Response(
                {
                    "detail": f"Invalid type. Must be one of: {', '.join(valid_types)}",
                    "code": "validation_error",
                },
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

        infra = Infrastructure.objects.create(
            id=data["id"],
            name=data["name"],
            type=data["type"],
            organization=org,
            fiber_id=data["fiberId"],
            direction=data.get("direction"),
            start_channel=data["startChannel"],
            end_channel=data["endChannel"],
            image=data.get("image", ""),
        )
        return Response(
            {
                "id": infra.id,
                "name": infra.name,
                "type": infra.type,
            },
            status=status.HTTP_201_CREATED,
        )


class InfrastructureAdminDetailView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def delete(self, request: Request, infra_id: str) -> Response:
        try:
            item = org_filter_queryset(Infrastructure.objects.all(), request.user).get(id=infra_id)
        except Infrastructure.DoesNotExist:
            return Response(
                {"detail": "Not found", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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
            severity_filter=data.get("severityFilter", []),
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
        if "severityFilter" in data:
            rule.severity_filter = data["severityFilter"]
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
# Fiber Assignments (superuser only)
# ---------------------------------------------------------------------------


class FiberAssignmentListView(APIView):
    permission_classes = [IsSuperuser]

    def get(self, request: Request, org_id: str) -> Response:
        assignments = FiberAssignment.objects.filter(organization_id=org_id)
        results = [
            {"id": str(a.pk), "fiberId": a.fiber_id, "assignedAt": a.assigned_at.isoformat()}
            for a in assignments
        ]
        return Response({"results": results})

    def post(self, request: Request, org_id: str) -> Response:
        fiber_id = request.data.get("fiberId")
        if not fiber_id:
            return Response({"detail": "fiberId is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            Organization.objects.get(pk=org_id)
        except Organization.DoesNotExist:
            return Response({"detail": "Organization not found"}, status=status.HTTP_404_NOT_FOUND)
        if FiberAssignment.objects.filter(organization_id=org_id, fiber_id=fiber_id).exists():
            return Response(
                {"detail": "Fiber already assigned to this organization"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        assignment = FiberAssignment.objects.create(organization_id=org_id, fiber_id=fiber_id)
        invalidate_org_fiber_cache(org_id)
        invalidate_fiber_org_map()
        return Response(
            {
                "id": str(assignment.pk),
                "fiberId": assignment.fiber_id,
                "assignedAt": assignment.assigned_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class FiberAssignmentDetailView(APIView):
    permission_classes = [IsSuperuser]

    def delete(self, request: Request, org_id: str, assignment_id: str) -> Response:
        try:
            assignment = FiberAssignment.objects.get(pk=assignment_id, organization_id=org_id)
        except FiberAssignment.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        assignment.delete()
        invalidate_org_fiber_cache(org_id)
        invalidate_fiber_org_map()
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
# API Keys (admin + superuser)
# ---------------------------------------------------------------------------


class APIKeyListView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request: Request) -> Response:
        keys = org_filter_queryset(APIKey.objects.filter(is_active=True), request.user)
        results = [
            {
                "id": str(k.pk),
                "name": k.name,
                "prefix": k.key_prefix,
                "scopes": k.scopes,
                "createdAt": k.created_at.isoformat(),
                "requestCount": k.request_count,
                "lastUsedAt": k.last_used_at.isoformat() if k.last_used_at else None,
                "expiresAt": k.expires_at.isoformat() if k.expires_at else None,
            }
            for k in keys
        ]
        return Response({"results": results})

    def post(self, request: Request) -> Response:
        name = request.data.get("name")
        if not name:
            return Response(
                {"detail": "name is required", "code": "validation_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        org = request.user.organization if not request.user.is_superuser else None
        if request.user.is_superuser:
            org_id = request.data.get("organizationId")
            if org_id:
                try:
                    org = Organization.objects.get(pk=org_id)
                except Organization.DoesNotExist:
                    return Response(
                        {"detail": "Organization not found"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                return Response(
                    {"detail": "organizationId required for superuser"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        from django.utils.dateparse import parse_datetime

        expires_at = None
        if request.data.get("expiresAt"):
            expires_at = parse_datetime(request.data["expiresAt"])

        key_obj, raw_key = APIKey.generate(
            organization=org,
            name=name,
            created_by=request.user,
            expires_at=expires_at,
        )
        return Response(
            {
                "id": str(key_obj.pk),
                "name": key_obj.name,
                "prefix": key_obj.key_prefix,
                "key": raw_key,  # Only returned once at creation
            },
            status=status.HTTP_201_CREATED,
        )


class APIKeyDetailView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def delete(self, request: Request, key_id: str) -> Response:
        try:
            key_obj = org_filter_queryset(APIKey.objects.all(), request.user).get(pk=key_id)
        except APIKey.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        key_obj.is_active = False
        key_obj.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class APIKeyRotateView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request: Request, key_id: str) -> Response:
        try:
            old_key = org_filter_queryset(APIKey.objects.all(), request.user).get(pk=key_id)
        except APIKey.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        # Revoke old key
        old_key.is_active = False
        old_key.save(update_fields=["is_active"])

        # Create new key with same config
        new_key, raw_key = APIKey.generate(
            organization=old_key.organization,
            name=old_key.name,
            created_by=request.user,
            expires_at=old_key.expires_at,
            scopes=old_key.scopes,
        )
        return Response(
            {
                "id": str(new_key.pk),
                "name": new_key.name,
                "prefix": new_key.key_prefix,
                "key": raw_key,
            }
        )


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
