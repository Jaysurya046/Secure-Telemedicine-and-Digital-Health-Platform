"""
Admin configuration for User app.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from .models import UserProfile, DoctorProfile, PatientMedicalInfo, TwoFactorAuth

User = get_user_model()


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'


class DoctorProfileInline(admin.StackedInline):
    model = DoctorProfile
    can_delete = False
    verbose_name_plural = 'Doctor Profile'


class PatientMedicalInfoInline(admin.StackedInline):
    model = PatientMedicalInfo
    can_delete = False
    verbose_name_plural = 'Medical Information'


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom User admin."""
    
    list_display = ['email', 'role', 'is_active', 'is_verified', 'created_at']
    list_filter = ['role', 'is_active', 'is_verified', 'created_at']
    search_fields = ['email', 'profile__first_name', 'profile__last_name']
    ordering = ['-created_at']
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Permissions', {'fields': ('role', 'is_active', 'is_verified', 'is_staff', 'is_superuser')}),
        ('Important dates', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'role'),
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at', 'last_login']
    
    def get_inline_instances(self, request, obj=None):
        if not obj:
            return list()
        
        inlines = [UserProfileInline]
        
        if obj.role == 'doctor':
            inlines.append(DoctorProfileInline)
        elif obj.role == 'patient':
            inlines.append(PatientMedicalInfoInline)
        
        return [inline(self.model, self.admin_site) for inline in inlines]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """User Profile admin."""
    
    list_display = ['full_name', 'phone', 'city', 'country']
    search_fields = ['first_name', 'last_name', 'phone', 'user__email']
    list_filter = ['gender', 'country']


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    """Doctor Profile admin."""
    
    list_display = ['user', 'specialization', 'license_number', 'is_available', 'average_rating']
    search_fields = ['user__email', 'specialization', 'license_number']
    list_filter = ['specialization', 'is_available']
    readonly_fields = ['average_rating', 'total_ratings']


@admin.register(PatientMedicalInfo)
class PatientMedicalInfoAdmin(admin.ModelAdmin):
    """Patient Medical Info admin."""
    
    list_display = ['user', 'blood_group', 'height', 'weight']
    search_fields = ['user__email', 'user__profile__first_name', 'user__profile__last_name']
    list_filter = ['blood_group']


@admin.register(TwoFactorAuth)
class TwoFactorAuthAdmin(admin.ModelAdmin):
    """Two Factor Auth admin."""
    
    list_display = ['user', 'is_enabled', 'created_at']
    search_fields = ['user__email']
    list_filter = ['is_enabled']
    readonly_fields = ['created_at', 'updated_at']
