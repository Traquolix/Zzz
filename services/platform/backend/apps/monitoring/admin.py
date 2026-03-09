from django.contrib import admin

from apps.monitoring.models import Infrastructure, Section


@admin.register(Infrastructure)
class InfrastructureAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "type", "fiber_id", "organization")
    list_filter = ("type", "organization")
    search_fields = ("name", "fiber_id")


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "fiber_id",
        "direction",
        "channel_start",
        "channel_end",
        "organization",
    )
    list_filter = ("fiber_id", "organization", "is_active")
    search_fields = ("name", "fiber_id")
