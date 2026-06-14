"""Serializers for audit logs."""
from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'user', 'user_email', 'action', 'resource_type',
            'resource_id', 'path', 'method', 'status_code', 'ip_address',
            'user_agent', 'metadata', 'created_at',
        ]
        read_only_fields = fields
