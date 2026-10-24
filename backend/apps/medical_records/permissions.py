"""
Custom permissions for medical records and prescriptions.
"""
from rest_framework import permissions


class ClinicalRecordPermission(permissions.BasePermission):
    """
    Reusable permission for clinical records and prescriptions.
    
    Required behavior:
    - Patients:
        - Safe methods (GET, HEAD, OPTIONS) permitted on their own objects.
        - Write methods (POST, PUT, PATCH, DELETE) and custom actions (e.g., cancel) denied.
    - Doctors:
        - Access and modify only objects assigned to them.
    - Application Admins:
        - Retain full access (read and write).
    - Unauthenticated users and unsupported roles:
        - Denied access.
    """

    SUPPORTED_ROLES = {'patient', 'doctor', 'admin'}

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        role = getattr(request.user, 'role', None)
        if role not in self.SUPPORTED_ROLES:
            return False

        if role == 'admin':
            return True

        if role == 'doctor':
            return True

        if role == 'patient':
            return request.method in permissions.SAFE_METHODS

        return False

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        role = getattr(request.user, 'role', None)
        if role not in self.SUPPORTED_ROLES:
            return False

        if role == 'admin':
            return True

        if role == 'doctor':
            # Doctors can access and modify only objects assigned to them
            return getattr(obj, 'doctor_id', None) == getattr(request.user, 'id', None)

        if role == 'patient':
            # Patients can only read their own objects
            if request.method not in permissions.SAFE_METHODS:
                return False
            return getattr(obj, 'patient_id', None) == getattr(request.user, 'id', None)

        return False


# Reusable aliases for semantic clarity
ClinicalDataPermission = ClinicalRecordPermission
IsClinicalStaffOrPatientReadOnly = ClinicalRecordPermission
