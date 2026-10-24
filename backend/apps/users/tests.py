"""
Tests for apps.users authentication and profile access control.
"""
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.users.models import UserProfile, DoctorProfile, PatientMedicalInfo
from apps.users.serializers import UserSerializer

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
