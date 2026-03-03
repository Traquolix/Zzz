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
    organizationId = serializers.UUIDField(required=False, allow_null=True, default=None)

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


class ReportScheduleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    frequency = serializers.CharField()
    fiberIds = serializers.ListField(source='fiber_ids')
    sections = serializers.ListField()
    recipients = serializers.ListField()
    isActive = serializers.BooleanField(source='is_active')
    lastRunAt = serializers.DateTimeField(source='last_run_at', allow_null=True)
    createdAt = serializers.DateTimeField(source='created_at')


class CreateScheduleSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    frequency = serializers.ChoiceField(choices=['daily', 'weekly', 'monthly'])
    fiberIds = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    sections = serializers.ListField(
        child=serializers.ChoiceField(choices=['incidents', 'speed', 'volume']),
        allow_empty=False,
    )
    recipients = serializers.ListField(child=serializers.EmailField(), default=list)

    def validate(self, attrs):
        if not attrs.get('title'):
            # Generate a default title if not provided
            frequency = attrs['frequency'].capitalize()
            attrs['title'] = f'{frequency} Traffic Report'
        return attrs
