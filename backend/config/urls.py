"""
URL configuration for Telemedicine Platform.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from rest_framework import routers

# API Router
router = routers.DefaultRouter()

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # API Endpoints
    path('api/', include(router.urls)),
    path('api/auth/', include('apps.users.urls')),
    path('api/appointments/', include('apps.appointments.urls')),
    path('api/consultations/', include('apps.consultations.urls')),
    path('api/medical-records/', include('apps.medical_records.urls')),
    path('api/audit/', include('apps.audit.urls')),
    
    # Health Check
    path('health/', include('apps.users.health_urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    # Debug Toolbar
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns

# Customize admin site
admin.site.site_header = "Telemedicine Platform Administration"
admin.site.site_title = "Telemedicine Admin"
admin.site.index_title = "Welcome to Telemedicine Platform Admin"
