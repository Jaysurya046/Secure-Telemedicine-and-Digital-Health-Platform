"""
Custom permissions for Telemedicine Platform.
"""
from rest_framework import permissions


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Permission to only allow owners of an object or admins to access it.
    """
    
    def has_object_permission(self, request, view, obj):
        # Admins have full access
        if request.user.role == 'admin':
            return True
        
        # Check if object has a user attribute
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        # Check if object is the user itself
        return obj == request.user


class IsDoctorOrAdmin(permissions.BasePermission):
    """
    Permission to only allow doctors or admins.
    """
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.role in ['doctor', 'admin']
        )


class IsPatientOrAdmin(permissions.BasePermission):
    """
    Permission to only allow patients or admins.
    """
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.role in ['patient', 'admin']
        )


class IsDoctor(permissions.BasePermission):
    """
    Permission to only allow doctors.
    """
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'doctor'


class IsPatient(permissions.BasePermission):
    """
    Permission to only allow patients.
    """
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'patient'


class IsAdmin(permissions.BasePermission):
    """
    Permission to only allow admins.
    """
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'


class ReadOnly(permissions.BasePermission):
    """
    Permission to only allow read-only access.
    """
    
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS
