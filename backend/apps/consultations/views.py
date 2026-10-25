"""Views for consultations."""
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from .models import Consultation, ConsultationMessage
from .permissions import ConsultationAccessPermission
from .serializers import (
    ConsultationSerializer,
    ConsultationMessageSerializer,
    ConsultationStartSerializer,
    ConsultationEndSerializer,
    MessageCreateSerializer,
)


class MessagePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class ConsultationViewSet(viewsets.ModelViewSet):
    serializer_class = ConsultationSerializer
    permission_classes = [IsAuthenticated, ConsultationAccessPermission]
    filterset_fields = ['status', 'doctor', 'patient', 'appointment', 'room_id']
    ordering_fields = ['created_at', 'started_at']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = Consultation.objects.select_related(
            'appointment', 'patient', 'patient__profile', 'doctor', 'doctor__profile', 'doctor__doctor_profile'
        )
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

        serializer = ConsultationStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            locked = Consultation.objects.select_for_update().get(id=consultation.id)
            if locked.status != 'scheduled':
                return Response(
                    {
                        'error': True,
                        'message': f"Cannot start consultation with status '{locked.status}'. Only 'scheduled' consultations can be started.",
                        'detail': f"Cannot start consultation with status '{locked.status}'. Only 'scheduled' consultations can be started.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            locked.status = 'in_progress'
            locked.started_at = timezone.now()
            locked.save(update_fields=['status', 'started_at', 'updated_at'])
            return Response(self.get_serializer(locked).data)

    @action(detail=True, methods=['post'])
    def end(self, request, pk=None):
        consultation = self.get_object()
        if request.user.role not in ['doctor', 'admin']:
            return Response({'error': 'Only doctors or admins can end consultations.'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role == 'doctor' and consultation.doctor_id != request.user.id:
            return Response({'error': 'Only the assigned doctor can end this consultation.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = ConsultationEndSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            locked = Consultation.objects.select_for_update().get(id=consultation.id)
            if locked.status != 'in_progress':
                return Response(
                    {
                        'error': True,
                        'message': f"Cannot end consultation with status '{locked.status}'. Only 'in_progress' consultations can be ended.",
                        'detail': f"Cannot end consultation with status '{locked.status}'. Only 'in_progress' consultations can be ended.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            locked.status = 'completed'
            locked.ended_at = timezone.now()
            # started_at is preserved
            update_fields = ['status', 'ended_at', 'updated_at']
            for field in ['diagnosis', 'clinical_notes', 'follow_up_notes', 'follow_up_required']:
                if field in serializer.validated_data:
                    setattr(locked, field, serializer.validated_data[field])
                    update_fields.append(field)
            locked.save(update_fields=update_fields)
            return Response(self.get_serializer(locked).data)

    @action(detail=False, methods=['get'])
    def identity(self, request):
        # JWTAuthentication loads the current active user from Django on every call.
        return Response({'id': str(request.user.id), 'role': request.user.role, 'email': request.user.email})

    @action(detail=True, methods=['get', 'post'])
    def messages(self, request, pk=None):
        consultation = self.get_object()
        if request.method == 'GET':
            qs = ConsultationMessage.objects.filter(consultation=consultation).select_related('sender').order_by('-sent_at', '-id')
            paginator = MessagePagination()
            page = paginator.paginate_queryset(qs, request)
            return paginator.get_paginated_response(ConsultationMessageSerializer(page, many=True).data)

        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            locked = Consultation.objects.select_for_update().get(pk=consultation.pk)
            key = data.get('client_msg_id', '')
            # Retries remain safe even if the consultation ended after the first send.
            if key:
                existing = ConsultationMessage.objects.filter(
                    consultation=locked, sender=request.user, client_msg_id=key,
                ).first()
                if existing:
                    if existing.message != data['message']:
                        return Response({'detail': 'Retry key already used for different content.'}, status=409)
                    return Response(ConsultationMessageSerializer(existing).data)
            if locked.status not in ('scheduled', 'in_progress'):
                return Response({'detail': 'This consultation is closed for new messages.'}, status=409)
            message = ConsultationMessage.objects.create(
                consultation=locked, sender=request.user, message=data['message'], client_msg_id=key,
            )
            return Response(ConsultationMessageSerializer(message).data, status=201)
