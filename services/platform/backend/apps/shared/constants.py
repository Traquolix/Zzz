"""
Shared constants and enums for the SequoIA platform.
"""

# Infrastructure types
INFRASTRUCTURE_TYPES = [
    ('bridge', 'Bridge'),
    ('tunnel', 'Tunnel'),
]

# User roles
USER_ROLES = [
    ('admin', 'Administrator'),
    ('operator', 'Operator'),
    ('viewer', 'Viewer'),
]

# Default widget and layer sets
ALL_WIDGETS = ['map', 'traffic_monitor', 'incidents', 'shm']
ALL_LAYERS = [
    'cables', 'fibers', 'vehicles', 'heatmap', 'landmarks',
    'sections', 'detections', 'incidents', 'infrastructure',
]

VIEWER_WIDGETS = ['map', 'incidents', 'shm']
VIEWER_LAYERS = ['cables', 'fibers', 'landmarks', 'incidents', 'infrastructure']
