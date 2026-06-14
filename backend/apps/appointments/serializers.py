"""Serializers for appointment scheduling."""
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.users.serializers import DoctorListSerializer, PatientListSerializer
from .models import Appointment, DoctorAvailability

User = get_user_model()


class AppointmentSerializer(serializers.ModelSerializer):
    patient_detail = PatientListSerializer(source='patient', read_only=True)
    doctor_detail = DoctorListSerializer(source='doctor', read_only=True)

    class Meta:
        model = Appointment
        fields = [
            'id', 'patient', 'doctor', 'patient_detail', 'doctor_detail',
            'scheduled_start', 'scheduled_end', 'status', 'reason', 'symptoms',
            'notes', 'cancellation_reason', 'meeting_link', 'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'meeting_link']

    def validate_patient(self, value):
        if value.role != 'patient':
            raise serializers.ValidationError('Selected user must be a patient.')
        return value

    def validate_doctor(self, value):
        if value.role != 'doctor':
            raise serializers.ValidationError('Selected user must be a doctor.')
        return value

    def validate(self, attrs):
        scheduled_start = attrs.get('scheduled_start', getattr(self.instance, 'scheduled_start', None))
        scheduled_end = attrs.get('scheduled_end', getattr(self.instance, 'scheduled_end', None))
        doctor = attrs.get('doctor', getattr(self.instance, 'doctor', None))
        if scheduled_start and scheduled_end and scheduled_end <= scheduled_start:
            raise serializers.ValidationError({'scheduled_end': 'End time must be after start time.'})
        if doctor and scheduled_start and scheduled_end:
            conflicts = Appointment.objects.filter(
                doctor=doctor,
                status__in=['pending', 'confirmed'],
                scheduled_start__lt=scheduled_end,
                scheduled_end__gt=scheduled_start,
            )
            if self.instance:
                conflicts = conflicts.exclude(pk=self.instance.pk)
            if conflicts.exists():
                raise serializers.ValidationError('Doctor already has an appointment in that time window.')
        return attrs


class DoctorAvailabilitySerializer(serializers.ModelSerializer):
    doctor_detail = DoctorListSerializer(source='doctor', read_only=True)

    class Meta:
        model = DoctorAvailability
        fields = [
            'id', 'doctor', 'doctor_detail', 'weekday', 'start_time',
            'end_time', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_doctor(self, value):
        if value.role != 'doctor':
            raise serializers.ValidationError('Selected user must be a doctor.')
        return value

    def validate(self, attrs):
        start_time = attrs.get('start_time', getattr(self.instance, 'start_time', None))
        end_time = attrs.get('end_time', getattr(self.instance, 'end_time', None))
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError({'end_time': 'End time must be after start time.'})
        return attrs
