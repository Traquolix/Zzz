"""
API URL configuration — aggregates all app endpoints under /api/.
"""

from django.conf import settings
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.accounts import views as auth_views
from apps.admin_api import views as admin_views
from apps.fibers import views as fiber_views
from apps.monitoring import export_views
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
        "sections/<path:section_id>/history",
        monitoring_views.SectionHistoryView.as_view(),
        name="section-history",
    ),
    path(
        "sections/<path:section_id>",
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

# OpenAPI schema + Swagger UI only in development
if settings.DEBUG:
    urlpatterns += [
        path("schema", SpectacularAPIView.as_view(), name="schema"),
        path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    ]
