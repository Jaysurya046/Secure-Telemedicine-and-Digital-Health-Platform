"""Serializers for consultations."""
from collections.abc import Mapping
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.appointments.models import Appointment
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
        extra_kwargs = {
            'patient': {'required': False},
            'doctor': {'required': False},
        }

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            return super().to_internal_value(data)

        if hasattr(data, 'copy'):
            data = data.copy()
        else:
            data = dict(data)

        # Apply creation security rules only when creating a new consultation
        if self.instance is None:
            request = self.context.get('request')
            user = getattr(request, 'user', None)

            # Reject patient-supplied clinical fields during creation
            if user and getattr(user, 'role', None) == 'patient':
                clinical_fields = ['diagnosis', 'clinical_notes', 'follow_up_required', 'follow_up_notes']
                injected = [f for f in clinical_fields if f in data]
                if injected:
                    raise serializers.ValidationError({
                        f: 'Patients cannot supply clinical fields during consultation creation.'
                        for f in injected
                    })

            raw_appointment = data.get('appointment')
            if raw_appointment is None or str(raw_appointment).strip() == '':
                raise serializers.ValidationError({
                    'appointment': 'Confirmed appointment is required to create a consultation.'
                })

            raw_appointment_id = getattr(raw_appointment, 'id', raw_appointment)
            try:
                appointment = Appointment.objects.select_related('patient', 'doctor').get(id=raw_appointment_id)
            except (Appointment.DoesNotExist, DjangoValidationError, ValueError, TypeError):
                raise serializers.ValidationError({
                    'appointment': 'Referenced appointment does not exist.'
                })

            # 1. Must be a confirmed appointment
            if appointment.status != 'confirmed':
                raise serializers.ValidationError({
                    'appointment': f'Appointment must be confirmed (current status: {appointment.status}).'
                })

            # 2. Duplicate check
            if Consultation.objects.filter(appointment=appointment).exists():
                raise serializers.ValidationError({
                    'appointment': 'A consultation already exists for this appointment.'
                })

            # 3. Caller authorization check
            if not user or not user.is_authenticated:
                raise serializers.ValidationError({
                    'detail': 'Authentication credentials were not provided.'
                })

            if user.role == 'patient':
                if appointment.patient_id != user.id:
                    raise serializers.ValidationError({
                        'appointment': 'Patients may only create consultations for their own appointments.'
                    })
            elif user.role == 'doctor':
                if appointment.doctor_id != user.id:
                    raise serializers.ValidationError({
                        'appointment': 'Doctors may only create consultations for appointments assigned to them.'
                    })
            elif user.role == 'admin':
                # Admins may create for any qualifying appointment
                pass
            else:
                raise serializers.ValidationError({
                    'detail': 'Your role is not permitted to create consultations.'
                })

            # 4. Status derivation & validation: initial status must be scheduled
            if 'status' in data and data['status'] is not None and str(data['status']).strip() != '':
                if str(data['status']).strip() != 'scheduled':
                    raise serializers.ValidationError({
                        'status': "Initial status must be 'scheduled'."
                    })
            data['status'] = 'scheduled'

            # 5. Patient derivation & conflict check
            if 'patient' in data and data['patient'] is not None and str(data['patient']).strip() != '':
                raw_patient = data['patient']
                raw_patient_id = getattr(raw_patient, 'id', raw_patient)
                if str(raw_patient_id) != str(appointment.patient_id):
                    raise serializers.ValidationError({
                        'patient': 'Supplied patient conflicts with the appointment.'
                    })
            data['patient'] = appointment.patient_id

            # 6. Doctor derivation & conflict check
            if 'doctor' in data and data['doctor'] is not None and str(data['doctor']).strip() != '':
                raw_doctor = data['doctor']
                raw_doctor_id = getattr(raw_doctor, 'id', raw_doctor)
                if str(raw_doctor_id) != str(appointment.doctor_id):
                    raise serializers.ValidationError({
                        'doctor': 'Supplied doctor conflicts with the appointment.'
                    })
            data['doctor'] = appointment.doctor_id

        if self.instance is not None:
            # 1. Appointment immutability
            if 'appointment' in data:
                raw_appt = data['appointment']
                raw_appt_id = getattr(raw_appt, 'id', raw_appt) if raw_appt is not None else None
                inst_appt_id = getattr(self.instance.appointment, 'id', self.instance.appointment_id)
                if str(raw_appt_id or '') != str(inst_appt_id or ''):
                    raise serializers.ValidationError({
                        'appointment': 'Appointment cannot be changed after creation.'
                    })

            # 2. Patient immutability
            if 'patient' in data:
                raw_pat = data['patient']
                raw_pat_id = getattr(raw_pat, 'id', raw_pat) if raw_pat is not None else None
                inst_pat_id = getattr(self.instance.patient, 'id', self.instance.patient_id)
                if str(raw_pat_id or '') != str(inst_pat_id or ''):
                    raise serializers.ValidationError({
                        'patient': 'Patient cannot be changed after creation.'
                    })

            # 3. Doctor immutability
            if 'doctor' in data:
                raw_doc = data['doctor']
                raw_doc_id = getattr(raw_doc, 'id', raw_doc) if raw_doc is not None else None
                inst_doc_id = getattr(self.instance.doctor, 'id', self.instance.doctor_id)
                if str(raw_doc_id or '') != str(inst_doc_id or ''):
                    raise serializers.ValidationError({
                        'doctor': 'Doctor cannot be changed after creation.'
                    })

            # 4. Status immutability via generic PUT/PATCH
            if 'status' in data:
                raw_status = str(data['status']).strip() if data['status'] is not None else ''
                if raw_status != str(self.instance.status):
                    raise serializers.ValidationError({
                        'status': 'Status cannot be changed directly via PUT/PATCH. Use lifecycle actions instead.'
                    })

        return super().to_internal_value(data)

    def validate_patient(self, value):
        if value.role != 'patient':
            raise serializers.ValidationError('Selected user must be a patient.')
        return value

    def validate_doctor(self, value):
        if value.role != 'doctor':
            raise serializers.ValidationError('Selected user must be a doctor.')
        return value


class ConsultationStartSerializer(serializers.Serializer):
    """Supporting serializer for starting a consultation session."""

    def validate(self, attrs):
        if isinstance(self.initial_data, Mapping):
            extra_fields = set(self.initial_data.keys())
            if extra_fields:
                raise serializers.ValidationError({
                    field: f"Unexpected field '{field}'."
                    for field in sorted(extra_fields)
                })
        return attrs


class ConsultationEndSerializer(serializers.Serializer):
    """Supporting serializer for ending a consultation session and validating clinical fields."""
    ALLOWED_FIELDS = {'diagnosis', 'clinical_notes', 'follow_up_required', 'follow_up_notes'}

    diagnosis = serializers.CharField(required=False, allow_blank=True)
    clinical_notes = serializers.CharField(required=False, allow_blank=True)
    follow_up_required = serializers.BooleanField(required=False)
    follow_up_notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if isinstance(self.initial_data, Mapping):
            extra_fields = set(self.initial_data.keys()) - self.ALLOWED_FIELDS
            if extra_fields:
                raise serializers.ValidationError({
                    field: f"Unexpected field '{field}'."
                    for field in sorted(extra_fields)
                })
        return attrs
