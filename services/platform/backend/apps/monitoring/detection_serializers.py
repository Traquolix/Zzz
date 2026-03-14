"""
Serializers for the public detection API (v1).

Separate from internal serializers to keep public API contracts independent.
"""

from rest_framework import serializers


class HiresDetectionSerializer(serializers.Serializer):
    """A single high-resolution detection record."""

    timestamp = serializers.DateTimeField(help_text="Detection timestamp (UTC)")
    fiber_id = serializers.CharField(help_text="Fiber identifier")
    channel = serializers.IntegerField(help_text="Channel number along the fiber")
    direction = serializers.IntegerField(help_text="Traffic direction (0 or 1)")
    speed = serializers.FloatField(help_text="Vehicle speed in km/h")
    vehicle_count = serializers.IntegerField(help_text="Number of vehicles detected")
    n_cars = serializers.IntegerField(help_text="Number of cars")
    n_trucks = serializers.IntegerField(help_text="Number of trucks")
    latitude = serializers.FloatField(help_text="Latitude coordinate", allow_null=True)
    longitude = serializers.FloatField(help_text="Longitude coordinate", allow_null=True)


class AggregateDetectionSerializer(serializers.Serializer):
    """An aggregated detection record (1-minute or 1-hour resolution)."""

    timestamp = serializers.DateTimeField(help_text="Aggregation period start (UTC)")
    fiber_id = serializers.CharField(help_text="Fiber identifier")
    channel = serializers.IntegerField(help_text="Channel number along the fiber")
    direction = serializers.IntegerField(help_text="Traffic direction (0 or 1)")
    speed_avg = serializers.FloatField(help_text="Average speed in km/h")
    speed_min = serializers.FloatField(help_text="Minimum speed in km/h")
    speed_max = serializers.FloatField(help_text="Maximum speed in km/h")
    vehicle_count = serializers.IntegerField(help_text="Total vehicles in period")
    n_cars = serializers.IntegerField(help_text="Total cars in period")
    n_trucks = serializers.IntegerField(help_text="Total trucks in period")
    sample_count = serializers.IntegerField(help_text="Number of raw samples aggregated")


class DetectionResponseMetaSerializer(serializers.Serializer):
    """Metadata for a paginated detection response."""

    tier = serializers.CharField(help_text="Data tier used: 'hires', '1m', or '1h'")
    start = serializers.DateTimeField(help_text="Query start time")
    end = serializers.DateTimeField(help_text="Query end time")
    fiber_id = serializers.CharField(help_text="Queried fiber ID")
    count = serializers.IntegerField(help_text="Number of records in this page")
    has_more = serializers.BooleanField(help_text="Whether more pages are available")
    next_cursor = serializers.CharField(
        help_text="Cursor for the next page (null if no more data)",
        allow_null=True,
    )


class DetectionListResponseSerializer(serializers.Serializer):
    """Top-level response for the detection list endpoint."""

    data = HiresDetectionSerializer(many=True, help_text="Detection records")
    meta = DetectionResponseMetaSerializer(help_text="Pagination and query metadata")


class DetectionSummarySerializer(serializers.Serializer):
    """Aggregated summary statistics for a fiber + time range."""

    fiber_id = serializers.CharField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    tier = serializers.CharField()
    total_vehicles = serializers.IntegerField()
    total_cars = serializers.IntegerField()
    total_trucks = serializers.IntegerField()
    avg_speed = serializers.FloatField(allow_null=True)
    min_speed = serializers.FloatField(allow_null=True)
    max_speed = serializers.FloatField(allow_null=True)
    channel_count = serializers.IntegerField(help_text="Distinct channels with detections")
    record_count = serializers.IntegerField(help_text="Total detection records in range")


class DataAvailabilitySerializer(serializers.Serializer):
    """Time range of available data for a fiber."""

    earliest = serializers.DateTimeField(allow_null=True, help_text="Earliest detection timestamp")
    latest = serializers.DateTimeField(allow_null=True, help_text="Latest detection timestamp")
    hires_since = serializers.DateTimeField(
        allow_null=True, help_text="Hires data available since (NOW - 48h)"
    )


class FiberAvailabilitySerializer(serializers.Serializer):
    """Fiber metadata with data availability for the public API."""

    fiber_id = serializers.CharField()
    name = serializers.CharField()
    directions = serializers.ListField(child=serializers.IntegerField())
    channel_range = serializers.ListField(child=serializers.IntegerField())
    data_available = DataAvailabilitySerializer()


class PublicFiberListResponseSerializer(serializers.Serializer):
    """Top-level response for the public fiber list endpoint."""

    data = FiberAvailabilitySerializer(many=True)


# ── Incident serializers ─────────────────────────────────────────────


class IncidentSerializer(serializers.Serializer):
    """Public API incident record from ClickHouse."""

    incidentId = serializers.CharField(help_text="Unique incident identifier")
    fiberId = serializers.CharField(help_text="Fiber cable ID")
    type = serializers.CharField(help_text="Incident type (slowdown, congestion, etc.)")
    severity = serializers.CharField(help_text="Severity level (low, medium, high, critical)")
    status = serializers.CharField(help_text="Current status (active, resolved, etc.)")
    detectedAt = serializers.DateTimeField(help_text="When the incident was detected (UTC)")
    channelStart = serializers.IntegerField(help_text="First affected channel")
    channelEnd = serializers.IntegerField(help_text="Last affected channel")
    speedKmh = serializers.FloatField(help_text="Speed at detection time (km/h)", allow_null=True)
    durationS = serializers.FloatField(help_text="Duration in seconds", allow_null=True)


class IncidentDetailResponseSerializer(serializers.Serializer):
    """Top-level response for a single incident."""

    data = IncidentSerializer()


class IncidentListMetaSerializer(serializers.Serializer):
    """Metadata for paginated incident list."""

    count = serializers.IntegerField()
    has_more = serializers.BooleanField()
    next_cursor = serializers.CharField(allow_null=True)


class IncidentListResponseSerializer(serializers.Serializer):
    """Top-level response for incident list."""

    data = IncidentSerializer(many=True)
    meta = IncidentListMetaSerializer()


# ── Section serializers ──────────────────────────────────────────────


class SectionSerializer(serializers.Serializer):
    """Public API section record from PostgreSQL."""

    id = serializers.CharField(help_text="Section identifier")
    fiberId = serializers.CharField(help_text="Fiber cable ID")
    direction = serializers.IntegerField(help_text="Traffic direction (0 or 1)")
    name = serializers.CharField(help_text="Section display name")
    channelStart = serializers.IntegerField(help_text="First channel in section")
    channelEnd = serializers.IntegerField(help_text="Last channel in section")
    isActive = serializers.BooleanField(help_text="Whether the section is active")


class SectionListResponseSerializer(serializers.Serializer):
    """Top-level response for section list."""

    data = SectionSerializer(many=True)


class SectionHistoryPointSerializer(serializers.Serializer):
    """Single point in a section history time series."""

    timestamp = serializers.CharField(help_text="Timestamp (ISO 8601 or epoch ms)")
    speed = serializers.FloatField(help_text="Average speed (km/h)", allow_null=True)
    flow = serializers.FloatField(help_text="Vehicle flow (veh/min)", allow_null=True)
    occupancy = serializers.FloatField(help_text="Channel occupancy ratio", allow_null=True)


class SectionHistoryMetaSerializer(serializers.Serializer):
    """Metadata for section history response."""

    section_id = serializers.CharField(help_text="Section identifier")
    tier = serializers.CharField(help_text="Data tier used: 'hires', '1m', or '1h'")


class SectionHistoryResponseSerializer(serializers.Serializer):
    """Top-level response for section history."""

    data = SectionHistoryPointSerializer(many=True)
    meta = SectionHistoryMetaSerializer(help_text="Query metadata")


# ── Stats serializer ─────────────────────────────────────────────────


class PublicStatsSerializer(serializers.Serializer):
    """System-level stats for the org."""

    fiberCount = serializers.IntegerField(help_text="Number of fibers assigned to org")
    totalChannels = serializers.IntegerField(help_text="Total DAS channels across fibers")
    activeIncidents = serializers.IntegerField(help_text="Currently active incidents")
    detectionsPerSecond = serializers.FloatField(help_text="Current detection throughput")


class PublicStatsResponseSerializer(serializers.Serializer):
    """Top-level response for stats."""

    data = PublicStatsSerializer()


# ── Infrastructure serializers ───────────────────────────────────────


class InfrastructureSerializer(serializers.Serializer):
    """Public API infrastructure record."""

    id = serializers.CharField(help_text="Infrastructure identifier (slug)")
    type = serializers.CharField(help_text="Type (bridge, tunnel, etc.)")
    name = serializers.CharField(help_text="Display name")
    fiberId = serializers.CharField(help_text="Fiber cable ID")
    direction = serializers.IntegerField(
        help_text="Direction (0, 1, or null for both)", allow_null=True
    )
    startChannel = serializers.IntegerField(help_text="First channel")
    endChannel = serializers.IntegerField(help_text="Last channel")


class InfrastructureListResponseSerializer(serializers.Serializer):
    """Top-level response for infrastructure list."""

    data = InfrastructureSerializer(many=True)


class InfrastructureStatusSerializer(serializers.Serializer):
    """SHM status for an infrastructure item."""

    status = serializers.CharField(help_text="Overall status (nominal, warning, critical)")
    currentMean = serializers.FloatField(help_text="Current mean frequency (Hz)")
    baselineMean = serializers.FloatField(help_text="Baseline mean frequency (Hz)")
    deviationSigma = serializers.FloatField(help_text="Deviation in sigma units")
    direction = serializers.CharField(help_text="Shift direction", allow_null=True)
    severity = serializers.CharField(help_text="Raw severity classification")
