"""Permissions for consultations app."""
from rest_framework import permissions


class ConsultationAccessPermission(permissions.BasePermission):
    """
    Permission class for consultations.
    - Unauthenticated: handled by IsAuthenticated (401)
    - Unsupported roles: denied (403)
    - Patient, Doctor, Admin: allowed
    """

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ['patient', 'doctor', 'admin']
        )
