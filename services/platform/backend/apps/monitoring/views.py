"""
Re-export all views for URL routing compatibility.

The implementation has been split into focused modules:
- incident_views.py  — IncidentListView, IncidentSnapshotView, IncidentActionView
- section_views.py   — SectionListView, SectionDeleteView, SectionHistoryView, BatchSectionHistoryView
- shm_views.py       — SpectralDataView, SpectralPeaksView, SpectralSummaryView, SHMStatusView
- stats_views.py     — StatsView, InfrastructureListView
- view_helpers.py    — shared helpers (_PROCESS_START_TIME, cache TTLs, _get_fiber_ids_or_none, _verify_infrastructure_access)
"""

from apps.monitoring.incident_views import *  # noqa: F403
from apps.monitoring.section_views import *  # noqa: F403
from apps.monitoring.shm_views import *  # noqa: F403
from apps.monitoring.stats_views import *  # noqa: F403
