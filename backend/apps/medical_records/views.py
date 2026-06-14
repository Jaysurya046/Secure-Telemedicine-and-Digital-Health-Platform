"""Views for medical records and prescriptions."""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .encryption import sha256_file
from .models import MedicalDocument, MedicalRecord, Prescription
from .serializers import MedicalDocumentSerializer, MedicalRecordSerializer, PrescriptionSerializer


class MedicalAccessMixin:
    def filter_for_user(self, queryset):
        user = self.request.user
        if user.role == 'admin':
            return queryset
        if user.role == 'doctor':
            return queryset.filter(doctor=user) if hasattr(queryset.model, 'doctor') else queryset.filter(uploaded_by=user)
        return queryset.filter(patient=user)


class MedicalRecordViewSet(MedicalAccessMixin, viewsets.ModelViewSet):
    serializer_class = MedicalRecordSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['patient', 'doctor', 'record_type', 'consultation']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    search_fields = ['title', 'description']

    def get_queryset(self):
        return self.filter_for_user(
            MedicalRecord.objects.select_related(
                'patient', 'patient__profile', 'doctor', 'doctor__profile', 'doctor__doctor_profile', 'consultation'
            ).prefetch_related('documents')
        )

    def perform_create(self, serializer):
        doctor = self.request.user if self.request.user.role == 'doctor' else serializer.validated_data.get('doctor')
        serializer.save(doctor=doctor)

    def create(self, request, *args, **kwargs):
        if request.user.role not in ['doctor', 'admin']:
            return Response({'error': 'Only doctors or admins can create clinical records.'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)


class PrescriptionViewSet(MedicalAccessMixin, viewsets.ModelViewSet):
    serializer_class = PrescriptionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['patient', 'doctor', 'status', 'consultation']
    ordering_fields = ['created_at', 'valid_until']
    ordering = ['-created_at']

    def get_queryset(self):
        return self.filter_for_user(
            Prescription.objects.select_related(
                'patient', 'patient__profile', 'doctor', 'doctor__profile', 'doctor__doctor_profile', 'consultation'
            ).prefetch_related('items')
        )

    def perform_create(self, serializer):
        doctor = self.request.user if self.request.user.role == 'doctor' else serializer.validated_data.get('doctor')
        serializer.save(doctor=doctor)

    def create(self, request, *args, **kwargs):
        if request.user.role not in ['doctor', 'admin']:
            return Response({'error': 'Only doctors or admins can issue prescriptions.'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        prescription = self.get_object()
        if request.user.role not in ['doctor', 'admin']:
            return Response({'error': 'Only doctors or admins can cancel prescriptions.'}, status=status.HTTP_403_FORBIDDEN)
        prescription.status = 'cancelled'
        prescription.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(prescription).data)


class MedicalDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = MedicalDocumentSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['patient', 'document_type', 'record']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    search_fields = ['title']

    def get_queryset(self):
        queryset = MedicalDocument.objects.select_related('patient', 'uploaded_by', 'record')
        user = self.request.user
        if user.role == 'admin':
            return queryset
        if user.role == 'doctor':
            return queryset.filter(uploaded_by=user)
        return queryset.filter(patient=user)

    def perform_create(self, serializer):
        if self.request.user.role == 'patient':
            document = serializer.save(uploaded_by=self.request.user, patient=self.request.user)
        else:
            document = serializer.save(uploaded_by=self.request.user)
        if document.file:
            document.file_hash = sha256_file(document.file)
            document.save(update_fields=['file_hash'])
