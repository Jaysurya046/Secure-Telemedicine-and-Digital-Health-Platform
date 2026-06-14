"""Celery tasks for consultations."""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

from .models import Consultation


@shared_task
def close_stale_consultations():
    """Close consultations left in progress for more than six hours."""
    cutoff = timezone.now() - timedelta(hours=6)
    updated = Consultation.objects.filter(
        status='in_progress',
        started_at__lt=cutoff,
    ).update(status='completed', ended_at=timezone.now())
    return f'Closed {updated} stale consultations'
