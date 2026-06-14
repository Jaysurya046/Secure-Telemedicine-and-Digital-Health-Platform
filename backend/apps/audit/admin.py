"""Admin for audit logs."""
from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'user', 'action', 'resource_type', 'method', 'status_code', 'ip_address']
    list_filter = ['action', 'resource_type', 'method', 'status_code', 'created_at']
    search_fields = ['user__email', 'path', 'resource_type', 'resource_id']
    readonly_fields = [
        'id', 'user', 'action', 'resource_type', 'resource_id', 'path',
        'method', 'status_code', 'ip_address', 'user_agent', 'metadata',
        'created_at',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
