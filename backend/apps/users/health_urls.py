"""
Health check endpoints.
"""
from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.db import connection
from django.core.cache import cache
import redis
from django.conf import settings


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Basic health check endpoint."""
    return Response({
        'status': 'healthy',
        'service': 'telemedicine-backend'
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def database_health_check(request):
    """Database connectivity health check."""
    try:
        connection.ensure_connection()
        return Response({
            'status': 'healthy',
            'database': 'connected'
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e)
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(['GET'])
@permission_classes([AllowAny])
def redis_health_check(request):
    """Redis connectivity health check."""
    try:
        cache.set('health_check', 'ok', 10)
        value = cache.get('health_check')
        if value == 'ok':
            return Response({
                'status': 'healthy',
                'redis': 'connected'
            }, status=status.HTTP_200_OK)
        else:
            raise Exception('Redis value mismatch')
    except Exception as e:
        return Response({
            'status': 'unhealthy',
            'redis': 'disconnected',
            'error': str(e)
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)


urlpatterns = [
    path('', health_check, name='health-check'),
    path('db/', database_health_check, name='database-health-check'),
    path('redis/', redis_health_check, name='redis-health-check'),
]
