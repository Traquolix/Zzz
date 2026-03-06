from django.contrib import admin

from apps.fibers.models import FiberAssignment


class FiberAssignmentInline(admin.TabularInline):
    model = FiberAssignment
    extra = 1
    readonly_fields = ("assigned_at",)


@admin.register(FiberAssignment)
class FiberAssignmentAdmin(admin.ModelAdmin):
    list_display = ("fiber_id", "organization", "assigned_at")
    list_filter = ("organization",)
    search_fields = ("fiber_id", "organization__name")
