"""
Tests for apps.users authentication and profile access control.
"""
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils.module_loading import import_string
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.throttling import AnonRateThrottle
from apps.users.models import UserProfile, DoctorProfile, PatientMedicalInfo
from apps.users.serializers import UserSerializer
from django_redis.pool import ConnectionFactory
from redis.connection import BaseParser
import datetime
from django.utils import timezone
from apps.appointments.models import Appointment
from apps.consultations.models import Consultation
import redis
import config.settings as prod_settings

User = get_user_model()


class UserProfileAccessControlTests(APITestCase):
    """
    Regression and security tests for UserProfileView and public registration.
    Covers:
    - PUT /api/auth/profile/ unsupported (returns 405) and prevents role escalation.
    - PATCH privilege-change attempts for patient and doctor are rejected / ignored.
    - Profile writes never alter role, is_active, is_staff, is_superuser, or is_verified.
    - Anonymous access to profile endpoints is rejected with 401 Unauthorized.
    - Legitimate nested profile updates for patient and doctor succeed.
    - Atomic rollback: invalid nested data prevents partial saves of valid fields.
    - Role boundary protections: patient cannot update doctor_profile.
    - Public registration strictly rejects the admin role.
    """

    def setUp(self):
        self.patient = User.objects.create_user(
            email='patient@example.com',
            password='Password123!@#',
            role='patient'
        )
        self.patient_profile = UserProfile.objects.create(
            user=self.patient,
            first_name='PatientFirst',
            last_name='PatientLast',
            phone='+1234567890',
            city='New York'
        )
        self.patient_medical = PatientMedicalInfo.objects.create(
            user=self.patient,
            blood_group='O+',
            allergies=['Penicillin']
        )

        self.doctor = User.objects.create_user(
            email='doctor@example.com',
            password='Password123!@#',
            role='doctor'
        )
        self.doctor_profile = UserProfile.objects.create(
            user=self.doctor,
            first_name='DoctorFirst',
            last_name='DoctorLast',
            phone='+1987654321',
            city='Boston'
        )
        self.doctor_details = DoctorProfile.objects.create(
            user=self.doctor,
            specialization='Cardiology',
            license_number='LIC-12345',
            years_of_experience=8,
            consultation_fee=150.00
        )

        self.profile_url = reverse('user-profile')
        self.register_url = reverse('register')

    # -------------------------------------------------------------------------
    # PUT Unsupported & Role Escalation Regression Tests
    # -------------------------------------------------------------------------

    def test_put_profile_unsupported_returns_405_and_prevents_role_escalation(self):
        """
        Regression: PUT /api/auth/profile/ must return 405 Method Not Allowed
        and cannot escalate a patient's role to admin.
        """
        self.client.force_authenticate(user=self.patient)
        payload = {
            'email': self.patient.email,
            'role': 'admin',
        }
        response = self.client.put(self.profile_url, payload, format='json')

        self.patient.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.patient.role, 'patient')
        self.assertFalse(self.patient.is_staff)
        self.assertFalse(self.patient.is_superuser)

    def test_put_profile_doctor_unsupported_returns_405(self):
        """
        Doctor cannot escalate role or update profile via PUT (must return 405).
        """
        self.client.force_authenticate(user=self.doctor)
        payload = {
            'email': self.doctor.email,
            'role': 'admin',
        }
        response = self.client.put(self.profile_url, payload, format='json')

        self.doctor.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.doctor.role, 'doctor')

    # -------------------------------------------------------------------------
    # Privilege-Change Attempts via PATCH
    # -------------------------------------------------------------------------

    def test_patch_profile_patient_privilege_change_attempts_ignored(self):
        """
        Profile writes must never change role, is_active, is_staff, is_superuser, or is_verified.
        """
        self.client.force_authenticate(user=self.patient)
        payload = {
            'role': 'admin',
            'is_staff': True,
            'is_superuser': True,
            'is_active': False,
            'is_verified': True,
            'profile': {
                'first_name': 'UpdatedFirst'
            }
        }
        response = self.client.patch(self.profile_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.patient.refresh_from_db()
        self.patient_profile.refresh_from_db()

        # Legitimate profile change was applied
        self.assertEqual(self.patient_profile.first_name, 'UpdatedFirst')
        # Account security fields must NEVER have changed
        self.assertEqual(self.patient.role, 'patient')
        self.assertFalse(self.patient.is_staff)
        self.assertFalse(self.patient.is_superuser)
        self.assertTrue(self.patient.is_active)
        self.assertFalse(self.patient.is_verified)

    def test_patch_profile_doctor_privilege_change_attempts_ignored(self):
        """
        Doctor privilege change attempt to admin or staff via PATCH must not take effect.
        """
        self.client.force_authenticate(user=self.doctor)
        payload = {
            'role': 'admin',
            'is_staff': True,
            'is_superuser': True,
            'profile': {
                'first_name': 'UpdatedDoctor'
            }
        }
        response = self.client.patch(self.profile_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.role, 'doctor')
        self.assertFalse(self.doctor.is_staff)
        self.assertFalse(self.doctor.is_superuser)

    # -------------------------------------------------------------------------
    # Anonymous Access Tests
    # -------------------------------------------------------------------------

    def test_anonymous_profile_get_rejected(self):
        """Unauthenticated GET to /api/auth/profile/ must return 401."""
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_anonymous_profile_patch_rejected(self):
        """Unauthenticated PATCH to /api/auth/profile/ must return 401."""
        response = self.client.patch(self.profile_url, {'profile': {'first_name': 'Hacker'}}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_anonymous_profile_put_rejected(self):
        """Unauthenticated PUT to /api/auth/profile/ must return 401."""
        response = self.client.put(self.profile_url, {'role': 'admin'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # -------------------------------------------------------------------------
    # Successful Allowed Nested Updates
    # -------------------------------------------------------------------------

    def test_patient_successful_nested_update(self):
        """
        Patient can successfully update their profile and medical info.
        """
        self.client.force_authenticate(user=self.patient)
        payload = {
            'profile': {
                'first_name': 'Jane',
                'last_name': 'Smith',
                'phone': '+15551234567',
                'city': 'Chicago',
                'gender': 'F'
            },
            'medical_info': {
                'blood_group': 'AB+',
                'allergies': ['Peanuts', 'Sulfa'],
                'emergency_contact_name': 'Bob Smith',
                'emergency_contact_phone': '+15557654321'
            }
        }
        response = self.client.patch(self.profile_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.patient_profile.refresh_from_db()
        self.patient_medical.refresh_from_db()

        self.assertEqual(self.patient_profile.first_name, 'Jane')
        self.assertEqual(self.patient_profile.last_name, 'Smith')
        self.assertEqual(self.patient_profile.phone, '+15551234567')
        self.assertEqual(self.patient_profile.city, 'Chicago')
        self.assertEqual(self.patient_profile.gender, 'F')

        self.assertEqual(self.patient_medical.blood_group, 'AB+')
        self.assertEqual(self.patient_medical.allergies, ['Peanuts', 'Sulfa'])
        self.assertEqual(self.patient_medical.emergency_contact_name, 'Bob Smith')

        # Check response structure
        self.assertEqual(response.data['profile']['first_name'], 'Jane')
        self.assertEqual(response.data['medical_info']['blood_group'], 'AB+')

    def test_doctor_successful_nested_update(self):
        """
        Doctor can successfully update their profile and doctor profile details.
        """
        self.client.force_authenticate(user=self.doctor)
        payload = {
            'profile': {
                'first_name': 'Gregory',
                'last_name': 'House',
                'phone': '+15559876543',
                'city': 'Princeton'
            },
            'doctor_profile': {
                'specialization': 'Diagnostic Medicine',
                'years_of_experience': 20,
                'consultation_fee': '350.00',
                'bio': 'Board-certified diagnostician.'
            }
        }
        response = self.client.patch(self.profile_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.doctor_profile.refresh_from_db()
        self.doctor_details.refresh_from_db()

        self.assertEqual(self.doctor_profile.first_name, 'Gregory')
        self.assertEqual(self.doctor_profile.city, 'Princeton')
        self.assertEqual(self.doctor_details.specialization, 'Diagnostic Medicine')
        self.assertEqual(self.doctor_details.years_of_experience, 20)
        self.assertEqual(float(self.doctor_details.consultation_fee), 350.00)
        self.assertEqual(self.doctor_details.bio, 'Board-certified diagnostician.')

    # -------------------------------------------------------------------------
    # Atomic Rollback / No Partial Updates on Validation Error
    # -------------------------------------------------------------------------

    def test_patient_invalid_nested_data_prevents_partial_save(self):
        """
        If profile data is valid but medical_info has invalid input (e.g. invalid blood group),
        the request must return 400 and NO changes must be saved to the profile.
        """
        self.client.force_authenticate(user=self.patient)
        payload = {
            'profile': {
                'first_name': 'ShouldNotPersist',
                'city': 'Miami'
            },
            'medical_info': {
                'blood_group': 'INVALID_CHOICE'  # Invalid choice for choices field
            }
        }
        response = self.client.patch(self.profile_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.patient_profile.refresh_from_db()
        self.patient_medical.refresh_from_db()

        # Database must NOT be partially updated
        self.assertEqual(self.patient_profile.first_name, 'PatientFirst')
        self.assertEqual(self.patient_profile.city, 'New York')
        self.assertEqual(self.patient_medical.blood_group, 'O+')

    def test_doctor_invalid_nested_data_prevents_partial_save(self):
        """
        If doctor profile data has valid profile but invalid doctor_profile
        (e.g. negative years_of_experience), all changes must roll back.
        """
        self.client.force_authenticate(user=self.doctor)
        payload = {
            'profile': {
                'first_name': 'ShouldNotPersistDoc'
            },
            'doctor_profile': {
                'years_of_experience': -5  # Negative integer violates min_value=0
            }
        }
        response = self.client.patch(self.profile_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.doctor_profile.refresh_from_db()
        self.doctor_details.refresh_from_db()

        self.assertEqual(self.doctor_profile.first_name, 'DoctorFirst')
        self.assertEqual(self.doctor_details.years_of_experience, 8)

    def test_invalid_nested_types_rejected(self):
        """Non-dictionary nested payloads must return 400 Bad Request."""
        self.client.force_authenticate(user=self.patient)
        payload = {
            'profile': 'not-a-dict'
        }
        response = self.client.patch(self.profile_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -------------------------------------------------------------------------
    # Missing Related Rows Atomicity Regression Tests
    # -------------------------------------------------------------------------

    def test_missing_user_profile_and_medical_info_invalid_request_creates_no_rows(self):
        """
        When a user has no UserProfile or PatientMedicalInfo rows,
        an invalid nested request must return 400 and NOT create either row.
        """
        raw_patient = User.objects.create_user(
            email='raw_patient@example.com',
            password='Password123!@#',
            role='patient'
        )
        self.client.force_authenticate(user=raw_patient)
        payload = {
            'profile': {
                'first_name': 'ValidFirst'
            },
            'medical_info': {
                'blood_group': 'INVALID_CHOICE'
            }
        }
        response = self.client.patch(self.profile_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            UserProfile.objects.filter(user=raw_patient).exists(),
            "UserProfile row must not be persisted on invalid request"
        )
        self.assertFalse(
            PatientMedicalInfo.objects.filter(user=raw_patient).exists(),
            "PatientMedicalInfo row must not be persisted on invalid request"
        )

    def test_missing_user_profile_and_medical_info_valid_request_creates_rows(self):
        """
        When a user has no UserProfile or PatientMedicalInfo rows,
        a valid nested request must atomically create both rows.
        """
        raw_patient = User.objects.create_user(
            email='raw_patient_valid@example.com',
            password='Password123!@#',
            role='patient'
        )
        self.client.force_authenticate(user=raw_patient)
        payload = {
            'profile': {
                'first_name': 'CreatedFirst',
                'last_name': 'CreatedLast',
                'phone': '+15550001122'
            },
            'medical_info': {
                'blood_group': 'B+',
                'allergies': ['Latex']
            }
        }
        response = self.client.patch(self.profile_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(UserProfile.objects.filter(user=raw_patient).exists())
        self.assertTrue(PatientMedicalInfo.objects.filter(user=raw_patient).exists())

        profile = UserProfile.objects.get(user=raw_patient)
        medical = PatientMedicalInfo.objects.get(user=raw_patient)
        self.assertEqual(profile.first_name, 'CreatedFirst')
        self.assertEqual(profile.last_name, 'CreatedLast')
        self.assertEqual(medical.blood_group, 'B+')
        self.assertEqual(medical.allergies, ['Latex'])

    def test_missing_doctor_profile_invalid_request_creates_no_rows_and_avoids_unvalidated_defaults(self):
        """
        When a doctor has no DoctorProfile, an invalid request must return 400
        without creating a DoctorProfile row or persisting unvalidated defaults.
        """
        raw_doctor = User.objects.create_user(
            email='raw_doctor@example.com',
            password='Password123!@#',
            role='doctor'
        )
        self.client.force_authenticate(user=raw_doctor)
        payload = {
            'doctor_profile': {
                'specialization': 'UnvalidatedSpecialization',
                'years_of_experience': -99
            }
        }
        response = self.client.patch(self.profile_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            DoctorProfile.objects.filter(user=raw_doctor).exists(),
            "DoctorProfile row must not be persisted when validation fails"
        )
        self.assertFalse(
            DoctorProfile.objects.filter(specialization='UnvalidatedSpecialization').exists(),
            "Unvalidated doctor specialization must not be persisted in database"
        )

    def test_missing_doctor_profile_valid_request_creates_row(self):
        """
        When a doctor has no DoctorProfile, a valid request must atomically create the row.
        """
        raw_doctor = User.objects.create_user(
            email='raw_doctor_valid@example.com',
            password='Password123!@#',
            role='doctor'
        )
        self.client.force_authenticate(user=raw_doctor)
        payload = {
            'doctor_profile': {
                'specialization': 'Neurology',
                'years_of_experience': 12,
                'consultation_fee': '250.00'
            }
        }
        response = self.client.patch(self.profile_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(DoctorProfile.objects.filter(user=raw_doctor).exists())
        doc_profile = DoctorProfile.objects.get(user=raw_doctor)
        self.assertEqual(doc_profile.specialization, 'Neurology')
        self.assertEqual(doc_profile.years_of_experience, 12)
        self.assertEqual(float(doc_profile.consultation_fee), 250.00)

    def test_existing_profile_with_missing_medical_info_invalid_request_leaves_existing_unmodified(self):
        """
        If a user has an existing UserProfile but no PatientMedicalInfo,
        an invalid request must not modify the existing UserProfile and must not create PatientMedicalInfo.
        """
        partial_patient = User.objects.create_user(
            email='partial_patient@example.com',
            password='Password123!@#',
            role='patient'
        )
        profile = UserProfile.objects.create(
            user=partial_patient,
            first_name='ExistingFirst',
            last_name='ExistingLast'
        )
        self.client.force_authenticate(user=partial_patient)
        payload = {
            'profile': {
                'first_name': 'ShouldNotChange'
            },
            'medical_info': {
                'blood_group': 'INVALID_CHOICE'
            }
        }
        response = self.client.patch(self.profile_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        profile.refresh_from_db()
        self.assertEqual(profile.first_name, 'ExistingFirst')
        self.assertFalse(PatientMedicalInfo.objects.filter(user=partial_patient).exists())

    def test_missing_user_profile_invalid_type_creates_no_row(self):
        """
        When a user has no UserProfile, sending an invalid type for profile must return 400
        and not create a UserProfile.
        """
        raw_patient = User.objects.create_user(
            email='raw_patient_bad_type@example.com',
            password='Password123!@#',
            role='patient'
        )
        self.client.force_authenticate(user=raw_patient)
        payload = {
            'profile': 'string-not-dict'
        }
        response = self.client.patch(self.profile_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(UserProfile.objects.filter(user=raw_patient).exists())

    # -------------------------------------------------------------------------
    # Role Boundary Protection
    # -------------------------------------------------------------------------

    def test_patient_cannot_create_or_modify_doctor_profile(self):
        """
        A patient submitting doctor_profile must not have a DoctorProfile created.
        """
        self.client.force_authenticate(user=self.patient)
        payload = {
            'doctor_profile': {
                'specialization': 'Neurosurgery',
                'license_number': 'FAKE-999',
                'consultation_fee': '500.00'
            }
        }
        response = self.client.patch(self.profile_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(DoctorProfile.objects.filter(user=self.patient).exists())

    # -------------------------------------------------------------------------
    # UserSerializer Direct Protection
    # -------------------------------------------------------------------------

    def test_user_serializer_read_only_fields_cannot_be_overridden(self):
        """
        Ensure UserSerializer treats role, is_active, is_verified as read-only.
        """
        serializer = UserSerializer(
            instance=self.patient,
            data={
                'role': 'admin',
                'is_active': False,
                'is_verified': True,
                'email': 'modified@example.com'
            },
            partial=True
        )
        self.assertTrue(serializer.is_valid())
        # validated_data must NOT contain any of the read-only fields
        self.assertNotIn('role', serializer.validated_data)
        self.assertNotIn('is_active', serializer.validated_data)
        self.assertNotIn('is_verified', serializer.validated_data)
        self.assertNotIn('email', serializer.validated_data)

        updated_user = serializer.save()
        self.assertEqual(updated_user.role, 'patient')
        self.assertTrue(updated_user.is_active)
        self.assertFalse(updated_user.is_verified)
        self.assertEqual(updated_user.email, 'patient@example.com')

    # -------------------------------------------------------------------------
    # Public Registration Role Protection
    # -------------------------------------------------------------------------

    def test_public_registration_rejects_admin_role(self):
        """
        Public registration must reject attempts to register with role='admin',
        regardless of case ('admin', 'Admin', 'ADMIN').
        """
        for admin_role in ['admin', 'Admin', 'ADMIN', ' admin ']:
            payload = {
                'email': f'admin_attempt_{admin_role.strip().lower()}@example.com',
                'password': 'StrongPassword123!',
                'password_confirm': 'StrongPassword123!',
                'role': admin_role,
                'first_name': 'Fake',
                'last_name': 'Admin'
            }
            response = self.client.post(self.register_url, payload, format='json')
            self.assertEqual(
                response.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"Registration unexpectedly succeeded for role={admin_role}"
            )
            self.assertFalse(
                User.objects.filter(email=payload['email']).exists(),
                f"User was created with admin role for input {admin_role}"
            )

    def test_public_registration_cannot_set_privileged_flags(self):
        """
        Public registration must ignore is_staff, is_superuser, and is_verified.
        """
        payload = {
            'email': 'new_patient_priv@example.com',
            'password': 'StrongPassword123!',
            'password_confirm': 'StrongPassword123!',
            'role': 'patient',
            'first_name': 'Safe',
            'last_name': 'User',
            'is_staff': True,
            'is_superuser': True,
            'is_verified': True
        }
        response = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        new_user = User.objects.get(email='new_patient_priv@example.com')
        self.assertEqual(new_user.role, 'patient')
        self.assertFalse(new_user.is_staff)
        self.assertFalse(new_user.is_superuser)
        self.assertFalse(new_user.is_verified)

    def test_public_registration_allowed_patient(self):
        """Patient registration succeeds with legitimate data."""
        payload = {
            'email': 'valid_patient@example.com',
            'password': 'StrongPassword123!',
            'password_confirm': 'StrongPassword123!',
            'role': 'patient',
            'first_name': 'Alice',
            'last_name': 'Wonder',
            'phone': '+15554443322'
        }
        response = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email='valid_patient@example.com', role='patient').exists())
        self.assertTrue(PatientMedicalInfo.objects.filter(user__email='valid_patient@example.com').exists())

    def test_public_registration_allowed_doctor(self):
        """Doctor registration succeeds with legitimate data and creates DoctorProfile."""
        payload = {
            'email': 'valid_doctor@example.com',
            'password': 'StrongPassword123!',
            'password_confirm': 'StrongPassword123!',
            'role': 'doctor',
            'first_name': 'Robert',
            'last_name': 'Smith',
            'specialization': 'Pediatrics',
            'license_number': 'LIC-998877',
            'years_of_experience': 5,
            'consultation_fee': '120.00'
        }
        response = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        doc = User.objects.get(email='valid_doctor@example.com')
        self.assertEqual(doc.role, 'doctor')
        self.assertTrue(DoctorProfile.objects.filter(user=doc, specialization='Pediatrics').exists())


def _get_sanitized_redis_url(raw_url: str) -> str:
    """Strip authentication credentials from Redis URL for safe diagnostics."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(raw_url)
        scheme = parsed.scheme or 'redis'
        host = parsed.hostname or 'localhost'
        port_part = f":{parsed.port}" if parsed.port else ""
        path = parsed.path or "/0"
        return f"{scheme}://{host}{port_part}{path}"
    except Exception:
        return "redis://localhost:6379/0"


class RedisCacheCompatibilityTests(APITestCase):
    """
    Step 2A regression tests for Redis cache compatibility.
    Verifies that:
    - Production CACHES configuration uses a supported parser (DefaultParser).
    - Initializing the cache client, connection factory, and connection pool
      succeeds without throwing ImportError (which occurred with HiredisParser)
      and without requiring a running Redis server.
    - If a live Redis server is running, verifies cache set/get and an actual DRF
      request sequence reaching HTTP 429 using a Redis-backed test cache with unique prefix.
    - If live Redis is not available, clearly reports the skipped live checks without exposing credentials.
    """

    def test_production_cache_config_uses_supported_default_parser(self):
        """
        Verify that production CACHES defines a supported PARSER_CLASS and backend.
        """
        default_cache_cfg = prod_settings.CACHES['default']
        self.assertEqual(default_cache_cfg['BACKEND'], 'django_redis.cache.RedisCache')
        parser_class_name = default_cache_cfg['OPTIONS'].get('PARSER_CLASS')
        self.assertEqual(
            parser_class_name,
            'redis.connection.DefaultParser',
            "Production CACHES must configure 'redis.connection.DefaultParser'"
        )

    def test_client_factory_and_parser_initialize_without_redis_server(self):
        """
        Regression test: ConnectionFactory and parser initialization must not raise
        ImportError, and must correctly resolve to a BaseParser subclass (e.g. _HiredisParser)
        without requiring a running Redis server.
        """
        options = prod_settings.CACHES['default']['OPTIONS']
        factory = ConnectionFactory(options)
        parser_cls = factory.get_parser_cls()

        self.assertIsNotNone(parser_cls)
        self.assertTrue(
            issubclass(parser_cls, BaseParser),
            f"Resolved parser {parser_cls} must be a subclass of BaseParser"
        )

        params = factory.make_connection_params(prod_settings.REDIS_URL)
        self.assertEqual(params['parser_class'], parser_cls)

        pool = factory.get_connection_pool(params)
        self.assertEqual(pool.connection_kwargs.get('parser_class'), parser_cls)

        client = factory.get_connection(params)
        self.assertIsInstance(client, redis.Redis)

    def test_old_hiredis_parser_import_error_regression(self):
        """
        Verify that the obsolete 'redis.connection.HiredisParser' indeed raises
        ImportError in the installed redis package (redis>=5.0/8.x).
        """
        with self.assertRaises(ImportError):
            import_string('redis.connection.HiredisParser')

    def test_live_redis_roundtrip_and_throttling_if_available(self):
        """
        If a live Redis server is available at REDIS_URL:
        - Configure a Redis-backed test cache using production options and unique key prefix.
        - Verify cache set/get round-trip.
        - Verify an actual DRF request sequence reaching HTTP 429.
        - Clean up all test keys.
        If unavailable, clearly skip with credentials stripped from diagnostics.
        """
        is_available = False
        try:
            probe_client = redis.Redis.from_url(
                prod_settings.REDIS_URL,
                socket_connect_timeout=0.5,
                socket_timeout=0.5
            )
            is_available = (probe_client.ping() is True)
            probe_client.close()
        except Exception:
            is_available = False

        if not is_available:
            safe_url = _get_sanitized_redis_url(prod_settings.REDIS_URL)
            self.skipTest(
                f"Live Redis server not reachable at {safe_url}. "
                "Integration round-trip and live throttling verification skipped."
            )

        # Configure Redis-backed test cache using production options with a unique key prefix
        test_cache_config = {
            'default': {
                'BACKEND': 'django_redis.cache.RedisCache',
                'LOCATION': prod_settings.REDIS_URL,
                'OPTIONS': dict(prod_settings.CACHES['default']['OPTIONS']),
                'KEY_PREFIX': 'test_telemedicine_step2a',
                'TIMEOUT': 60,
            }
        }

        with self.settings(CACHES=test_cache_config):
            from django.core.cache import caches
            redis_cache = caches['default']
            test_key = 'roundtrip_probe_key'
            test_val = {'status': 'healthy', 'payload': 12345}

            orig_rate = AnonRateThrottle.THROTTLE_RATES.get('anon')
            AnonRateThrottle.THROTTLE_RATES['anon'] = '2/min'

            try:
                # Pre-clean any leftover keys
                try:
                    redis_cache.delete_pattern('*')
                except Exception:
                    pass

                # 1. Verify set/get round-trip on Redis-backed cache
                redis_cache.set(test_key, test_val, timeout=30)
                self.assertEqual(redis_cache.get(test_key), test_val)

                # 2. Verify DRF throttling request sequence reaches HTTP 429
                stats_url = reverse('statistics')
                r1 = self.client.get(stats_url)
                r2 = self.client.get(stats_url)
                r3 = self.client.get(stats_url)

                self.assertEqual(r1.status_code, status.HTTP_200_OK)
                self.assertEqual(r2.status_code, status.HTTP_200_OK)
                self.assertEqual(
                    r3.status_code,
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    f"Expected 429 Too Many Requests on 3rd request, got {r3.status_code}"
                )
            finally:
                # Clean up rate limit setting
                AnonRateThrottle.THROTTLE_RATES['anon'] = orig_rate

                # Clean up test keys from Redis
                try:
                    redis_cache.delete(test_key)
                    redis_cache.delete_pattern('*')
                except Exception:
                    pass
                try:
                    raw_cleanup_client = redis.Redis.from_url(prod_settings.REDIS_URL)
                    keys = raw_cleanup_client.keys('test_telemedicine_step2a:*')
                    if keys:
                        raw_cleanup_client.delete(*keys)
                    raw_cleanup_client.close()
                except Exception:
                    pass


class PatientDirectoryAccessScopingTests(APITestCase):
    """
    Feature 3C: Scope patient directory access.
    
    Requirements:
    - Doctors may see active patients linked to them through a confirmed/completed appointment
      or a non-cancelled consultation.
    - Pending/cancelled appointments alone do not grant directory access.
    - Admins retain access to all active patients.
    - Patients, unsupported roles, and unauthenticated users remain denied.
    - Apply the same scoped queryset to list, search, pagination, and detail lookup.
    - Unrelated patient detail requests must return 404.
    - Multiple qualifying relationships do not duplicate patients.
    """

    def setUp(self):
        self.patient_list_url = reverse('patient-list')

        # Doctors
        self.doctor_1 = User.objects.create_user(
            email='doctor1_f3c@example.com',
            password='Password123!@#',
            role='doctor',
        )
        UserProfile.objects.create(user=self.doctor_1, first_name='Doctor', last_name='One')
        DoctorProfile.objects.create(user=self.doctor_1, specialization='Cardiology', license_number='DOC1_F3C_LIC')

        self.doctor_2 = User.objects.create_user(
            email='doctor2_f3c@example.com',
            password='Password123!@#',
            role='doctor',
        )
        UserProfile.objects.create(user=self.doctor_2, first_name='Doctor', last_name='Two')
        DoctorProfile.objects.create(user=self.doctor_2, specialization='Neurology', license_number='DOC2_F3C_LIC')

        # Admin
        self.admin = User.objects.create_user(
            email='admin_f3c@example.com',
            password='Password123!@#',
            role='admin',
            is_staff=True,
        )

        # Patient & Unsupported role callers
        self.caller_patient = User.objects.create_user(
            email='caller_patient_f3c@example.com',
            password='Password123!@#',
            role='patient',
        )
        self.caller_nurse = User.objects.create_user(
            email='caller_nurse_f3c@example.com',
            password='Password123!@#',
            role='nurse',
        )

    def create_patient(self, email, first_name='Pat', last_name='Test', is_active=True):
        patient = User.objects.create_user(
            email=email,
            password='Password123!@#',
            role='patient',
            is_active=is_active,
        )
        UserProfile.objects.create(user=patient, first_name=first_name, last_name=last_name)
        PatientMedicalInfo.objects.create(user=patient, blood_group='O+')
        return patient

    def create_appointment(self, doctor, patient, status='confirmed'):
        now = timezone.now()
        return Appointment.objects.create(
            doctor=doctor,
            patient=patient,
            status=status,
            scheduled_start=now,
            scheduled_end=now + datetime.timedelta(hours=1),
            reason='Consultation appointment',
        )

    def create_consultation(self, doctor, patient, status='scheduled'):
        return Consultation.objects.create(
            doctor=doctor,
            patient=patient,
            status=status,
            chief_complaint='Follow up',
        )

    def detail_url(self, patient_id):
        return reverse('patient-detail', kwargs={'pk': patient_id})

    def test_relationship_source_confirmed_and_completed_appointments_grant_access(self):
        """Confirmed or completed appointments grant access to the patient in list and detail."""
        p_confirmed = self.create_patient('p_confirmed@example.com', first_name='ConfirmedPat')
        p_completed = self.create_patient('p_completed@example.com', first_name='CompletedPat')

        self.create_appointment(self.doctor_1, p_confirmed, status='confirmed')
        self.create_appointment(self.doctor_1, p_completed, status='completed')

        self.client.force_authenticate(user=self.doctor_1)

        # List
        res = self.client.get(self.patient_list_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        returned_ids = [item['id'] for item in res.data['results']]
        self.assertIn(str(p_confirmed.id), returned_ids)
        self.assertIn(str(p_completed.id), returned_ids)

        # Detail
        res_conf = self.client.get(self.detail_url(p_confirmed.id))
        self.assertEqual(res_conf.status_code, status.HTTP_200_OK)
        self.assertEqual(res_conf.data['id'], str(p_confirmed.id))

        res_comp = self.client.get(self.detail_url(p_completed.id))
        self.assertEqual(res_comp.status_code, status.HTTP_200_OK)
        self.assertEqual(res_comp.data['id'], str(p_completed.id))

    def test_relationship_source_non_cancelled_consultations_grant_access(self):
        """Non-cancelled consultations (scheduled, in_progress, completed) grant access in list and detail."""
        p_sched = self.create_patient('p_sched@example.com', first_name='SchedPat')
        p_prog = self.create_patient('p_prog@example.com', first_name='ProgPat')
        p_comp = self.create_patient('p_comp@example.com', first_name='CompPat')

        self.create_consultation(self.doctor_1, p_sched, status='scheduled')
        self.create_consultation(self.doctor_1, p_prog, status='in_progress')
        self.create_consultation(self.doctor_1, p_comp, status='completed')

        self.client.force_authenticate(user=self.doctor_1)

        res = self.client.get(self.patient_list_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        returned_ids = [item['id'] for item in res.data['results']]
        self.assertIn(str(p_sched.id), returned_ids)
        self.assertIn(str(p_prog.id), returned_ids)
        self.assertIn(str(p_comp.id), returned_ids)

        # Detail
        for pat in [p_sched, p_prog, p_comp]:
            detail_res = self.client.get(self.detail_url(pat.id))
            self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
            self.assertEqual(detail_res.data['id'], str(pat.id))

    def test_excluded_statuses_alone_do_not_grant_access(self):
        """
        Pending, cancelled, or no-show appointments and cancelled consultations alone do not grant access.
        Detail requests return 404 Not Found.
        """
        p_pending = self.create_patient('p_pending@example.com')
        p_cancelled_appt = self.create_patient('p_canc_appt@example.com')
        p_noshow = self.create_patient('p_noshow@example.com')
        p_cancelled_consult = self.create_patient('p_canc_consult@example.com')
        p_pending_and_cancelled = self.create_patient('p_pending_canc@example.com')

        self.create_appointment(self.doctor_1, p_pending, status='pending')
        self.create_appointment(self.doctor_1, p_cancelled_appt, status='cancelled')
        self.create_appointment(self.doctor_1, p_noshow, status='no_show')
        self.create_consultation(self.doctor_1, p_cancelled_consult, status='cancelled')
        self.create_appointment(self.doctor_1, p_pending_and_cancelled, status='pending')
        self.create_consultation(self.doctor_1, p_pending_and_cancelled, status='cancelled')

        self.client.force_authenticate(user=self.doctor_1)

        res = self.client.get(self.patient_list_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        returned_ids = [item['id'] for item in res.data['results']]

        for pat in [p_pending, p_cancelled_appt, p_noshow, p_cancelled_consult, p_pending_and_cancelled]:
            self.assertNotIn(str(pat.id), returned_ids)
            detail_res = self.client.get(self.detail_url(pat.id))
            self.assertEqual(detail_res.status_code, status.HTTP_404_NOT_FOUND)

    def test_unrelated_patients_isolated_from_doctor(self):
        """Unrelated patients (no appointments/consultations, or linked only to other doctors) return 404."""
        p_unrelated = self.create_patient('p_unrelated@example.com')
        p_doc2 = self.create_patient('p_doc2@example.com')

        # Link p_doc2 to Doctor 2
        self.create_appointment(self.doctor_2, p_doc2, status='confirmed')
        self.create_consultation(self.doctor_2, p_doc2, status='completed')

        # Doctor 1 requests
        self.client.force_authenticate(user=self.doctor_1)
        res1 = self.client.get(self.patient_list_url)
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        returned_ids1 = [item['id'] for item in res1.data['results']]
        self.assertNotIn(str(p_unrelated.id), returned_ids1)
        self.assertNotIn(str(p_doc2.id), returned_ids1)

        self.assertEqual(self.client.get(self.detail_url(p_unrelated.id)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(self.detail_url(p_doc2.id)).status_code, status.HTTP_404_NOT_FOUND)

        # Doctor 2 can see p_doc2, but not p_unrelated
        self.client.force_authenticate(user=self.doctor_2)
        res2 = self.client.get(self.patient_list_url)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        returned_ids2 = [item['id'] for item in res2.data['results']]
        self.assertIn(str(p_doc2.id), returned_ids2)
        self.assertNotIn(str(p_unrelated.id), returned_ids2)

        self.assertEqual(self.client.get(self.detail_url(p_doc2.id)).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(self.detail_url(p_unrelated.id)).status_code, status.HTTP_404_NOT_FOUND)

    def test_inactive_patients_excluded_from_doctor_and_admin(self):
        """Inactive patients (is_active=False) are excluded from both doctor and admin access."""
        p_inactive_doc = self.create_patient('p_inact_doc@example.com', is_active=False)
        self.create_appointment(self.doctor_1, p_inactive_doc, status='confirmed')
        self.create_consultation(self.doctor_1, p_inactive_doc, status='completed')

        p_inactive_admin = self.create_patient('p_inact_adm@example.com', is_active=False)

        # Doctor check
        self.client.force_authenticate(user=self.doctor_1)
        res_doc = self.client.get(self.patient_list_url)
        returned_ids_doc = [item['id'] for item in res_doc.data['results']]
        self.assertNotIn(str(p_inactive_doc.id), returned_ids_doc)
        self.assertNotIn(str(p_inactive_admin.id), returned_ids_doc)
        self.assertEqual(self.client.get(self.detail_url(p_inactive_doc.id)).status_code, status.HTTP_404_NOT_FOUND)

        # Admin check
        self.client.force_authenticate(user=self.admin)
        res_adm = self.client.get(self.patient_list_url)
        returned_ids_adm = [item['id'] for item in res_adm.data['results']]
        self.assertNotIn(str(p_inactive_doc.id), returned_ids_adm)
        self.assertNotIn(str(p_inactive_admin.id), returned_ids_adm)
        self.assertEqual(self.client.get(self.detail_url(p_inactive_doc.id)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(self.detail_url(p_inactive_admin.id)).status_code, status.HTTP_404_NOT_FOUND)

    def test_multiple_qualifying_relationships_do_not_duplicate_patients(self):
        """A patient linked through multiple qualifying appointments and consultations appears exactly once."""
        p_multi = self.create_patient('p_multi@example.com', first_name='MultiRelation')

        self.create_appointment(self.doctor_1, p_multi, status='confirmed')
        self.create_appointment(self.doctor_1, p_multi, status='completed')
        self.create_consultation(self.doctor_1, p_multi, status='scheduled')
        self.create_consultation(self.doctor_1, p_multi, status='completed')

        self.client.force_authenticate(user=self.doctor_1)
        res = self.client.get(self.patient_list_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        matching_items = [item for item in res.data['results'] if item['id'] == str(p_multi.id)]
        self.assertEqual(len(matching_items), 1, "Patient should appear exactly once in results list")
        self.assertEqual(res.data['count'], 1)

    def test_search_isolation_between_doctors(self):
        """Search queries only return matching patients linked to the authenticated doctor."""
        p_alice = self.create_patient('alice@example.com', first_name='Alice', last_name='Smith')
        p_alicia = self.create_patient('alicia@example.com', first_name='Alicia', last_name='Keys')

        self.create_appointment(self.doctor_1, p_alice, status='confirmed')
        self.create_appointment(self.doctor_2, p_alicia, status='confirmed')

        # Doctor 1 search
        self.client.force_authenticate(user=self.doctor_1)
        res_doc1 = self.client.get(self.patient_list_url + '?search=Alic')
        self.assertEqual(res_doc1.status_code, status.HTTP_200_OK)
        returned_ids_doc1 = [item['id'] for item in res_doc1.data['results']]
        self.assertIn(str(p_alice.id), returned_ids_doc1)
        self.assertNotIn(str(p_alicia.id), returned_ids_doc1)
        self.assertEqual(res_doc1.data['count'], 1)

        # Doctor 2 search
        self.client.force_authenticate(user=self.doctor_2)
        res_doc2 = self.client.get(self.patient_list_url + '?search=Alic')
        self.assertEqual(res_doc2.status_code, status.HTTP_200_OK)
        returned_ids_doc2 = [item['id'] for item in res_doc2.data['results']]
        self.assertIn(str(p_alicia.id), returned_ids_doc2)
        self.assertNotIn(str(p_alice.id), returned_ids_doc2)
        self.assertEqual(res_doc2.data['count'], 1)

        # Admin search sees both
        self.client.force_authenticate(user=self.admin)
        res_admin = self.client.get(self.patient_list_url + '?search=Alic')
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        returned_ids_admin = [item['id'] for item in res_admin.data['results']]
        self.assertIn(str(p_alice.id), returned_ids_admin)
        self.assertIn(str(p_alicia.id), returned_ids_admin)
        self.assertEqual(res_admin.data['count'], 2)

    def test_pagination_with_scoped_queryset(self):
        """Pagination preserves relationship scoping without including cross-doctor patients."""
        doc1_patients = [
            self.create_patient(f'p_page_d1_{i}@example.com', first_name=f'P1_{i}')
            for i in range(25)
        ]
        doc2_patients = [
            self.create_patient(f'p_page_d2_{i}@example.com', first_name=f'P2_{i}')
            for i in range(5)
        ]

        for p in doc1_patients:
            self.create_appointment(self.doctor_1, p, status='confirmed')
        for p in doc2_patients:
            self.create_appointment(self.doctor_2, p, status='confirmed')

        self.client.force_authenticate(user=self.doctor_1)

        # Page 1
        res_page1 = self.client.get(self.patient_list_url)
        self.assertEqual(res_page1.status_code, status.HTTP_200_OK)
        self.assertEqual(res_page1.data['count'], 25)
        self.assertEqual(len(res_page1.data['results']), 20)
        self.assertIsNotNone(res_page1.data['next'])

        # Page 2
        res_page2 = self.client.get(res_page1.data['next'])
        self.assertEqual(res_page2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_page2.data['results']), 5)

        # All 25 are doc1 patients, none are doc2
        all_returned_ids = {item['id'] for item in res_page1.data['results']} | {item['id'] for item in res_page2.data['results']}
        doc1_ids = {str(p.id) for p in doc1_patients}
        doc2_ids = {str(p.id) for p in doc2_patients}

        self.assertEqual(all_returned_ids, doc1_ids)
        self.assertTrue(all_returned_ids.isdisjoint(doc2_ids))

    def test_admin_access_to_all_active_patients(self):
        """Admins retain full access to all active patients, whether linked to doctors or unlinked."""
        p_doc1 = self.create_patient('admin_check_d1@example.com')
        p_doc2 = self.create_patient('admin_check_d2@example.com')
        p_unlinked = self.create_patient('admin_check_unlinked@example.com')

        self.create_appointment(self.doctor_1, p_doc1, status='confirmed')
        self.create_appointment(self.doctor_2, p_doc2, status='confirmed')

        self.client.force_authenticate(user=self.admin)
        res = self.client.get(self.patient_list_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        returned_ids = [item['id'] for item in res.data['results']]

        self.assertIn(str(p_doc1.id), returned_ids)
        self.assertIn(str(p_doc2.id), returned_ids)
        self.assertIn(str(p_unlinked.id), returned_ids)

        for pat in [p_doc1, p_doc2, p_unlinked]:
            detail_res = self.client.get(self.detail_url(pat.id))
            self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
            self.assertEqual(detail_res.data['id'], str(pat.id))

    def test_unauthenticated_and_unsupported_roles_denied(self):
        """Unauthenticated requests are denied with 401; patients and unsupported roles are denied with 403."""
        target_patient = self.create_patient('target_pat@example.com')
        detail_url = self.detail_url(target_patient.id)

        # 1. Unauthenticated (401)
        self.client.logout()
        res_anon_list = self.client.get(self.patient_list_url)
        self.assertEqual(res_anon_list.status_code, status.HTTP_401_UNAUTHORIZED)
        res_anon_detail = self.client.get(detail_url)
        self.assertEqual(res_anon_detail.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Patient (403)
        self.client.force_authenticate(user=self.caller_patient)
        res_pat_list = self.client.get(self.patient_list_url)
        self.assertEqual(res_pat_list.status_code, status.HTTP_403_FORBIDDEN)
        res_pat_detail = self.client.get(detail_url)
        self.assertEqual(res_pat_detail.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Unsupported role (403)
        self.client.force_authenticate(user=self.caller_nurse)
        res_nurse_list = self.client.get(self.patient_list_url)
        self.assertEqual(res_nurse_list.status_code, status.HTTP_403_FORBIDDEN)
        res_nurse_detail = self.client.get(detail_url)
        self.assertEqual(res_nurse_detail.status_code, status.HTTP_403_FORBIDDEN)



