from django.contrib import admin
from apps.monitoring.models import Infrastructure


@admin.register(Infrastructure)
class InfrastructureAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'type', 'fiber_id', 'organization')
    list_filter = ('type', 'organization')
    search_fields = ('name', 'fiber_id')
