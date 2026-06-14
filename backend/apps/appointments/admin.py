"""Admin for appointments."""
from django.contrib import admin

from .models import Appointment, DoctorAvailability


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['patient', 'doctor', 'scheduled_start', 'scheduled_end', 'status']
    list_filter = ['status', 'scheduled_start']
    search_fields = ['patient__email', 'doctor__email', 'reason']
    date_hierarchy = 'scheduled_start'


@admin.register(DoctorAvailability)
class DoctorAvailabilityAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'weekday', 'start_time', 'end_time', 'is_active']
    list_filter = ['weekday', 'is_active']
    search_fields = ['doctor__email']
