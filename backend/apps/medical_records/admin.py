"""Admin for medical records."""
from django.contrib import admin

from .models import MedicalDocument, MedicalRecord, Prescription, PrescriptionItem


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 0


@admin.register(MedicalRecord)
class MedicalRecordAdmin(admin.ModelAdmin):
    list_display = ['title', 'patient', 'doctor', 'record_type', 'created_at']
    list_filter = ['record_type', 'is_sensitive', 'created_at']
    search_fields = ['title', 'description', 'patient__email', 'doctor__email']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ['id', 'patient', 'doctor', 'status', 'valid_until', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['patient__email', 'doctor__email', 'instructions']
    readonly_fields = ['verification_code', 'created_at', 'updated_at']
    inlines = [PrescriptionItemInline]


@admin.register(PrescriptionItem)
class PrescriptionItemAdmin(admin.ModelAdmin):
    list_display = ['medication_name', 'dosage', 'frequency', 'duration']
    search_fields = ['medication_name']


@admin.register(MedicalDocument)
class MedicalDocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'patient', 'document_type', 'uploaded_by', 'created_at']
    list_filter = ['document_type', 'is_encrypted', 'created_at']
    search_fields = ['title', 'patient__email', 'uploaded_by__email']
    readonly_fields = ['file_hash', 'created_at']
