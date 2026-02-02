"""
Serializers for User app.
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import UserProfile, DoctorProfile, PatientMedicalInfo, TwoFactorAuth

User = get_user_model()


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile."""
    
    full_name = serializers.ReadOnlyField()
    
    class Meta:
        model = UserProfile
        fields = [
            'first_name', 'last_name', 'full_name', 'phone', 
            'date_of_birth', 'gender', 'address', 'city', 
            'state', 'country', 'postal_code', 'avatar'
        ]


class DoctorProfileSerializer(serializers.ModelSerializer):
    """Serializer for doctor profile."""
    
    class Meta:
        model = DoctorProfile
        fields = [
            'specialization', 'license_number', 'years_of_experience',
            'consultation_fee', 'bio', 'education', 'certifications',
            'languages', 'is_available', 'consultation_duration',
            'average_rating', 'total_ratings'
        ]
        read_only_fields = ['average_rating', 'total_ratings']


class PatientMedicalInfoSerializer(serializers.ModelSerializer):
    """Serializer for patient medical information."""
    
    class Meta:
        model = PatientMedicalInfo
        fields = [
            'blood_group', 'height', 'weight', 'allergies',
            'chronic_conditions', 'current_medications',
            'emergency_contact_name', 'emergency_contact_phone',
            'emergency_contact_relation'
        ]


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user."""
    
    profile = UserProfileSerializer(required=False)
    doctor_profile = DoctorProfileSerializer(required=False, read_only=True)
    medical_info = PatientMedicalInfoSerializer(required=False, read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'role', 'is_active', 'is_verified',
            'created_at', 'profile', 'doctor_profile', 'medical_info'
        ]
        read_only_fields = ['id', 'created_at', 'is_verified']


class RegisterSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""
    
    password = serializers.CharField(
        write_only=True, 
        required=True, 
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True, 
        required=True,
        style={'input_type': 'password'}
    )
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    
    class Meta:
        model = User
        fields = [
            'email', 'password', 'password_confirm', 'role',
            'first_name', 'last_name', 'phone'
        ]
    
    def validate(self, attrs):
        """Validate password confirmation."""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                "password": "Password fields didn't match."
            })
        return attrs
    
    def validate_role(self, value):
        """Validate role - only patients can self-register."""
        if value not in ['patient', 'doctor']:
            raise serializers.ValidationError(
                "Invalid role. Only 'patient' or 'doctor' allowed for registration."
            )
        return value
    
    def create(self, validated_data):
        """Create user with profile."""
        # Remove password_confirm and profile fields
        validated_data.pop('password_confirm')
        first_name = validated_data.pop('first_name')
        last_name = validated_data.pop('last_name')
        phone = validated_data.pop('phone', '')
        
        # Create user
        user = User.objects.create_user(**validated_data)
        
        # Create profile
        UserProfile.objects.create(
            user=user,
            first_name=first_name,
            last_name=last_name,
            phone=phone
        )
        
        # Create medical info for patients
        if user.role == 'patient':
            PatientMedicalInfo.objects.create(user=user)
        
        return user


class LoginSerializer(serializers.Serializer):
    """Serializer for user login."""
    
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'}
    )


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change."""
    
    old_password = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'}
    )
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    new_password_confirm = serializers.CharField(
        required=True,
        write_only=True,
        style={'input_type': 'password'}
    )
    
    def validate(self, attrs):
        """Validate new password confirmation."""
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({
                "new_password": "Password fields didn't match."
            })
        return attrs


class DoctorListSerializer(serializers.ModelSerializer):
    """Serializer for listing doctors."""
    
    profile = UserProfileSerializer(read_only=True)
    doctor_profile = DoctorProfileSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'email', 'profile', 'doctor_profile', 'is_active']


class DoctorDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for doctor information."""
    
    profile = UserProfileSerializer(read_only=True)
    doctor_profile = DoctorProfileSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'profile', 'doctor_profile',
            'is_active', 'created_at'
        ]


class PatientListSerializer(serializers.ModelSerializer):
    """Serializer for listing patients."""
    
    profile = UserProfileSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'email', 'profile', 'is_active', 'created_at']


class PatientDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for patient information."""
    
    profile = UserProfileSerializer(read_only=True)
    medical_info = PatientMedicalInfoSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'profile', 'medical_info',
            'is_active', 'created_at'
        ]


class UpdateProfileSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile."""
    
    class Meta:
        model = UserProfile
        fields = [
            'first_name', 'last_name', 'phone', 'date_of_birth',
            'gender', 'address', 'city', 'state', 'country',
            'postal_code', 'avatar'
        ]


class UpdateDoctorProfileSerializer(serializers.ModelSerializer):
    """Serializer for updating doctor profile."""
    
    class Meta:
        model = DoctorProfile
        fields = [
            'specialization', 'years_of_experience', 'consultation_fee',
            'bio', 'education', 'certifications', 'languages',
            'is_available', 'consultation_duration'
        ]
        read_only_fields = ['license_number']


class UpdateMedicalInfoSerializer(serializers.ModelSerializer):
    """Serializer for updating patient medical information."""
    
    class Meta:
        model = PatientMedicalInfo
        fields = [
            'blood_group', 'height', 'weight', 'allergies',
            'chronic_conditions', 'current_medications',
            'emergency_contact_name', 'emergency_contact_phone',
            'emergency_contact_relation'
        ]
