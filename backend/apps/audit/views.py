"""Views for audit logs."""
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.users.permissions import IsAdmin
from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    queryset = AuditLog.objects.select_related('user').all()
    filterset_fields = ['user', 'action', 'resource_type', 'method', 'status_code']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    search_fields = ['path', 'user__email', 'resource_type', 'resource_id']
