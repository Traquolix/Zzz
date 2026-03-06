from django.contrib import admin

from apps.reporting.models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "status", "created_by", "created_at")
    list_filter = ("status", "organization", "created_at")
    search_fields = ("title",)
    readonly_fields = ("id", "created_at", "sent_at")
