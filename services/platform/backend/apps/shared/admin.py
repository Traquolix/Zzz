from django.contrib import admin
from apps.shared.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'user', 'organization', 'object_type', 'created_at')
    list_filter = ('action', 'organization')
    search_fields = ('user__username', 'object_type', 'object_id')
    readonly_fields = (
        'id', 'organization', 'user', 'action', 'object_type',
        'object_id', 'changes', 'ip_address', 'created_at',
    )
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
