"""Consultations app models."""
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
import uuid


class Consultation(models.Model):
    """A real-time or documented consultation session."""

    STATUS_CHOICES = (
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.OneToOneField(
        'appointments.Appointment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='consultation',
    )
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='patient_consultations',
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='doctor_consultations',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    room_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    chief_complaint = models.CharField(max_length=255, blank=True)
    diagnosis = models.TextField(blank=True)
    clinical_notes = models.TextField(blank=True)
    follow_up_required = models.BooleanField(default=False)
    follow_up_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'consultations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['patient', 'created_at']),
            models.Index(fields=['doctor', 'created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Consultation {self.id}"

    def clean(self):
        if self.patient_id and getattr(self.patient, 'role', None) != 'patient':
            raise ValidationError({'patient': 'Selected user must be a patient.'})
        if self.doctor_id and getattr(self.doctor, 'role', None) != 'doctor':
            raise ValidationError({'doctor': 'Selected user must be a doctor.'})


class ConsultationMessage(models.Model):
    """Persisted text chat messages from a consultation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'consultation_messages'
        ordering = ['sent_at']

    def __str__(self):
        return f"{self.sender.email}: {self.message[:40]}"
