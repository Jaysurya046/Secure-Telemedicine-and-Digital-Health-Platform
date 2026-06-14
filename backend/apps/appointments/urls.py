"""Appointments app URLs."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AppointmentViewSet, DoctorAvailabilityViewSet

router = DefaultRouter()
router.register(r'availability', DoctorAvailabilityViewSet, basename='doctor-availability')
router.register(r'', AppointmentViewSet, basename='appointment')

urlpatterns = [
    path('', include(router.urls)),
]
