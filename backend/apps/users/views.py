"""
Views for User app - Authentication and User Management.
"""
from rest_framework import status, generics, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.contrib.auth import get_user_model, authenticate
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters

from .models import UserProfile, DoctorProfile, PatientMedicalInfo
from .serializers import (
    UserSerializer, RegisterSerializer, LoginSerializer,
    ChangePasswordSerializer, DoctorListSerializer, DoctorDetailSerializer,
    PatientListSerializer, PatientDetailSerializer, UpdateProfileSerializer,
    UpdateDoctorProfileSerializer, UpdateMedicalInfoSerializer
)
from .permissions import IsOwnerOrAdmin, IsDoctorOrAdmin, IsPatientOrAdmin

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """
    User registration endpoint.
    Allows patients and doctors to register.
    """
    queryset = User.objects.all()
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer
    
    @extend_schema(
        summary="Register a new user",
        description="Create a new user account (patient or doctor)",
        tags=["Authentication"]
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            user = serializer.save()
        
        # Generate tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'user': UserSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
            'message': 'Registration successful'
        }, status=status.HTTP_201_CREATED)


class LoginView(generics.GenericAPIView):
    """
    User login endpoint.
    Returns JWT tokens on successful authentication.
    """
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer
    
    @extend_schema(
        summary="User login",
        description="Authenticate user and return JWT tokens",
        tags=["Authentication"]
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        
        user = authenticate(request, username=email, password=password)
        
        if user is None:
            return Response({
                'error': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        if not user.is_active:
            return Response({
                'error': 'Account is inactive'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Generate tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'user': UserSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
            'message': 'Login successful'
        }, status=status.HTTP_200_OK)


class LogoutView(generics.GenericAPIView):
    """
    User logout endpoint.
    Blacklists the refresh token.
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        summary="User logout",
        description="Logout user and blacklist refresh token",
        tags=["Authentication"]
    )
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response({
                    'error': 'Refresh token is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            token = RefreshToken(refresh_token)
            token.blacklist()
            
            return Response({
                'message': 'Logout successful'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(generics.UpdateAPIView):
    """
    Change password endpoint.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer
    
    @extend_schema(
        summary="Change password",
        description="Change user password",
        tags=["User Management"]
    )
    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = request.user
        
        # Check old password
        if not user.check_password(serializer.validated_data['old_password']):
            return Response({
                'error': 'Old password is incorrect'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Set new password
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        return Response({
            'message': 'Password changed successfully'
        }, status=status.HTTP_200_OK)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    Get and update user profile.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer
    
    def get_object(self):
        return self.request.user
    
    @extend_schema(
        summary="Get current user profile",
        description="Retrieve authenticated user's profile",
        tags=["User Management"]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
    
    @extend_schema(
        summary="Update current user profile",
        description="Update authenticated user's profile",
        tags=["User Management"]
    )
    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        
        # Update user profile
        if 'profile' in request.data:
            profile_serializer = UpdateProfileSerializer(
                user.profile,
                data=request.data['profile'],
                partial=True
            )
            if profile_serializer.is_valid(raise_exception=True):
                profile_serializer.save()
        
        # Update doctor profile if doctor
        if user.is_doctor and 'doctor_profile' in request.data:
            doctor_profile_serializer = UpdateDoctorProfileSerializer(
                user.doctor_profile,
                data=request.data['doctor_profile'],
                partial=True
            )
            if doctor_profile_serializer.is_valid(raise_exception=True):
                doctor_profile_serializer.save()
        
        # Update medical info if patient
        if user.is_patient and 'medical_info' in request.data:
            medical_info_serializer = UpdateMedicalInfoSerializer(
                user.medical_info,
                data=request.data['medical_info'],
                partial=True
            )
            if medical_info_serializer.is_valid(raise_exception=True):
                medical_info_serializer.save()
        
        return Response(UserSerializer(user).data)


class DoctorViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing and retrieving doctors.
    """
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['doctor_profile__specialization', 'doctor_profile__is_available']
    search_fields = ['profile__first_name', 'profile__last_name', 'doctor_profile__specialization']
    ordering_fields = ['doctor_profile__average_rating', 'doctor_profile__consultation_fee']
    ordering = ['-doctor_profile__average_rating']
    
    def get_queryset(self):
        return User.objects.filter(
            role='doctor',
            is_active=True
        ).select_related('profile', 'doctor_profile')
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return DoctorDetailSerializer
        return DoctorListSerializer
    
    @extend_schema(
        summary="List all doctors",
        description="Get a list of all active doctors with filtering and search",
        tags=["Doctors"]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary="Get doctor details",
        description="Retrieve detailed information about a specific doctor",
        tags=["Doctors"]
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    @action(detail=True, methods=['get'])
    @extend_schema(
        summary="Get doctor availability",
        description="Get doctor's availability schedule",
        tags=["Doctors"]
    )
    def availability(self, request, pk=None):
        doctor = self.get_object()
        # This will be implemented when we create the appointments app
        return Response({
            'doctor_id': str(doctor.id),
            'is_available': doctor.doctor_profile.is_available,
            'consultation_duration': doctor.doctor_profile.consultation_duration,
            'message': 'Availability endpoint - to be fully implemented with appointments app'
        })


class PatientViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing and retrieving patients.
    Only accessible by doctors and admins.
    """
    permission_classes = [IsAuthenticated, IsDoctorOrAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['profile__first_name', 'profile__last_name', 'email']
    
    def get_queryset(self):
        user = self.request.user
        queryset = User.objects.filter(
            role='patient',
            is_active=True
        ).select_related('profile', 'medical_info')
        
        # Doctors can only see their patients
        if user.is_doctor:
            # This will be filtered based on appointments when that app is created
            # For now, return all patients
            pass
        
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PatientDetailSerializer
        return PatientListSerializer
    
    @extend_schema(
        summary="List patients",
        description="Get a list of patients (doctors see their patients, admins see all)",
        tags=["Patients"]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary="Get patient details",
        description="Retrieve detailed information about a specific patient",
        tags=["Patients"]
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


@api_view(['GET'])
@permission_classes([AllowAny])
@extend_schema(
    summary="Get user statistics",
    description="Get platform statistics (public endpoint)",
    tags=["Statistics"]
)
def statistics_view(request):
    """Public statistics endpoint."""
    total_doctors = User.objects.filter(role='doctor', is_active=True).count()
    total_patients = User.objects.filter(role='patient', is_active=True).count()
    
    return Response({
        'total_doctors': total_doctors,
        'total_patients': total_patients,
        'specializations': DoctorProfile.objects.values_list(
            'specialization', flat=True
        ).distinct().count()
    })
