"""
API URL configuration — aggregates all app endpoints under /api/.
"""

from django.conf import settings
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

from apps.accounts import views as auth_views
from apps.admin_api import views as admin_views
from apps.fibers import views as fiber_views
from apps.monitoring import detection_api, export_views
from apps.monitoring import views as monitoring_views
from apps.preferences import views as pref_views
from apps.reporting import views as reporting_views
from apps.shared import views as shared_views

urlpatterns = [
    # Health checks & metrics
    path("health", shared_views.HealthCheckView.as_view(), name="health"),
    path("health/ready", shared_views.ReadinessCheckView.as_view(), name="readiness"),
    path("metrics", shared_views.MetricsView.as_view(), name="metrics"),
    # Auth endpoints
    path("auth/login", auth_views.LoginView.as_view(), name="login"),
    path("auth/verify", auth_views.VerifyView.as_view(), name="verify"),
    path("auth/refresh", auth_views.CookieTokenRefreshView.as_view(), name="token-refresh"),
    path("auth/logout", auth_views.LogoutView.as_view(), name="logout"),
    # Data endpoints
    path("fibers", fiber_views.FiberListView.as_view(), name="fibers"),
    path("incidents", monitoring_views.IncidentListView.as_view(), name="incidents"),
    path(
        "incidents/<str:incident_id>/snapshot",
        monitoring_views.IncidentSnapshotView.as_view(),
        name="incident-snapshot",
    ),
    path(
        "incidents/<str:incident_id>/actions",
        monitoring_views.IncidentActionView.as_view(),
        name="incident-actions",
    ),
    path(
        "infrastructure", monitoring_views.InfrastructureListView.as_view(), name="infrastructure"
    ),
    path("sections", monitoring_views.SectionListView.as_view(), name="sections"),
    path(
        "sections/batch-history",
        monitoring_views.BatchSectionHistoryView.as_view(),
        name="section-batch-history",
    ),
    path(
        "sections/<str:section_id>/history",
        monitoring_views.SectionHistoryView.as_view(),
        name="section-history",
    ),
    path(
        "sections/<str:section_id>",
        monitoring_views.SectionDeleteView.as_view(),
        name="section-delete",
    ),
    path("stats", monitoring_views.StatsView.as_view(), name="stats"),
    path("user/preferences", pref_views.UserPreferencesView.as_view(), name="user-preferences"),
    # SHM Spectral data
    path("shm/spectra", monitoring_views.SpectralDataView.as_view(), name="shm-spectra"),
    path("shm/peaks", monitoring_views.SpectralPeaksView.as_view(), name="shm-peaks"),
    path("shm/summary", monitoring_views.SpectralSummaryView.as_view(), name="shm-summary"),
    path(
        "monitoring/shm/status/<str:infrastructure_id>",
        monitoring_views.SHMStatusView.as_view(),
        name="shm-status",
    ),
    # Reports
    path("reports", reporting_views.ReportListView.as_view(), name="reports"),
    path("reports/generate", reporting_views.ReportGenerateView.as_view(), name="report-generate"),
    path(
        "reports/<uuid:report_id>", reporting_views.ReportDetailView.as_view(), name="report-detail"
    ),
    path(
        "reports/<uuid:report_id>/send",
        reporting_views.ReportSendView.as_view(),
        name="report-send",
    ),
    path(
        "reports/schedules",
        reporting_views.ReportScheduleListView.as_view(),
        name="report-schedules",
    ),
    path(
        "reports/schedules/<uuid:schedule_id>",
        reporting_views.ReportScheduleDetailView.as_view(),
        name="report-schedule-detail",
    ),
    # Export endpoints
    path("export/incidents", export_views.ExportIncidentsView.as_view(), name="export-incidents"),
    path(
        "export/detections", export_views.ExportDetectionsView.as_view(), name="export-detections"
    ),
    # Export estimate
    path("export/estimate", export_views.ExportEstimateView.as_view(), name="export-estimate"),
    # Public API v1
    path(
        "v1/detections",
        detection_api.DetectionListView.as_view(),
        name="public-detections",
    ),
    path(
        "v1/detections/summary",
        detection_api.DetectionSummaryView.as_view(),
        name="public-detections-summary",
    ),
    path(
        "v1/fibers",
        detection_api.PublicFiberListView.as_view(),
        name="public-fibers",
    ),
    path(
        "v1/incidents",
        detection_api.IncidentListAPIView.as_view(),
        name="public-incidents",
    ),
    path(
        "v1/incidents/<str:incident_id>",
        detection_api.IncidentDetailAPIView.as_view(),
        name="public-incident-detail",
    ),
    path(
        "v1/sections",
        detection_api.SectionListAPIView.as_view(),
        name="public-sections",
    ),
    path(
        "v1/sections/<str:section_id>/history",
        detection_api.SectionHistoryAPIView.as_view(),
        name="public-section-history",
    ),
    path(
        "v1/stats",
        detection_api.StatsAPIView.as_view(),
        name="public-stats",
    ),
    path(
        "v1/infrastructure",
        detection_api.InfrastructureListAPIView.as_view(),
        name="public-infrastructure",
    ),
    path(
        "v1/infrastructure/<str:infra_id>/status",
        detection_api.InfrastructureStatusAPIView.as_view(),
        name="public-infrastructure-status",
    ),
    # Admin endpoints
    path(
        "admin/organizations",
        admin_views.OrganizationListView.as_view(),
        name="admin-organizations",
    ),
    path(
        "admin/organizations/<uuid:org_id>",
        admin_views.OrganizationDetailView.as_view(),
        name="admin-organization-detail",
    ),
    path(
        "admin/organizations/<uuid:org_id>/settings",
        admin_views.OrgSettingsView.as_view(),
        name="admin-org-settings",
    ),
    path(
        "admin/organizations/<uuid:org_id>/fibers",
        admin_views.FiberAssignmentListView.as_view(),
        name="admin-fiber-assignments",
    ),
    path(
        "admin/organizations/<uuid:org_id>/fibers/<uuid:assignment_id>",
        admin_views.FiberAssignmentDetailView.as_view(),
        name="admin-fiber-assignment-detail",
    ),
    path("admin/users", admin_views.UserListView.as_view(), name="admin-users"),
    path(
        "admin/users/<uuid:user_id>", admin_views.UserDetailView.as_view(), name="admin-user-detail"
    ),
    path(
        "admin/infrastructure",
        admin_views.InfrastructureAdminListView.as_view(),
        name="admin-infrastructure",
    ),
    path(
        "admin/infrastructure/<str:infra_id>",
        admin_views.InfrastructureAdminDetailView.as_view(),
        name="admin-infrastructure-detail",
    ),
    path("admin/alert-rules", admin_views.AlertRuleListView.as_view(), name="admin-alert-rules"),
    path(
        "admin/alert-rules/<uuid:rule_id>",
        admin_views.AlertRuleDetailView.as_view(),
        name="admin-alert-rule-detail",
    ),
    path(
        "admin/alert-rules/<uuid:rule_id>/test",
        admin_views.AlertRuleTestView.as_view(),
        name="admin-alert-rule-test",
    ),
    path("admin/alert-logs", admin_views.AlertLogListView.as_view(), name="admin-alert-logs"),
    path("admin/api-keys", admin_views.APIKeyListView.as_view(), name="admin-api-keys"),
    path(
        "admin/api-keys/<uuid:key_id>",
        admin_views.APIKeyDetailView.as_view(),
        name="admin-api-key-detail",
    ),
    path(
        "admin/api-keys/<uuid:key_id>/rotate",
        admin_views.APIKeyRotateView.as_view(),
        name="admin-api-key-rotate",
    ),
]

# OpenAPI schema + Swagger UI — internal (DEBUG only)
if settings.DEBUG:
    urlpatterns += [
        path("schema", SpectacularAPIView.as_view(), name="schema"),
        path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    ]


def _filter_v1_endpoints(endpoints, **kwargs):
    """Preprocessing hook: keep only /api/v1/ endpoints for the public schema."""
    return [
        (path, path_regex, method, callback)
        for path, path_regex, method, callback in endpoints
        if path.startswith("/api/v1/") and "/schema" not in path and "/docs" not in path
    ]


# Public API v1 docs — always served, no auth required, only v1 endpoints
_PUBLIC_SCHEMA_SETTINGS = {
    "TITLE": "SequoIA Public API",
    "DESCRIPTION": (
        "Programmatic access to SequoIA DAS traffic detection, incident, "
        "section, and infrastructure data.\n\n"
        "## Quick Start\n\n"
        "**1. Get an API key** — create one from the SequoIA app (User Menu → API Keys).\n\n"
        "**2. Make your first request:**\n\n"
        "```bash\n"
        'curl -H "X-API-Key: sqk_YOUR_SECRET" \\\n'
        "  https://your-sequoia-instance/api/v1/fibers\n"
        "```\n\n"
        "**3. Query detection data:**\n\n"
        "```bash\n"
        'curl -H "X-API-Key: sqk_YOUR_SECRET" \\\n'
        '  "https://your-sequoia-instance/api/v1/detections?fiber_id=carros'
        '&start=2024-01-01T00:00:00Z&end=2024-01-01T01:00:00Z"\n'
        "```\n\n"
        "## Authentication\n\n"
        "All requests require an API key passed in the `X-API-Key` header:\n\n"
        "```\n"
        "X-API-Key: sqk_<your_secret>\n"
        "```\n\n"
        "## Code Examples\n\n"
        "**Python:**\n\n"
        "```python\n"
        "import requests\n\n"
        'headers = {"X-API-Key": "sqk_YOUR_SECRET"}\n'
        'resp = requests.get("https://your-instance/api/v1/fibers", headers=headers)\n'
        'fibers = resp.json()["data"]\n'
        "```\n\n"
        "**JavaScript:**\n\n"
        "```javascript\n"
        "const resp = await fetch('/api/v1/fibers', {\n"
        "  headers: { 'X-API-Key': 'sqk_YOUR_SECRET' }\n"
        "});\n"
        "const { data } = await resp.json();\n"
        "```\n\n"
        "## Rate Limits\n\n"
        "**300 requests/hour** per API key (~5 req/min sustained).\n\n"
        "When rate-limited, you'll receive a `429 Too Many Requests` response "
        "with a `Retry-After` header.\n\n"
        "## Data Tiers\n\n"
        "Detection data is stored at three resolutions:\n\n"
        "| Tier | Resolution | Retention | Auto-selected when |\n"
        "|------|-----------|-----------|-------------------|\n"
        "| `raw` | Per-detection | 48 hours | Range ≤ 48h |\n"
        "| `1m` | 1-minute aggregates | 90 days | 48h < range ≤ 90d |\n"
        "| `1h` | 1-hour aggregates | Forever | Range > 90d |\n\n"
        "Use `resolution=auto` (default) to let the API choose, or specify "
        "`raw`, `1m`, or `1h` explicitly.\n\n"
        "## Pagination\n\n"
        "Large result sets are split into pages (default 1000 rows, max 5000).\n\n"
        "Each response includes a `meta` object:\n"
        "- `has_more` — `true` if there are more rows after this page\n"
        "- `next_cursor` — an opaque token representing your position in the results\n\n"
        "To fetch the next page, pass `next_cursor` as the `cursor` query parameter:\n\n"
        "```\n"
        "GET /api/v1/detections?fiber_id=carros&start=...&end=...&cursor=<next_cursor>\n"
        "```\n\n"
        "Repeat until `has_more` is `false`. You don't need to decode the cursor — "
        "just pass it back as-is.\n\n"
        "## Error Codes\n\n"
        "| Code | Meaning |\n"
        "|------|---------|\n"
        "| `400` | Invalid parameters — check the `detail` field for specifics |\n"
        "| `401` | Missing or invalid API key |\n"
        "| `403` | API key doesn't have access to the requested resource |\n"
        "| `429` | Rate limit exceeded — wait and retry |\n"
        "| `503` | Analytics service temporarily unavailable — retry shortly |"
    ),
    "VERSION": "1.0.0",
    "PREPROCESSING_HOOKS": [
        "apps.api.urls._filter_v1_endpoints",
    ],
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "apiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "API key with sqk_ prefix (created in the admin panel)",
            },
        },
    },
    "SECURITY": [{"apiKeyAuth": []}],
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "defaultModelsExpandDepth": 2,
        "defaultModelExpandDepth": 2,
        "docExpansion": "list",
        "filter": False,
        "operationsSorter": "method",
        "tagsSorter": "alpha",
        "tryItOutEnabled": True,
    },
    "TAGS": [
        {
            "name": "Fibers",
            "description": "Discover available fibers and their data coverage.",
        },
        {
            "name": "Detections",
            "description": "Query and aggregate traffic detection data.",
        },
        {
            "name": "Incidents",
            "description": "Traffic incidents detected by the AI engine.",
        },
        {
            "name": "Sections",
            "description": "User-defined road sections with traffic metrics.",
        },
        {
            "name": "Infrastructure",
            "description": "Structural health monitoring (SHM) for bridges and tunnels.",
        },
        {
            "name": "Stats",
            "description": "System-level statistics and throughput metrics.",
        },
    ],
}

urlpatterns += [
    path(
        "v1/schema",
        SpectacularAPIView.as_view(
            authentication_classes=[],
            permission_classes=[AllowAny],
            custom_settings=_PUBLIC_SCHEMA_SETTINGS,
        ),
        name="public-schema",
    ),
    path(
        "v1/docs/",
        SpectacularSwaggerView.as_view(
            url_name="public-schema",
            template_name="public_api/swagger_ui.html",
            authentication_classes=[],
            permission_classes=[AllowAny],
        ),
        name="public-swagger-ui",
    ),
]
