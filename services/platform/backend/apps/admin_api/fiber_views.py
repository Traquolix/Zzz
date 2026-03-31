"""
Admin API views — Fiber Assignment CRUD.

Permission model:
- Fiber assignment management: superuser only
"""

import logging

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.models import FiberAssignment
from apps.fibers.utils import invalidate_fiber_org_map, invalidate_org_fiber_cache
from apps.organizations.models import Organization
from apps.shared.admin_permissions import IsSuperuser

logger = logging.getLogger("sequoia.admin_api.fiber_views")


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
