"""Celery tasks for audit logs."""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

from .models import AuditLog


@shared_task
def summarize_recent_audit_activity(days=1):
    """Return a lightweight audit summary for monitoring jobs."""
    since = timezone.now() - timedelta(days=days)
    logs = AuditLog.objects.filter(created_at__gte=since)
    return {
        'since': since.isoformat(),
        'total_events': logs.count(),
        'failed_events': logs.filter(status_code__gte=400).count(),
    }
