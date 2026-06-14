"""Celery tasks for medical records."""
from celery import shared_task
from django.utils import timezone

from .models import Prescription


@shared_task
def expire_old_prescriptions():
    """Mark active prescriptions as expired after their validity date."""
    today = timezone.localdate()
    updated = Prescription.objects.filter(
        status='active',
        valid_until__isnull=False,
        valid_until__lt=today,
    ).update(status='expired')
    return f'Expired {updated} prescriptions'
