"""
Response serializers for monitoring endpoints.

Read-only serializers for ClickHouse data (incidents, stats)
and PostgreSQL data (infrastructure).
"""

from rest_framework import serializers


class IncidentSerializer(serializers.Serializer):
    id = serializers.CharField()
    type = serializers.CharField()
    severity = serializers.CharField()
    fiberLine = serializers.CharField()
    channel = serializers.IntegerField()
    detectedAt = serializers.CharField()
    status = serializers.CharField()
    duration = serializers.IntegerField(allow_null=True)


class DetectionSerializer(serializers.Serializer):
    fiberLine = serializers.CharField()
    channel = serializers.IntegerField()
    speed = serializers.FloatField()
    count = serializers.IntegerField()
    direction = serializers.IntegerField()
    timestamp = serializers.IntegerField()


class IncidentSnapshotSerializer(serializers.Serializer):
    incidentId = serializers.CharField()
    fiberLine = serializers.CharField()
    centerChannel = serializers.IntegerField()
    capturedAt = serializers.IntegerField()
    detections = DetectionSerializer(many=True)


class InfrastructureSerializer(serializers.Serializer):
    id = serializers.CharField()
    type = serializers.CharField()
    name = serializers.CharField()
    fiberId = serializers.CharField()
    startChannel = serializers.IntegerField()
    endChannel = serializers.IntegerField()
    imageUrl = serializers.SerializerMethodField()

    def get_imageUrl(self, obj):
        """Return URL for infrastructure image, or None if not set."""
        if not obj.image:
            return None
        return f'/infrastructure/{obj.image}'


class StatsSerializer(serializers.Serializer):
    fiberCount = serializers.IntegerField()
    totalChannels = serializers.IntegerField()
    activeVehicles = serializers.IntegerField()
    detectionsPerSecond = serializers.FloatField()
    activeIncidents = serializers.IntegerField()
    systemUptime = serializers.IntegerField()


class IncidentActionSerializer(serializers.Serializer):
    """Serializes a single workflow action for display."""
    id = serializers.UUIDField(read_only=True)
    fromStatus = serializers.CharField(source='from_status')
    toStatus = serializers.CharField(source='to_status')
    performedBy = serializers.CharField(source='performed_by.username', default=None)
    note = serializers.CharField()
    performedAt = serializers.DateTimeField(source='performed_at')


class IncidentActionInputSerializer(serializers.Serializer):
    """Validates incoming workflow action requests."""
    action = serializers.ChoiceField(
        choices=['acknowledged', 'investigating', 'resolved'],
    )
    note = serializers.CharField(required=False, default='', allow_blank=True)


class SectionInputSerializer(serializers.Serializer):
    """Validates incoming section creation requests."""
    fiberId = serializers.CharField()
    name = serializers.CharField()
    channelStart = serializers.IntegerField()
    channelEnd = serializers.IntegerField()


class SectionSerializer(serializers.Serializer):
    """Response serializer for a monitored section."""
    id = serializers.CharField()
    fiberId = serializers.CharField()
    name = serializers.CharField()
    channelStart = serializers.IntegerField()
    channelEnd = serializers.IntegerField()
    expectedTravelTime = serializers.FloatField(allow_null=True)
    isActive = serializers.BooleanField()
    createdAt = serializers.CharField()


class SectionHistoryPointSerializer(serializers.Serializer):
    """A single point in a section speed time-series."""
    time = serializers.IntegerField()
    speed = serializers.FloatField()
    speedMax = serializers.FloatField()
    samples = serializers.IntegerField()


class SectionHistorySerializer(serializers.Serializer):
    """Response serializer for section history endpoint."""
    sectionId = serializers.CharField()
    minutes = serializers.IntegerField()
    points = SectionHistoryPointSerializer(many=True)


class SpectralDataSerializer(serializers.Serializer):
    """Response serializer for spectral heatmap data."""
    t0 = serializers.CharField()
    dt = serializers.ListField(child=serializers.FloatField())
    frequencies = serializers.ListField(child=serializers.FloatField())
    power = serializers.ListField()
    freqRange = serializers.ListField(child=serializers.FloatField())


class SpectralPeaksSerializer(serializers.Serializer):
    """Response serializer for spectral peak frequencies."""
    t0 = serializers.CharField()
    dt = serializers.ListField(child=serializers.FloatField())
    peakFrequencies = serializers.ListField(child=serializers.FloatField())
    peakPowers = serializers.ListField(child=serializers.FloatField())
    freqRange = serializers.ListField(child=serializers.FloatField())
