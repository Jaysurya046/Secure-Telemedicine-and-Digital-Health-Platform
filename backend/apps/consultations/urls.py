"""Consultations app URLs."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ConsultationViewSet

router = DefaultRouter()
router.register(r'', ConsultationViewSet, basename='consultation')

urlpatterns = [
    path('', include(router.urls)),
]
