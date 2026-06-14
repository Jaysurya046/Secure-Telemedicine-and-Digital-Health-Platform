"""Medical records app URLs."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import MedicalDocumentViewSet, MedicalRecordViewSet, PrescriptionViewSet

router = DefaultRouter()
router.register(r'prescriptions', PrescriptionViewSet, basename='prescription')
router.register(r'documents', MedicalDocumentViewSet, basename='medical-document')
router.register(r'', MedicalRecordViewSet, basename='medical-record')

urlpatterns = [
    path('', include(router.urls)),
]
