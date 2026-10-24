"""Permissions for appointments app."""
from rest_framework import permissions


class AppointmentAccessPermission(permissions.BasePermission):
    """
    Permission class for appointments:
    - Denies unauthenticated callers (handled by IsAuthenticated, 401).
    - Denies unsupported roles (403).
    - Preserves participant-scoped access:
        - Admins: full access.
        - Doctors: only their assigned appointments.
        - Patients: only their assigned appointments.
    """

    SUPPORTED_ROLES = {'patient', 'doctor', 'admin'}

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        role = getattr(request.user, 'role', None)
        if role not in self.SUPPORTED_ROLES:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_authenticated):
            return False
        role = getattr(request.user, 'role', None)
        if role not in self.SUPPORTED_ROLES:
            return False
        if role == 'admin':
            return True
        if role == 'doctor':
            return getattr(obj, 'doctor_id', None) == request.user.id
        if role == 'patient':
            return getattr(obj, 'patient_id', None) == request.user.id
        return False


class DoctorAvailabilityAccessPermission(permissions.BasePermission):
    """
    Permission class for doctor availability:
    - Denies unauthenticated callers (401 via IsAuthenticated).
    - Denies unsupported roles (403). Supported roles: doctor, admin, patient.
    - Patients: read-only access (SAFE_METHODS). Write requests return 403.
    - Doctors: can manage only their own availability.
    - Admins: full access to manage all availability.
    """

    SUPPORTED_ROLES = {'doctor', 'admin', 'patient'}
    message = 'Only doctors or admins can manage availability.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        role = getattr(request.user, 'role', None)
        if role not in self.SUPPORTED_ROLES:
            return False
        if role == 'patient' and request.method not in permissions.SAFE_METHODS:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_authenticated):
            return False
        role = getattr(request.user, 'role', None)
        if role not in self.SUPPORTED_ROLES:
            return False
        if role == 'admin':
            return True
        if role == 'doctor':
            return obj.doctor_id == request.user.id
        if role == 'patient':
            if request.method not in permissions.SAFE_METHODS:
                return False
            return obj.is_active
        return False
