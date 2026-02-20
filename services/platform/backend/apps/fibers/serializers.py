"""
Response serializers for fiber endpoints.

Read-only serializers for ClickHouse fiber_cables data.
"""

from rest_framework import serializers


class LandmarkSerializer(serializers.Serializer):
    channel = serializers.IntegerField()
    name = serializers.CharField()


class FiberLineSerializer(serializers.Serializer):
    id = serializers.CharField()
    parentFiberId = serializers.CharField()
    direction = serializers.IntegerField()
    name = serializers.CharField()
    color = serializers.CharField()
    coordinates = serializers.ListField()
    coordsPrecomputed = serializers.BooleanField(default=False)
    landmarks = LandmarkSerializer(many=True, allow_null=True)
