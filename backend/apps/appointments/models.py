"""Appointments app models."""
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
import uuid


class Appointment(models.Model):
    """A scheduled appointment between a patient and doctor."""

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
        ('no_show', 'No Show'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='patient_appointments',
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='doctor_appointments',
    )
    scheduled_start = models.DateTimeField(db_index=True)
    scheduled_end = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reason = models.CharField(max_length=255)
    symptoms = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)
    meeting_link = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'appointments'
        ordering = ['scheduled_start']
        indexes = [
            models.Index(fields=['patient', 'scheduled_start']),
            models.Index(fields=['doctor', 'scheduled_start']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.patient.email} with {self.doctor.email} at {self.scheduled_start}"

    def clean(self):
        if self.patient_id and getattr(self.patient, 'role', None) != 'patient':
            raise ValidationError({'patient': 'Selected user must be a patient.'})
        if self.doctor_id and getattr(self.doctor, 'role', None) != 'doctor':
            raise ValidationError({'doctor': 'Selected user must be a doctor.'})
        if self.scheduled_end <= self.scheduled_start:
            raise ValidationError({'scheduled_end': 'End time must be after start time.'})

    @property
    def is_upcoming(self):
        return self.status in ['pending', 'confirmed'] and self.scheduled_start > timezone.now()


class DoctorAvailability(models.Model):
    """Weekly availability windows for doctors."""

    WEEKDAY_CHOICES = (
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='availability_windows',
    )
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'doctor_availability'
        ordering = ['doctor', 'weekday', 'start_time']
        unique_together = ('doctor', 'weekday', 'start_time', 'end_time')

    def __str__(self):
        return f"{self.doctor.email} {self.get_weekday_display()} {self.start_time}-{self.end_time}"

    def clean(self):
        if self.doctor_id and getattr(self.doctor, 'role', None) != 'doctor':
            raise ValidationError({'doctor': 'Selected user must be a doctor.'})
        if self.end_time <= self.start_time:
            raise ValidationError({'end_time': 'End time must be after start time.'})
