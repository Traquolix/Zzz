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
        """Return full URL for infrastructure image, or None if not set."""
        if not obj.image:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(f'/media/infrastructure/{obj.image}')
        return f'/media/infrastructure/{obj.image}'


class StatsSerializer(serializers.Serializer):
    fiberCount = serializers.IntegerField()
    totalChannels = serializers.IntegerField()
    activeVehicles = serializers.IntegerField()
    detectionsPerSecond = serializers.FloatField()
    activeIncidents = serializers.IntegerField()
    systemUptime = serializers.IntegerField()
