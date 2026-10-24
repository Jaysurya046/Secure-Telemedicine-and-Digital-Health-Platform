"""Serializers for appointment scheduling."""
from collections.abc import Mapping
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
        extra_kwargs = {
            'patient': {'required': False},
            'doctor': {'required': False},
            'status': {'required': False},
        }

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            return super().to_internal_value(data)

        if hasattr(data, 'copy'):
            data = data.copy()
        else:
            data = dict(data)

        request = self.context.get('request')
        user = getattr(request, 'user', None)

        if self.instance is None and user and user.is_authenticated:
            # Patient creation derives patient from the caller before validation.
            # Omitting patient must work; conflicting patient IDs must be rejected.
            if getattr(user, 'role', None) == 'patient':
                if 'patient' in data and data['patient'] not in (None, ''):
                    raw_patient = data['patient']
                    raw_patient_id = getattr(raw_patient, 'id', raw_patient)
                    if str(raw_patient_id) != str(user.id):
                        raise serializers.ValidationError({
                            'patient': 'You cannot schedule an appointment for another patient.'
                        })
                data['patient'] = user.id

            # Doctor creation similarly derives doctor and rejects author spoofing.
            elif getattr(user, 'role', None) == 'doctor':
                if 'doctor' in data and data['doctor'] not in (None, ''):
                    raw_doctor = data['doctor']
                    raw_doctor_id = getattr(raw_doctor, 'id', raw_doctor)
                    if str(raw_doctor_id) != str(user.id):
                        raise serializers.ValidationError({
                            'doctor': 'You cannot specify another doctor as the author.'
                        })
                data['doctor'] = user.id

        return super().to_internal_value(data)

    def validate_patient(self, value):
        if value.role != 'patient':
            raise serializers.ValidationError('Selected user must be a patient.')
        return value

    def validate_doctor(self, value):
        if value.role != 'doctor':
            raise serializers.ValidationError('Selected user must be a doctor.')
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        # Creation validation
        if self.instance is None:
            if not attrs.get('patient'):
                raise serializers.ValidationError({'patient': 'Patient is required.'})
            if not attrs.get('doctor'):
                raise serializers.ValidationError({'doctor': 'Doctor is required.'})

            # Every new appointment starts as pending. Reject supplied non-pending status.
            if hasattr(self, 'initial_data') and 'status' in self.initial_data:
                supplied_status = self.initial_data.get('status')
                if supplied_status != 'pending':
                    raise serializers.ValidationError({
                        'status': 'New appointments must start with pending status.'
                    })
            attrs['status'] = 'pending'

        # Update validation (PUT/PATCH)
        else:
            if hasattr(self, 'initial_data'):
                # Patient and doctor are immutable after creation, including admin updates.
                # Accept unchanged values.
                if 'patient' in self.initial_data:
                    new_patient = attrs.get('patient')
                    if new_patient != self.instance.patient:
                        raise serializers.ValidationError({
                            'patient': 'Patient cannot be changed after creation.'
                        })

                if 'doctor' in self.initial_data:
                    new_doctor = attrs.get('doctor')
                    if new_doctor != self.instance.doctor:
                        raise serializers.ValidationError({
                            'doctor': 'Doctor cannot be changed after creation.'
                        })

                # Generic PUT/PATCH must reject status changes.
                if 'status' in self.initial_data:
                    new_status = self.initial_data.get('status')
                    if new_status != self.instance.status:
                        raise serializers.ValidationError({
                            'status': 'Status cannot be updated directly. Use the confirm, cancel, or complete actions.'
                        })

            attrs.pop('status', None)

        # Existing time and conflict validation
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


class AppointmentConfirmSerializer(serializers.Serializer):
    """
    Supporting serializer for confirming appointments.
    Accepts only empty objects or genuinely bodyless requests.
    Rejects unknown fields and non-object JSON, including explicit null and "".
    """

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            raise serializers.ValidationError({'non_field_errors': ['Expected an object or empty body.']})
        return super().to_internal_value(data)

    def validate(self, attrs):
        if not isinstance(self.initial_data, Mapping):
            raise serializers.ValidationError({'non_field_errors': ['Expected an object or empty body.']})
        extra_fields = set(self.initial_data.keys())
        if extra_fields:
            raise serializers.ValidationError({
                field: f"Unexpected field '{field}'. This action accepts no parameters."
                for field in sorted(extra_fields)
            })
        return attrs


class AppointmentCompleteSerializer(AppointmentConfirmSerializer):
    """
    Supporting serializer for completing appointments.
    Accepts only empty objects or genuinely bodyless requests.
    Rejects unknown fields and non-object JSON, including explicit null and "".
    """
    pass


class AppointmentCancelSerializer(serializers.Serializer):
    """
    Supporting serializer for cancelling appointments.
    Accepts only an optional cancellation_reason string; allow blank, reject null and structured values.
    Reject unknown fields and non-object JSON, including explicit null and "".
    """
    ALLOWED_FIELDS = {'cancellation_reason'}

    cancellation_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=False,
    )

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            raise serializers.ValidationError({'non_field_errors': ['Expected an object.']})
        if 'cancellation_reason' in data:
            raw = data['cancellation_reason']
            if raw is None:
                raise serializers.ValidationError({'cancellation_reason': ['This field may not be null.']})
            if not isinstance(raw, str):
                raise serializers.ValidationError({'cancellation_reason': ['Must be a string; structured values are rejected.']})
        return super().to_internal_value(data)

    def validate(self, attrs):
        if not isinstance(self.initial_data, Mapping):
            raise serializers.ValidationError({'non_field_errors': ['Expected an object.']})
        extra_fields = set(self.initial_data.keys()) - self.ALLOWED_FIELDS
        if extra_fields:
            raise serializers.ValidationError({
                field: f"Unexpected field '{field}'."
                for field in sorted(extra_fields)
            })
        return attrs
