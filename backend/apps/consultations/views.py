"""Views for consultations."""
from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Consultation, ConsultationMessage
from .permissions import ConsultationAccessPermission
from .serializers import ConsultationSerializer, ConsultationMessageSerializer


class ConsultationViewSet(viewsets.ModelViewSet):
    serializer_class = ConsultationSerializer
    permission_classes = [IsAuthenticated, ConsultationAccessPermission]
    filterset_fields = ['status', 'doctor', 'patient', 'appointment']
    ordering_fields = ['created_at', 'started_at']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = Consultation.objects.select_related(
            'appointment', 'patient', 'patient__profile', 'doctor', 'doctor__profile', 'doctor__doctor_profile'
        ).prefetch_related('messages')
        user = self.request.user
        if not user.is_authenticated:
            return Consultation.objects.none()
        if user.role == 'admin':
            return queryset
        if user.role == 'doctor':
            return queryset.filter(doctor=user)
        if user.role == 'patient':
            return queryset.filter(patient=user)
        return Consultation.objects.none()

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError:
            return Response(
                {
                    'error': True,
                    'message': 'A consultation already exists for this appointment.',
                    'details': {'appointment': ['A consultation already exists for this appointment.']},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    def perform_create(self, serializer):
        appointment = serializer.validated_data.get('appointment')
        if appointment:
            serializer.save(
                patient=appointment.patient,
                doctor=appointment.doctor,
                status='scheduled',
            )
        else:
            serializer.save(status='scheduled')

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        consultation = self.get_object()
        if request.user.role not in ['doctor', 'admin']:
            return Response({'error': 'Only doctors or admins can start consultations.'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role == 'doctor' and consultation.doctor_id != request.user.id:
            return Response({'error': 'Only the assigned doctor can start this consultation.'}, status=status.HTTP_403_FORBIDDEN)
        consultation.status = 'in_progress'
        consultation.started_at = consultation.started_at or timezone.now()
        consultation.save(update_fields=['status', 'started_at', 'updated_at'])
        return Response(self.get_serializer(consultation).data)

    @action(detail=True, methods=['post'])
    def end(self, request, pk=None):
        consultation = self.get_object()
        if request.user.role not in ['doctor', 'admin']:
            return Response({'error': 'Only doctors or admins can end consultations.'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role == 'doctor' and consultation.doctor_id != request.user.id:
            return Response({'error': 'Only the assigned doctor can end this consultation.'}, status=status.HTTP_403_FORBIDDEN)
        consultation.status = 'completed'
        consultation.ended_at = timezone.now()
        for field in ['diagnosis', 'clinical_notes', 'follow_up_notes']:
            if field in request.data:
                setattr(consultation, field, request.data[field])
        if 'follow_up_required' in request.data:
            consultation.follow_up_required = bool(request.data['follow_up_required'])
        consultation.save()
        return Response(self.get_serializer(consultation).data)

    @action(detail=True, methods=['post'])
    def messages(self, request, pk=None):
        consultation = self.get_object()
        serializer = ConsultationMessageSerializer(data={
            'consultation': consultation.id,
            'message': request.data.get('message', ''),
        })
        serializer.is_valid(raise_exception=True)
        message = serializer.save(consultation=consultation, sender=request.user)
        return Response(ConsultationMessageSerializer(message).data, status=status.HTTP_201_CREATED)
