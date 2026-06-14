"""Serializers for consultations."""
from rest_framework import serializers

from apps.users.serializers import DoctorListSerializer, PatientListSerializer
from .models import Consultation, ConsultationMessage


class ConsultationMessageSerializer(serializers.ModelSerializer):
    sender_email = serializers.EmailField(source='sender.email', read_only=True)

    class Meta:
        model = ConsultationMessage
        fields = ['id', 'consultation', 'sender', 'sender_email', 'message', 'sent_at']
        read_only_fields = ['id', 'sender', 'sender_email', 'sent_at']


class ConsultationSerializer(serializers.ModelSerializer):
    patient_detail = PatientListSerializer(source='patient', read_only=True)
    doctor_detail = DoctorListSerializer(source='doctor', read_only=True)
    messages = ConsultationMessageSerializer(many=True, read_only=True)

    class Meta:
        model = Consultation
        fields = [
            'id', 'appointment', 'patient', 'doctor', 'patient_detail',
            'doctor_detail', 'status', 'room_id', 'started_at', 'ended_at',
            'chief_complaint', 'diagnosis', 'clinical_notes',
            'follow_up_required', 'follow_up_notes', 'messages', 'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'room_id', 'started_at', 'ended_at', 'created_at', 'updated_at']

    def validate_patient(self, value):
        if value.role != 'patient':
            raise serializers.ValidationError('Selected user must be a patient.')
        return value

    def validate_doctor(self, value):
        if value.role != 'doctor':
            raise serializers.ValidationError('Selected user must be a doctor.')
        return value
