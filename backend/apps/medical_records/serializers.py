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


class ClinicalOwnershipValidationMixin:
    """
    Validation mixin for MedicalRecord and Prescription serializers.
    
    Required behavior:
    - On doctor creation, derive doctor from the authenticated user before validation.
      Omitting doctor must work; supplying another doctor must be rejected.
    - Admin creation must validate the selected author's doctor role.
    - Patient references must identify users with the patient role.
    - After creation, patient and doctor are immutable through PUT/PATCH, including admin requests.
      Unchanged values may be accepted.
    - Any supplied consultation must match the record/prescription's effective patient and doctor.
      Preserve existing nullable behavior.
    """

    def to_internal_value(self, data):
        if hasattr(data, 'copy'):
            data = data.copy()
        elif isinstance(data, dict):
            data = dict(data)

        request = self.context.get('request')
        user = getattr(request, 'user', None)

        # On doctor creation, derive doctor from authenticated user before validation.
        # Omitting doctor must work; supplying another doctor must be rejected.
        if self.instance is None and user and getattr(user, 'role', None) == 'doctor':
            if 'doctor' in data and data['doctor'] is not None and str(data['doctor']).strip() != '':
                raw_doctor = data['doctor']
                raw_doctor_id = getattr(raw_doctor, 'id', raw_doctor)
                if str(raw_doctor_id) != str(user.id):
                    raise serializers.ValidationError({
                        'doctor': 'You cannot specify another doctor as the author.'
                    })
            data['doctor'] = user.id

        return super().to_internal_value(data)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        # 1. Patient reference validation: must have the 'patient' role
        patient = attrs.get('patient')
        if self.instance is None and patient is None:
            raise serializers.ValidationError({'patient': 'Patient is required.'})

        if patient is not None:
            if getattr(patient, 'role', None) != 'patient':
                raise serializers.ValidationError({'patient': 'Selected user must have the patient role.'})

        # 2. Doctor reference validation on creation
        if self.instance is None:
            doctor = attrs.get('doctor')
            if user and getattr(user, 'role', None) == 'doctor':
                if doctor is None:
                    attrs['doctor'] = user
                elif doctor != user:
                    raise serializers.ValidationError({'doctor': 'You cannot specify another doctor as the author.'})
            elif user and getattr(user, 'role', None) == 'admin':
                if doctor is not None and getattr(doctor, 'role', None) != 'doctor':
                    raise serializers.ValidationError({'doctor': 'Selected author must have the doctor role.'})

        # 3. Immutability on update (PUT/PATCH), including admin requests
        if self.instance is not None and hasattr(self, 'initial_data'):
            if 'patient' in self.initial_data:
                new_patient = attrs.get('patient')
                if new_patient != self.instance.patient:
                    raise serializers.ValidationError({'patient': 'Patient cannot be changed after creation.'})

            if 'doctor' in self.initial_data:
                new_doctor = attrs.get('doctor')
                if new_doctor != self.instance.doctor:
                    raise serializers.ValidationError({'doctor': 'Doctor cannot be changed after creation.'})

        # 4. Consultation validation: must match effective patient and doctor
        effective_patient = self.instance.patient if self.instance is not None else attrs.get('patient')
        effective_doctor = self.instance.doctor if self.instance is not None else attrs.get('doctor')

        consultation = attrs.get('consultation')
        if consultation is not None:
            if effective_patient is not None and consultation.patient_id != effective_patient.id:
                raise serializers.ValidationError({
                    'consultation': 'Consultation patient does not match the record/prescription patient.'
                })
            if effective_doctor is None or consultation.doctor_id != effective_doctor.id:
                raise serializers.ValidationError({
                    'consultation': 'Consultation doctor does not match the record/prescription doctor.'
                })

        return attrs


class MedicalRecordSerializer(ClinicalOwnershipValidationMixin, serializers.ModelSerializer):
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
        extra_kwargs = {
            'doctor': {'required': False},
            'consultation': {'required': False},
        }


class PrescriptionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionItem
        fields = ['id', 'medication_name', 'dosage', 'frequency', 'duration', 'instructions']
        read_only_fields = ['id']


class PrescriptionSerializer(ClinicalOwnershipValidationMixin, serializers.ModelSerializer):
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
        extra_kwargs = {
            'doctor': {'required': False},
            'consultation': {'required': False},
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Prescriptions strictly require a doctor (model has null=False)
        if self.instance is None and not attrs.get('doctor'):
            raise serializers.ValidationError({'doctor': 'Doctor is required for prescriptions.'})
        return attrs

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
