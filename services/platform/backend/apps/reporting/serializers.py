from rest_framework import serializers


class ReportSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    status = serializers.CharField()
    startTime = serializers.DateTimeField(source='start_time')
    endTime = serializers.DateTimeField(source='end_time')
    fiberIds = serializers.ListField(source='fiber_ids')
    sections = serializers.ListField()
    recipients = serializers.ListField()
    sentAt = serializers.DateTimeField(source='sent_at', allow_null=True)
    createdAt = serializers.DateTimeField(source='created_at')
    createdBy = serializers.CharField(source='created_by.username', allow_null=True)


class GenerateReportSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    startTime = serializers.DateTimeField()
    endTime = serializers.DateTimeField()
    fiberIds = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    sections = serializers.ListField(
        child=serializers.ChoiceField(choices=['incidents', 'speed', 'volume']),
        allow_empty=False,
    )
    recipients = serializers.ListField(child=serializers.EmailField(), default=list)

    def validate(self, attrs):
        if attrs['endTime'] <= attrs['startTime']:
            raise serializers.ValidationError({
                'endTime': 'End time must be after start time.'
            })
        return attrs


class SendReportSerializer(serializers.Serializer):
    recipients = serializers.ListField(
        child=serializers.EmailField(),
        allow_empty=False,
        help_text='Override recipients. If empty, uses the report\'s saved recipients.',
    )
