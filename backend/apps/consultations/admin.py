"""Admin for consultations."""
from django.contrib import admin

from .models import Consultation, ConsultationMessage


class ConsultationMessageInline(admin.TabularInline):
    model = ConsultationMessage
    extra = 0
    readonly_fields = ['sent_at']


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ['id', 'patient', 'doctor', 'status', 'started_at', 'ended_at']
    list_filter = ['status', 'created_at']
    search_fields = ['patient__email', 'doctor__email', 'chief_complaint', 'diagnosis']
    readonly_fields = ['room_id', 'created_at', 'updated_at']
    inlines = [ConsultationMessageInline]


@admin.register(ConsultationMessage)
class ConsultationMessageAdmin(admin.ModelAdmin):
    list_display = ['consultation', 'sender', 'sent_at']
    search_fields = ['sender__email', 'message']
    readonly_fields = ['sent_at']
