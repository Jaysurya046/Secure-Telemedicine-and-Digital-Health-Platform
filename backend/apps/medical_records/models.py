"""Medical records app models."""
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
import uuid


class MedicalRecord(models.Model):
    """Clinical record for a patient."""

    RECORD_TYPE_CHOICES = (
        ('consultation', 'Consultation'),
        ('lab', 'Lab Result'),
        ('imaging', 'Imaging'),
        ('summary', 'Summary'),
        ('other', 'Other'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='medical_records',
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_medical_records',
    )
    consultation = models.ForeignKey(
        'consultations.Consultation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='medical_records',
    )
    record_type = models.CharField(max_length=20, choices=RECORD_TYPE_CHOICES, default='summary')
    title = models.CharField(max_length=150)
    description = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    is_sensitive = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'medical_records'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['patient', 'created_at']),
            models.Index(fields=['doctor', 'created_at']),
            models.Index(fields=['record_type']),
        ]

    def __str__(self):
        return f"{self.title} - {self.patient.email}"

    def clean(self):
        if self.patient_id and getattr(self.patient, 'role', None) != 'patient':
            raise ValidationError({'patient': 'Selected user must be a patient.'})
        if self.doctor_id and getattr(self.doctor, 'role', None) != 'doctor':
            raise ValidationError({'doctor': 'Selected user must be a doctor.'})


class Prescription(models.Model):
    """Digital prescription issued by a doctor."""

    STATUS_CHOICES = (
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='prescriptions',
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='issued_prescriptions',
    )
    consultation = models.ForeignKey(
        'consultations.Consultation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prescriptions',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    instructions = models.TextField(blank=True)
    valid_until = models.DateField(null=True, blank=True)
    verification_code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'prescriptions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['patient', 'created_at']),
            models.Index(fields=['doctor', 'created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Prescription {self.id} for {self.patient.email}"


class PrescriptionItem(models.Model):
    """Medication line item for a prescription."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name='items',
    )
    medication_name = models.CharField(max_length=150)
    dosage = models.CharField(max_length=100)
    frequency = models.CharField(max_length=100)
    duration = models.CharField(max_length=100)
    instructions = models.TextField(blank=True)

    class Meta:
        db_table = 'prescription_items'

    def __str__(self):
        return self.medication_name


class MedicalDocument(models.Model):
    """Uploaded medical file metadata."""

    DOCUMENT_TYPE_CHOICES = (
        ('report', 'Report'),
        ('lab', 'Lab Result'),
        ('imaging', 'Imaging'),
        ('prescription', 'Prescription'),
        ('insurance', 'Insurance'),
        ('other', 'Other'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='medical_documents',
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_medical_documents',
    )
    record = models.ForeignKey(
        MedicalRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
    )
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES, default='other')
    title = models.CharField(max_length=150)
    file = models.FileField(upload_to='medical_documents/')
    file_hash = models.CharField(max_length=64, blank=True)
    is_encrypted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'medical_documents'
        ordering = ['-created_at']

    def __str__(self):
        return self.title
