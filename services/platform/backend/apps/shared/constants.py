"""
Shared constants and enums for the SequoIA platform.
"""

# Realtime simulation and Kafka bridge
MAP_REFRESH_INTERVAL = 300  # 5 minutes
INFRA_REFRESH_INTERVAL = 300  # 5 minutes
FIBER_REFRESH_INTERVAL = 600  # 10 minutes

# Infrastructure types
INFRASTRUCTURE_TYPES = [
    ("bridge", "Bridge"),
    ("tunnel", "Tunnel"),
]


# User roles
USER_ROLES = [
    ("admin", "Administrator"),
    ("operator", "Operator"),
    ("viewer", "Viewer"),
]

# Default widget and layer sets
ALL_WIDGETS = ["map", "traffic_monitor", "incidents", "shm", "admin"]
ALL_LAYERS = [
    "cables",
    "fibers",
    "vehicles",
    "heatmap",
    "landmarks",
    "sections",
    "detections",
    "incidents",
    "infrastructure",
]

VIEWER_WIDGETS = ["map", "incidents", "shm"]
VIEWER_LAYERS = ["cables", "fibers", "landmarks", "incidents", "infrastructure"]

# ClickHouse table names (shared across monitoring + realtime)
CH_INCIDENTS = "fiber_incidents"
CH_FIBER_CABLES = "fiber_cables"

# Simulation snapshot parameters
SNAPSHOT_CHANNEL_RADIUS = 30  # ±30 channels (~300m) around incident center
SNAPSHOT_WINDOW_S = 60  # Record ±60s around incident detected_at

# Business limits
# Keep in sync with frontend: services/platform/frontend/src/api/sections.ts
MAX_SECTIONS_PER_ORG = 50
