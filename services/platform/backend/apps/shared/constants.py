"""
Shared constants and enums for the SequoIA platform.
"""

# Realtime simulation and Kafka bridge
MAP_REFRESH_INTERVAL = 300  # 5 minutes

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
