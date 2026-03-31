"""
Public detection API (v1) — versioned REST endpoints for external consumers.

Split into focused modules by resource type. This __init__.py re-exports
all view classes so that ``from apps.monitoring import detection_api``
followed by ``detection_api.DetectionListView`` continues to work.
"""

from .detections import DetectionListView, DetectionSummaryView
from .fibers import PublicFiberListView
from .incidents import IncidentDetailAPIView, IncidentListAPIView
from .infrastructure import InfrastructureListAPIView, InfrastructureStatusAPIView
from .sections import SectionHistoryAPIView, SectionListAPIView
from .stats import StatsAPIView

__all__ = [
    "DetectionListView",
    "DetectionSummaryView",
    "IncidentDetailAPIView",
    "IncidentListAPIView",
    "InfrastructureListAPIView",
    "InfrastructureStatusAPIView",
    "PublicFiberListView",
    "SectionHistoryAPIView",
    "SectionListAPIView",
    "StatsAPIView",
]
