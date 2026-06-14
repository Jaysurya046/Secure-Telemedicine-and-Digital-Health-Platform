"""Views for appointment scheduling."""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from .models import Appointment, DoctorAvailability
from .serializers import AppointmentSerializer, DoctorAvailabilitySerializer


class AppointmentViewSet(viewsets.ModelViewSet):
    serializer_class = AppointmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['status', 'doctor', 'patient']
    ordering_fields = ['scheduled_start', 'created_at']
    ordering = ['scheduled_start']
    search_fields = ['reason', 'notes', 'doctor__email', 'patient__email']

    def get_queryset(self):
        user = self.request.user
        queryset = Appointment.objects.select_related(
            'patient', 'patient__profile', 'doctor', 'doctor__profile', 'doctor__doctor_profile'
        )
        if user.role == 'admin':
            return queryset
        if user.role == 'doctor':
            return queryset.filter(doctor=user)
        return queryset.filter(patient=user)

    def perform_create(self, serializer):
        if self.request.user.role == 'patient':
            serializer.save(patient=self.request.user)
        elif self.request.user.role == 'doctor':
            serializer.save(doctor=self.request.user)
        else:
            serializer.save()

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        appointment = self.get_object()
        if request.user.role not in ['doctor', 'admin']:
            return Response({'error': 'Only doctors or admins can confirm appointments.'}, status=status.HTTP_403_FORBIDDEN)
        appointment.status = 'confirmed'
        appointment.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(appointment).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        appointment = self.get_object()
        appointment.status = 'cancelled'
        appointment.cancellation_reason = request.data.get('cancellation_reason', '')
        appointment.save(update_fields=['status', 'cancellation_reason', 'updated_at'])
        return Response(self.get_serializer(appointment).data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        appointment = self.get_object()
        if request.user.role not in ['doctor', 'admin']:
            return Response({'error': 'Only doctors or admins can complete appointments.'}, status=status.HTTP_403_FORBIDDEN)
        appointment.status = 'completed'
        appointment.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(appointment).data)


class DoctorAvailabilityViewSet(viewsets.ModelViewSet):
    serializer_class = DoctorAvailabilitySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['doctor', 'weekday', 'is_active']
    ordering_fields = ['weekday', 'start_time']
    ordering = ['weekday', 'start_time']

    def get_queryset(self):
        queryset = DoctorAvailability.objects.select_related(
            'doctor', 'doctor__profile', 'doctor__doctor_profile'
        )
        if self.request.user.role == 'doctor':
            return queryset.filter(doctor=self.request.user)
        return queryset.filter(is_active=True)

    def perform_create(self, serializer):
        if self.request.user.role == 'doctor':
            serializer.save(doctor=self.request.user)
        else:
            serializer.save()

    def create(self, request, *args, **kwargs):
        if request.user.role not in ['doctor', 'admin']:
            return Response({'error': 'Only doctors or admins can manage availability.'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if request.user.role not in ['doctor', 'admin']:
            return Response({'error': 'Only doctors or admins can manage availability.'}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if request.user.role not in ['doctor', 'admin']:
            return Response({'error': 'Only doctors or admins can manage availability.'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)
