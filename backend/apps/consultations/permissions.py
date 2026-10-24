"""Permissions for consultations app."""
from rest_framework import permissions


class ConsultationAccessPermission(permissions.BasePermission):
    """
    Permission class for consultations.
    - Unauthenticated: handled by IsAuthenticated (401)
    - Unsupported roles: denied (403)
    - Patients: permitted for list, retrieve, create (Feature 3D), messages;
      denied for update, partial_update, destroy, start, end (403)
    - Doctors: permitted for their assigned consultations
    - Admins: permitted
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role not in ['patient', 'doctor', 'admin']:
            return False
        # Patients cannot update, partial_update, destroy, start, or end
        if request.user.role == 'patient' and view.action in ['update', 'partial_update', 'destroy', 'start', 'end']:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role == 'admin':
            return True
        if user.role == 'doctor':
            return obj.doctor_id == user.id
        if user.role == 'patient':
            if view.action in ['update', 'partial_update', 'destroy', 'start', 'end']:
                return False
            return obj.patient_id == user.id
        return False
