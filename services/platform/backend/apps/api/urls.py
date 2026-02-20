"""
API URL configuration — aggregates all app endpoints under /api/.
"""

from django.conf import settings
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.shared import views as shared_views
from apps.accounts import views as auth_views
from apps.fibers import views as fiber_views
from apps.monitoring import views as monitoring_views
from apps.preferences import views as pref_views
from apps.reporting import views as reporting_views

urlpatterns = [
    # Health checks
    path('health', shared_views.HealthCheckView.as_view(), name='health'),
    path('health/ready', shared_views.ReadinessCheckView.as_view(), name='readiness'),

    # Auth endpoints
    path('auth/login', auth_views.LoginView.as_view(), name='login'),
    path('auth/verify', auth_views.VerifyView.as_view(), name='verify'),
    path('auth/refresh', auth_views.CookieTokenRefreshView.as_view(), name='token-refresh'),
    path('auth/logout', auth_views.LogoutView.as_view(), name='logout'),

    # Data endpoints
    path('fibers', fiber_views.FiberListView.as_view(), name='fibers'),
    path('incidents', monitoring_views.IncidentListView.as_view(), name='incidents'),
    path('incidents/<str:incident_id>/snapshot', monitoring_views.IncidentSnapshotView.as_view(), name='incident-snapshot'),
    path('infrastructure', monitoring_views.InfrastructureListView.as_view(), name='infrastructure'),
    path('stats', monitoring_views.StatsView.as_view(), name='stats'),
    path('user/preferences', pref_views.UserPreferencesView.as_view(), name='user-preferences'),

    # SHM Spectral data
    path('shm/spectra', monitoring_views.SpectralDataView.as_view(), name='shm-spectra'),
    path('shm/peaks', monitoring_views.SpectralPeaksView.as_view(), name='shm-peaks'),
    path('shm/summary', monitoring_views.SpectralSummaryView.as_view(), name='shm-summary'),

    # Reports
    path('reports', reporting_views.ReportListView.as_view(), name='reports'),
    path('reports/generate', reporting_views.ReportGenerateView.as_view(), name='report-generate'),
    path('reports/<uuid:report_id>', reporting_views.ReportDetailView.as_view(), name='report-detail'),
    path('reports/<uuid:report_id>/send', reporting_views.ReportSendView.as_view(), name='report-send'),

]

# OpenAPI schema + Swagger UI only in development
if settings.DEBUG:
    urlpatterns += [
        path('schema', SpectacularAPIView.as_view(), name='schema'),
        path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    ]
