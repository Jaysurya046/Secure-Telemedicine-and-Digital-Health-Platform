"""Celery tasks for appointments."""
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from .models import Appointment


@shared_task
def send_appointment_reminders():
    """Send reminders for confirmed appointments starting in the next hour."""
    window_start = timezone.now()
    window_end = window_start + timedelta(hours=1)
    appointments = Appointment.objects.select_related('patient', 'doctor').filter(
        status='confirmed',
        scheduled_start__gte=window_start,
        scheduled_start__lte=window_end,
    )
    sent = 0
    for appointment in appointments:
        recipients = [appointment.patient.email, appointment.doctor.email]
        send_mail(
            'Upcoming telemedicine appointment',
            f'Your appointment starts at {appointment.scheduled_start}.',
            settings.DEFAULT_FROM_EMAIL,
            recipients,
            fail_silently=True,
        )
        sent += len(recipients)
    return f'Sent {sent} appointment reminders'
