"""Audit middleware."""
from django.utils.deprecation import MiddlewareMixin

from .models import AuditLog


class AuditMiddleware(MiddlewareMixin):
    """Record access to sensitive API paths and all mutating API requests."""

    SENSITIVE_PREFIXES = (
        '/api/medical-records/',
        '/api/consultations/',
        '/api/appointments/',
    )

    def process_response(self, request, response):
        if not request.path.startswith('/api/'):
            return response

        should_log = request.method in ['POST', 'PUT', 'PATCH', 'DELETE'] or request.path.startswith(self.SENSITIVE_PREFIXES)
        if not should_log:
            return response

        user = getattr(request, 'user', None)
        action = self._action_for_method(request.method)
        try:
            AuditLog.objects.create(
                user=user if getattr(user, 'is_authenticated', False) else None,
                action=action,
                resource_type=self._resource_type(request.path),
                path=request.path[:255],
                method=request.method,
                status_code=response.status_code,
                ip_address=self._client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:1000],
            )
        except Exception:
            pass
        return response

    def _action_for_method(self, method):
        return {
            'GET': 'read',
            'POST': 'create',
            'PUT': 'update',
            'PATCH': 'update',
            'DELETE': 'delete',
        }.get(method, 'system')

    def _resource_type(self, path):
        parts = [part for part in path.split('/') if part]
        return parts[1] if len(parts) > 1 else ''

    def _client_ip(self, request):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded:
            return forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
