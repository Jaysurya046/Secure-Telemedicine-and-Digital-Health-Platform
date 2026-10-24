"""Views for appointment scheduling."""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from .models import Appointment, DoctorAvailability
from .permissions import AppointmentAccessPermission, DoctorAvailabilityAccessPermission
from .serializers import (
    AppointmentSerializer,
    DoctorAvailabilitySerializer,
    AppointmentConfirmSerializer,
    AppointmentCompleteSerializer,
    AppointmentCancelSerializer,
)


class AppointmentViewSet(viewsets.ModelViewSet):
    serializer_class = AppointmentSerializer
    permission_classes = [IsAuthenticated, AppointmentAccessPermission]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['status', 'doctor', 'patient']
    ordering_fields = ['scheduled_start', 'created_at']
    ordering = ['scheduled_start']
    search_fields = ['reason', 'notes', 'doctor__email', 'patient__email']

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return Appointment.objects.none()

        queryset = Appointment.objects.select_related(
            'patient', 'patient__profile', 'doctor', 'doctor__profile', 'doctor__doctor_profile'
        )
        role = getattr(user, 'role', None)
        if role == 'admin':
            return queryset
        if role == 'doctor':
            return queryset.filter(doctor=user)
        if role == 'patient':
            return queryset.filter(patient=user)
        return Appointment.objects.none()

    def perform_create(self, serializer):
        if self.request.user.role == 'patient':
            serializer.save(patient=self.request.user, status='pending')
        elif self.request.user.role == 'doctor':
            serializer.save(doctor=self.request.user, status='pending')
        else:
            serializer.save(status='pending')

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        appointment = self.get_object()
        if request.user.role not in ['doctor', 'admin']:
            return Response({'error': 'Only doctors or admins can confirm appointments.'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role == 'doctor' and appointment.doctor_id != request.user.id:
            return Response({'error': 'Only the assigned doctor or an admin can confirm this appointment.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = AppointmentConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            locked = Appointment.objects.select_for_update().get(id=appointment.id)
            if locked.status != 'pending':
                return Response(
                    {
                        'error': True,
                        'message': f"Cannot confirm appointment with status '{locked.status}'. Only 'pending' appointments can be confirmed.",
                        'detail': f"Cannot confirm appointment with status '{locked.status}'. Only 'pending' appointments can be confirmed.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            locked.status = 'confirmed'
            locked.save(update_fields=['status', 'updated_at'])
            return Response(self.get_serializer(locked).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        appointment = self.get_object()
        if request.user.role == 'doctor' and appointment.doctor_id != request.user.id:
            return Response({'error': 'Only the assigned doctor, patient, or an admin can cancel this appointment.'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role == 'patient' and appointment.patient_id != request.user.id:
            return Response({'error': 'Only the assigned doctor, patient, or an admin can cancel this appointment.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = AppointmentCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            locked = Appointment.objects.select_for_update().get(id=appointment.id)
            if locked.status not in ['pending', 'confirmed']:
                return Response(
                    {
                        'error': True,
                        'message': f"Cannot cancel appointment with status '{locked.status}'. Only 'pending' or 'confirmed' appointments can be cancelled.",
                        'detail': f"Cannot cancel appointment with status '{locked.status}'. Only 'pending' or 'confirmed' appointments can be cancelled.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            locked.status = 'cancelled'
            update_fields = ['status', 'updated_at']
            if 'cancellation_reason' in serializer.validated_data:
                locked.cancellation_reason = serializer.validated_data['cancellation_reason']
                update_fields.append('cancellation_reason')
            locked.save(update_fields=update_fields)
            return Response(self.get_serializer(locked).data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        appointment = self.get_object()
        if request.user.role not in ['doctor', 'admin']:
            return Response({'error': 'Only doctors or admins can complete appointments.'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role == 'doctor' and appointment.doctor_id != request.user.id:
            return Response({'error': 'Only the assigned doctor or an admin can complete this appointment.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = AppointmentCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            locked = Appointment.objects.select_for_update().get(id=appointment.id)
            if locked.status != 'confirmed':
                return Response(
                    {
                        'error': True,
                        'message': f"Cannot complete appointment with status '{locked.status}'. Only 'confirmed' appointments can be completed.",
                        'detail': f"Cannot complete appointment with status '{locked.status}'. Only 'confirmed' appointments can be completed.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            locked.status = 'completed'
            locked.save(update_fields=['status', 'updated_at'])
            return Response(self.get_serializer(locked).data)


class DoctorAvailabilityViewSet(viewsets.ModelViewSet):
    serializer_class = DoctorAvailabilitySerializer
    permission_classes = [IsAuthenticated, DoctorAvailabilityAccessPermission]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['doctor', 'weekday', 'is_active']
    ordering_fields = ['weekday', 'start_time']
    ordering = ['weekday', 'start_time']

    def get_queryset(self):
        queryset = DoctorAvailability.objects.select_related(
            'doctor', 'doctor__profile', 'doctor__doctor_profile'
        )
        user = getattr(self.request, 'user', None)
        if not user or not user.is_authenticated:
            return queryset.none()
        if user.role == 'admin':
            return queryset
        if user.role == 'doctor':
            return queryset.filter(doctor=user)
        if user.role == 'patient':
            return queryset.filter(is_active=True)
        return queryset.none()

    def perform_create(self, serializer):
        if self.request.user.role == 'doctor':
            serializer.save(doctor=self.request.user)
        else:
            serializer.save()
