from django.contrib import admin

from apps.fibers.admin import FiberAssignmentInline
from apps.organizations.models import Organization, OrganizationSettings


class OrganizationSettingsInline(admin.StackedInline):
    model = OrganizationSettings
    can_delete = False


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [OrganizationSettingsInline, FiberAssignmentInline]
