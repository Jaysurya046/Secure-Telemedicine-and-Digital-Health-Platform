"""Serializers for medical records."""
from rest_framework import serializers

from apps.users.serializers import DoctorListSerializer, PatientListSerializer
from .models import MedicalDocument, MedicalRecord, Prescription, PrescriptionItem


class MedicalDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.EmailField(source='uploaded_by.email', read_only=True)

    class Meta:
        model = MedicalDocument
        fields = [
            'id', 'patient', 'uploaded_by', 'uploaded_by_email', 'record',
            'document_type', 'title', 'file', 'file_hash', 'is_encrypted',
            'created_at',
        ]
        read_only_fields = ['id', 'uploaded_by', 'uploaded_by_email', 'file_hash', 'is_encrypted', 'created_at']
        extra_kwargs = {'patient': {'required': False}}


class MedicalRecordSerializer(serializers.ModelSerializer):
    patient_detail = PatientListSerializer(source='patient', read_only=True)
    doctor_detail = DoctorListSerializer(source='doctor', read_only=True)
    documents = MedicalDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = MedicalRecord
        fields = [
            'id', 'patient', 'doctor', 'patient_detail', 'doctor_detail',
            'consultation', 'record_type', 'title', 'description', 'metadata',
            'is_sensitive', 'documents', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PrescriptionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionItem
        fields = ['id', 'medication_name', 'dosage', 'frequency', 'duration', 'instructions']
        read_only_fields = ['id']


class PrescriptionSerializer(serializers.ModelSerializer):
    patient_detail = PatientListSerializer(source='patient', read_only=True)
    doctor_detail = DoctorListSerializer(source='doctor', read_only=True)
    items = PrescriptionItemSerializer(many=True, required=False)

    class Meta:
        model = Prescription
        fields = [
            'id', 'patient', 'doctor', 'patient_detail', 'doctor_detail',
            'consultation', 'status', 'instructions', 'valid_until',
            'verification_code', 'items', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'verification_code', 'created_at', 'updated_at']

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        prescription = Prescription.objects.create(**validated_data)
        for item_data in items_data:
            PrescriptionItem.objects.create(prescription=prescription, **item_data)
        return prescription

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                PrescriptionItem.objects.create(prescription=instance, **item_data)
        return instance
