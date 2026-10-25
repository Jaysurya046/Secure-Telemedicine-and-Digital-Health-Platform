"""
Tests for Feature 4A: Secure appointment ownership and status writes.

Covers:
- Patient creation derives patient from caller; omits work; spoofing rejected.
- Doctor creation derives doctor; author spoofing rejected.
- Admin creation validates both participant roles.
- Every new appointment starts as pending; non-pending status rejected.
- Patient and doctor are immutable after creation (including admin); unchanged values accepted.
- Generic PUT/PATCH rejects status changes; confirm/cancel/complete actions preserved.
- Deny unsupported roles and unauthenticated callers; participant-scoped access preserved.
- Patient portal actual booking payload, malformed bodies, and DB immutability after rejection.
"""
from datetime import datetime, timedelta, time, timezone as dt_timezone
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APITransactionTestCase, APIRequestFactory

from apps.appointments.models import Appointment, DoctorAvailability
from apps.appointments.permissions import AppointmentAccessPermission, DoctorAvailabilityAccessPermission

User = get_user_model()


class AppointmentTestMixin:
    """Shared test setup and helper methods for appointment test cases."""

    def setUp(self):
        super().setUp()
        # Patients
        self.patient_1 = User.objects.create_user(
            email='patient1@example.com',
            password='Password123!@#',
            role='patient',
        )
        self.patient_2 = User.objects.create_user(
            email='patient2@example.com',
            password='Password123!@#',
            role='patient',
        )

        # Doctors
        self.doctor_1 = User.objects.create_user(
            email='doctor1@example.com',
            password='Password123!@#',
            role='doctor',
        )
        self.doctor_2 = User.objects.create_user(
            email='doctor2@example.com',
            password='Password123!@#',
            role='doctor',
        )

        # Admin
        self.admin = User.objects.create_user(
            email='admin@example.com',
            password='Password123!@#',
            role='admin',
            is_staff=True,
            is_superuser=True,
        )

        # Unsupported role
        self.nurse = User.objects.create_user(
            email='nurse@example.com',
            password='Password123!@#',
            role='nurse',
        )

        # URLs
        self.list_url = reverse('appointment-list')

        # Baseline active availability windows for doctor_1 and doctor_2 covering all days
        for doc in (self.doctor_1, self.doctor_2):
            for day in range(7):
                DoctorAvailability.objects.create(
                    doctor=doc,
                    weekday=day,
                    start_time=time(0, 0, 0),
                    end_time=time(23, 59, 59),
                    is_active=True,
                )

        # Baseline appointment between doctor_1 and patient_1
        now = timezone.now()
        self.appointment_1 = Appointment.objects.create(
            patient=self.patient_1,
            doctor=self.doctor_1,
            scheduled_start=now + timedelta(days=2, hours=9),
            scheduled_end=now + timedelta(days=2, hours=10),
            status='pending',
            reason='General Checkup',
            notes='Initial notes',
        )

        # Baseline appointment between doctor_2 and patient_2
        self.appointment_2 = Appointment.objects.create(
            patient=self.patient_2,
            doctor=self.doctor_2,
            scheduled_start=now + timedelta(days=3, hours=14),
            scheduled_end=now + timedelta(days=3, hours=15),
            status='pending',
            reason='Follow-up Visit',
            notes='Follow-up notes',
        )

    def detail_url(self, pk):
        return reverse('appointment-detail', kwargs={'pk': pk})

    def confirm_url(self, pk):
        return reverse('appointment-confirm', kwargs={'pk': pk})

    def cancel_url(self, pk):
        return reverse('appointment-cancel', kwargs={'pk': pk})

    def complete_url(self, pk):
        return reverse('appointment-complete', kwargs={'pk': pk})

    @property
    def availability_list_url(self):
        return reverse('doctor-availability-list')

    def availability_detail_url(self, pk):
        return reverse('doctor-availability-detail', kwargs={'pk': pk})

    def get_error_details(self, response):
        """Helper to extract field errors from standard or custom DRF responses."""
        if isinstance(response.data, dict) and 'details' in response.data:
            return response.data['details']
        return response.data


class BaseAppointmentTestCase(AppointmentTestMixin, APITestCase):
    """Base test setup with standard transactional rollback between tests."""
    pass


class BaseAppointmentTransactionTestCase(AppointmentTestMixin, APITransactionTestCase):
    """Committed transaction test setup for multi-threaded concurrency testing."""
    pass


class PatientBookingAndDerivationTests(BaseAppointmentTestCase):
    """
    Tests for patient appointment creation:
    - Derives patient from authenticated caller before validation.
    - Omitting patient must work (patient portal actual booking payload).
    - Conflicting patient IDs must be rejected.
    """

    def test_patient_portal_actual_booking_payload_derives_patient(self):
        """
        Patient portal sends: { doctor, scheduled_start, scheduled_end, reason, symptoms: [] }
        Omitting patient must succeed and derive patient from caller.
        """
        self.client.force_authenticate(user=self.patient_1)
        start = timezone.now() + timedelta(days=5, hours=10)
        end = timezone.now() + timedelta(days=5, hours=11)
        payload = {
            'doctor': str(self.doctor_1.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Annual wellness examination',
            'symptoms': ['headache', 'fatigue'],
        }

        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Appointment.objects.count(), initial_count + 1)

        created = Appointment.objects.get(id=response.data['id'])
        self.assertEqual(created.patient, self.patient_1)
        self.assertEqual(created.doctor, self.doctor_1)
        self.assertEqual(created.status, 'pending')
        self.assertEqual(created.reason, 'Annual wellness examination')
        self.assertEqual(created.symptoms, ['headache', 'fatigue'])

    def test_patient_booking_with_matching_patient_id_succeeds(self):
        """Supplying caller's own patient ID explicitly is accepted."""
        self.client.force_authenticate(user=self.patient_1)
        start = timezone.now() + timedelta(days=6, hours=10)
        end = timezone.now() + timedelta(days=6, hours=11)
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_2.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Consultation with doctor 2',
        }

        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Appointment.objects.get(id=response.data['id'])
        self.assertEqual(created.patient, self.patient_1)
        self.assertEqual(created.doctor, self.doctor_2)

    def test_patient_spoofing_another_patient_id_rejected(self):
        """Patient 1 attempting to schedule for Patient 2 is rejected before validation."""
        self.client.force_authenticate(user=self.patient_1)
        start = timezone.now() + timedelta(days=7, hours=10)
        end = timezone.now() + timedelta(days=7, hours=11)
        payload = {
            'patient': str(self.patient_2.id),
            'doctor': str(self.doctor_1.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Attempted identity spoofing',
        }

        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(response))
        self.assertEqual(Appointment.objects.count(), initial_count)

    def test_patient_booking_omitting_doctor_rejected(self):
        """Patient booking without specifying a doctor is rejected."""
        self.client.force_authenticate(user=self.patient_1)
        start = timezone.now() + timedelta(days=8, hours=10)
        end = timezone.now() + timedelta(days=8, hours=11)
        payload = {
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Missing doctor appointment',
        }

        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(response))
        self.assertEqual(Appointment.objects.count(), initial_count)

    def test_patient_booking_with_non_doctor_user_as_doctor_rejected(self):
        """Patient supplying a patient user as the doctor is rejected."""
        self.client.force_authenticate(user=self.patient_1)
        start = timezone.now() + timedelta(days=9, hours=10)
        end = timezone.now() + timedelta(days=9, hours=11)
        payload = {
            'doctor': str(self.patient_2.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Invalid doctor role',
        }

        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(response))
        self.assertEqual(Appointment.objects.count(), initial_count)


class DoctorBookingAndDerivationTests(BaseAppointmentTestCase):
    """
    Tests for doctor appointment creation:
    - Derives doctor from authenticated caller before validation.
    - Omitting doctor must work.
    - Conflicting doctor IDs (author spoofing) must be rejected.
    """

    def test_doctor_creation_omitting_doctor_derives_caller(self):
        """Doctor creating appointment without supplying doctor derives caller."""
        self.client.force_authenticate(user=self.doctor_1)
        start = timezone.now() + timedelta(days=10, hours=9)
        end = timezone.now() + timedelta(days=10, hours=10)
        payload = {
            'patient': str(self.patient_1.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Routine clinical checkup scheduled by doctor',
        }

        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Appointment.objects.count(), initial_count + 1)

        created = Appointment.objects.get(id=response.data['id'])
        self.assertEqual(created.doctor, self.doctor_1)
        self.assertEqual(created.patient, self.patient_1)
        self.assertEqual(created.status, 'pending')

    def test_doctor_creation_with_matching_doctor_id_succeeds(self):
        """Doctor creating appointment supplying their own ID succeeds."""
        self.client.force_authenticate(user=self.doctor_1)
        start = timezone.now() + timedelta(days=11, hours=9)
        end = timezone.now() + timedelta(days=11, hours=10)
        payload = {
            'doctor': str(self.doctor_1.id),
            'patient': str(self.patient_2.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Explicit doctor ID match',
        }

        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Appointment.objects.get(id=response.data['id'])
        self.assertEqual(created.doctor, self.doctor_1)
        self.assertEqual(created.patient, self.patient_2)

    def test_doctor_author_spoofing_another_doctor_rejected(self):
        """Doctor 1 attempting to create appointment as Doctor 2 is rejected."""
        self.client.force_authenticate(user=self.doctor_1)
        start = timezone.now() + timedelta(days=12, hours=9)
        end = timezone.now() + timedelta(days=12, hours=10)
        payload = {
            'doctor': str(self.doctor_2.id),
            'patient': str(self.patient_1.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Doctor author spoofing attempt',
        }

        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(response))
        self.assertEqual(Appointment.objects.count(), initial_count)

    def test_doctor_creation_omitting_patient_rejected(self):
        """Doctor creating appointment without specifying patient is rejected."""
        self.client.force_authenticate(user=self.doctor_1)
        start = timezone.now() + timedelta(days=13, hours=9)
        end = timezone.now() + timedelta(days=13, hours=10)
        payload = {
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Missing patient',
        }

        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(response))
        self.assertEqual(Appointment.objects.count(), initial_count)

    def test_doctor_creation_with_non_patient_user_rejected(self):
        """Doctor specifying a doctor as patient is rejected."""
        self.client.force_authenticate(user=self.doctor_1)
        start = timezone.now() + timedelta(days=14, hours=9)
        end = timezone.now() + timedelta(days=14, hours=10)
        payload = {
            'patient': str(self.doctor_2.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Invalid patient role',
        }

        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(response))
        self.assertEqual(Appointment.objects.count(), initial_count)


class AdminBookingAndValidationTests(BaseAppointmentTestCase):
    """
    Tests for admin appointment creation:
    - Admin must supply both patient and doctor.
    - Validates participant roles (patient role for patient, doctor role for doctor).
    """

    def test_admin_creation_with_valid_roles_succeeds(self):
        """Admin supplies valid patient and doctor; appointment created as pending."""
        self.client.force_authenticate(user=self.admin)
        start = timezone.now() + timedelta(days=15, hours=11)
        end = timezone.now() + timedelta(days=15, hours=12)
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_1.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Admin scheduled consultation',
        }

        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Appointment.objects.count(), initial_count + 1)

        created = Appointment.objects.get(id=response.data['id'])
        self.assertEqual(created.patient, self.patient_1)
        self.assertEqual(created.doctor, self.doctor_1)
        self.assertEqual(created.status, 'pending')

    def test_admin_creation_omitting_patient_rejected(self):
        """Admin omitting patient is rejected."""
        self.client.force_authenticate(user=self.admin)
        start = timezone.now() + timedelta(days=16, hours=11)
        end = timezone.now() + timedelta(days=16, hours=12)
        payload = {
            'doctor': str(self.doctor_1.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Admin missing patient',
        }

        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(response))
        self.assertEqual(Appointment.objects.count(), initial_count)

    def test_admin_creation_omitting_doctor_rejected(self):
        """Admin omitting doctor is rejected."""
        self.client.force_authenticate(user=self.admin)
        start = timezone.now() + timedelta(days=17, hours=11)
        end = timezone.now() + timedelta(days=17, hours=12)
        payload = {
            'patient': str(self.patient_1.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Admin missing doctor',
        }

        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(response))
        self.assertEqual(Appointment.objects.count(), initial_count)

    def test_admin_creation_with_invalid_patient_role_rejected(self):
        """Admin supplying a doctor as the patient is rejected."""
        self.client.force_authenticate(user=self.admin)
        start = timezone.now() + timedelta(days=18, hours=11)
        end = timezone.now() + timedelta(days=18, hours=12)
        payload = {
            'patient': str(self.doctor_2.id),
            'doctor': str(self.doctor_1.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Admin invalid patient role',
        }

        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(response))
        self.assertEqual(Appointment.objects.count(), initial_count)

    def test_admin_creation_with_invalid_doctor_role_rejected(self):
        """Admin supplying a patient as the doctor is rejected."""
        self.client.force_authenticate(user=self.admin)
        start = timezone.now() + timedelta(days=19, hours=11)
        end = timezone.now() + timedelta(days=19, hours=12)
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.patient_2.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Admin invalid doctor role',
        }

        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(response))
        self.assertEqual(Appointment.objects.count(), initial_count)


class StatusInjectionTests(BaseAppointmentTestCase):
    """
    Every new appointment starts as pending. Reject supplied non-pending status.
    Tests patient, doctor, and admin creation with non-pending status injection.
    """

    def test_patient_status_injection_rejected(self):
        """Patient attempting to create appointment with status='confirmed' is rejected."""
        self.client.force_authenticate(user=self.patient_1)
        start = timezone.now() + timedelta(days=20, hours=10)
        end = timezone.now() + timedelta(days=20, hours=11)
        for injected_status in ['confirmed', 'completed', 'cancelled', 'no_show']:
            with self.subTest(status=injected_status):
                initial_count = Appointment.objects.count()
                payload = {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': start.isoformat(),
                    'scheduled_end': end.isoformat(),
                    'reason': f'Status injection {injected_status}',
                    'status': injected_status,
                }
                response = self.client.post(self.list_url, payload, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('status', self.get_error_details(response))
                self.assertEqual(Appointment.objects.count(), initial_count)

    def test_doctor_status_injection_rejected(self):
        """Doctor attempting to create appointment with status='confirmed' is rejected."""
        self.client.force_authenticate(user=self.doctor_1)
        start = timezone.now() + timedelta(days=21, hours=10)
        end = timezone.now() + timedelta(days=21, hours=11)
        initial_count = Appointment.objects.count()
        payload = {
            'patient': str(self.patient_1.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Doctor status injection attempt',
            'status': 'confirmed',
        }
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', self.get_error_details(response))
        self.assertEqual(Appointment.objects.count(), initial_count)

    def test_admin_status_injection_rejected(self):
        """Admin attempting to create appointment with status='completed' is rejected."""
        self.client.force_authenticate(user=self.admin)
        start = timezone.now() + timedelta(days=22, hours=10)
        end = timezone.now() + timedelta(days=22, hours=11)
        initial_count = Appointment.objects.count()
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_1.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Admin status injection attempt',
            'status': 'completed',
        }
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', self.get_error_details(response))
        self.assertEqual(Appointment.objects.count(), initial_count)

    def test_explicit_pending_status_accepted(self):
        """Supplying status='pending' explicitly on creation is accepted."""
        self.client.force_authenticate(user=self.patient_1)
        start = timezone.now() + timedelta(days=23, hours=10)
        end = timezone.now() + timedelta(days=23, hours=11)
        payload = {
            'doctor': str(self.doctor_1.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Explicit pending status',
            'status': 'pending',
        }
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Appointment.objects.get(id=response.data['id'])
        self.assertEqual(created.status, 'pending')


class ReassignmentAndImmutabilityTests(BaseAppointmentTestCase):
    """
    Patient and doctor are immutable after creation, including admin updates.
    Accept unchanged values. Verify DB state remains unchanged after rejection.
    """

    def test_patient_reassignment_rejected_for_patient(self):
        """Patient cannot change patient ID via PATCH."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.detail_url(self.appointment_1.id)
        response = self.client.patch(url, {'patient': str(self.patient_2.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(response))

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.patient, self.patient_1)

    def test_doctor_reassignment_rejected_for_patient(self):
        """Patient cannot change doctor ID via PATCH."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.detail_url(self.appointment_1.id)
        response = self.client.patch(url, {'doctor': str(self.doctor_2.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(response))

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.doctor, self.doctor_1)

    def test_patient_reassignment_rejected_for_doctor(self):
        """Doctor cannot change patient ID via PATCH."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.detail_url(self.appointment_1.id)
        response = self.client.patch(url, {'patient': str(self.patient_2.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(response))

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.patient, self.patient_1)

    def test_doctor_reassignment_rejected_for_doctor(self):
        """Doctor cannot change doctor ID via PATCH."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.detail_url(self.appointment_1.id)
        response = self.client.patch(url, {'doctor': str(self.doctor_2.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(response))

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.doctor, self.doctor_1)

    def test_patient_and_doctor_reassignment_rejected_for_admin(self):
        """Admin cannot change patient or doctor after creation."""
        self.client.force_authenticate(user=self.admin)
        url = self.detail_url(self.appointment_1.id)

        # Attempt patient change
        res1 = self.client.patch(url, {'patient': str(self.patient_2.id)}, format='json')
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(res1))

        # Attempt doctor change
        res2 = self.client.patch(url, {'doctor': str(self.doctor_2.id)}, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(res2))

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.patient, self.patient_1)
        self.assertEqual(self.appointment_1.doctor, self.doctor_1)

    def test_unchanged_patient_and_doctor_accepted_on_update(self):
        """Supplying unchanged patient and doctor on update is accepted."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.detail_url(self.appointment_1.id)
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_1.id),
            'reason': 'Updated reason with same participants',
        }
        response = self.client.patch(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.reason, 'Updated reason with same participants')
        self.assertEqual(self.appointment_1.patient, self.patient_1)
        self.assertEqual(self.appointment_1.doctor, self.doctor_1)

    def test_full_put_with_unchanged_participants_accepted(self):
        """Full PUT update providing unchanged patient and doctor succeeds."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.detail_url(self.appointment_1.id)
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_1.id),
            'scheduled_start': self.appointment_1.scheduled_start.isoformat(),
            'scheduled_end': self.appointment_1.scheduled_end.isoformat(),
            'reason': 'Doctor updated full record',
            'notes': 'New notes added',
            'symptoms': ['fever'],
        }
        response = self.client.put(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.reason, 'Doctor updated full record')
        self.assertEqual(self.appointment_1.notes, 'New notes added')
        self.assertEqual(self.appointment_1.symptoms, ['fever'])


class GenericStatusUpdateRejectionTests(BaseAppointmentTestCase):
    """
    Generic PUT/PATCH must reject status changes.
    Preserve existing confirm/cancel/complete actions.
    """

    def test_generic_patch_status_change_rejected_for_patient(self):
        """Patient cannot change status via generic PATCH."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.detail_url(self.appointment_1.id)
        response = self.client.patch(url, {'status': 'confirmed'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', self.get_error_details(response))

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'pending')

    def test_generic_patch_status_change_rejected_for_doctor(self):
        """Doctor cannot change status via generic PATCH."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.detail_url(self.appointment_1.id)
        response = self.client.patch(url, {'status': 'confirmed'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', self.get_error_details(response))

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'pending')

    def test_generic_patch_status_change_rejected_for_admin(self):
        """Admin cannot change status via generic PATCH."""
        self.client.force_authenticate(user=self.admin)
        url = self.detail_url(self.appointment_1.id)
        response = self.client.patch(url, {'status': 'cancelled'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', self.get_error_details(response))

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'pending')

    def test_generic_put_status_change_rejected(self):
        """PUT request attempting to change status is rejected."""
        self.client.force_authenticate(user=self.admin)
        url = self.detail_url(self.appointment_1.id)
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_1.id),
            'scheduled_start': self.appointment_1.scheduled_start.isoformat(),
            'scheduled_end': self.appointment_1.scheduled_end.isoformat(),
            'reason': 'Admin attempt to change status via PUT',
            'status': 'completed',
        }
        response = self.client.put(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', self.get_error_details(response))

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'pending')

    def test_generic_put_with_unchanged_status_accepted(self):
        """PUT request providing unchanged status is accepted."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.detail_url(self.appointment_1.id)
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_1.id),
            'scheduled_start': self.appointment_1.scheduled_start.isoformat(),
            'scheduled_end': self.appointment_1.scheduled_end.isoformat(),
            'reason': 'Updated reason keeping status unchanged',
            'status': 'pending',
        }
        response = self.client.put(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'pending')
        self.assertEqual(self.appointment_1.reason, 'Updated reason keeping status unchanged')

    def test_preserved_confirm_action(self):
        """Doctor confirms appointment via dedicated confirm action; patient is denied."""
        # Patient attempting confirm action is denied (403)
        self.client.force_authenticate(user=self.patient_1)
        res_pat = self.client.post(self.confirm_url(self.appointment_1.id))
        self.assertEqual(res_pat.status_code, status.HTTP_403_FORBIDDEN)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'pending')

        # Doctor confirms own appointment (200)
        self.client.force_authenticate(user=self.doctor_1)
        res_doc = self.client.post(self.confirm_url(self.appointment_1.id))
        self.assertEqual(res_doc.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'confirmed')

    def test_preserved_cancel_action(self):
        """Patient, doctor, or admin cancels appointment via dedicated cancel action."""
        self.client.force_authenticate(user=self.patient_1)
        response = self.client.post(
            self.cancel_url(self.appointment_1.id),
            {'cancellation_reason': 'Patient feeling better'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'cancelled')
        self.assertEqual(self.appointment_1.cancellation_reason, 'Patient feeling better')

    def test_preserved_complete_action(self):
        """Doctor completes appointment via dedicated complete action; patient is denied."""
        # First confirm
        self.appointment_1.status = 'confirmed'
        self.appointment_1.save()

        # Patient cannot complete
        self.client.force_authenticate(user=self.patient_1)
        res_pat = self.client.post(self.complete_url(self.appointment_1.id))
        self.assertEqual(res_pat.status_code, status.HTTP_403_FORBIDDEN)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'confirmed')

        # Doctor completes
        self.client.force_authenticate(user=self.doctor_1)
        res_doc = self.client.post(self.complete_url(self.appointment_1.id))
        self.assertEqual(res_doc.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'completed')

    def test_admin_can_use_dedicated_lifecycle_actions(self):
        """Admin can call confirm, cancel, and complete on appointments."""
        self.client.force_authenticate(user=self.admin)

        # Confirm
        res1 = self.client.post(self.confirm_url(self.appointment_1.id))
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'confirmed')

        # Complete
        res2 = self.client.post(self.complete_url(self.appointment_1.id))
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'completed')


class CrossUserAccessTests(BaseAppointmentTestCase):
    """
    Preserve participant-scoped access:
    - Patients only access their own appointments.
    - Doctors only access their assigned appointments.
    - Admins retain access to all appointments.
    - Cross-user access returns 404 and leaves DB rows untouched.
    """

    def test_patient_cross_user_access_denied_and_leaves_db_unchanged(self):
        """Patient 2 cannot read, edit, delete, or perform actions on Patient 1's appointment."""
        self.client.force_authenticate(user=self.patient_2)
        url = self.detail_url(self.appointment_1.id)

        # Retrieve
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        # Partial update
        self.assertEqual(self.client.patch(url, {'reason': 'Hacked'}).status_code, status.HTTP_404_NOT_FOUND)
        # Full update
        self.assertEqual(self.client.put(url, {'reason': 'Hacked'}).status_code, status.HTTP_404_NOT_FOUND)
        # Delete
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)
        # Actions
        self.assertEqual(self.client.post(self.confirm_url(self.appointment_1.id)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(self.cancel_url(self.appointment_1.id)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(self.complete_url(self.appointment_1.id)).status_code, status.HTTP_404_NOT_FOUND)

        # Verify DB row is completely unchanged
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.reason, 'General Checkup')
        self.assertEqual(self.appointment_1.status, 'pending')
        self.assertEqual(self.appointment_1.patient, self.patient_1)
        self.assertEqual(self.appointment_1.doctor, self.doctor_1)

    def test_doctor_cross_user_access_denied_and_leaves_db_unchanged(self):
        """Doctor 2 cannot read, edit, delete, or perform actions on Doctor 1's appointment."""
        self.client.force_authenticate(user=self.doctor_2)
        url = self.detail_url(self.appointment_1.id)

        # Retrieve
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        # Partial update
        self.assertEqual(self.client.patch(url, {'reason': 'Hacked by doctor 2'}).status_code, status.HTTP_404_NOT_FOUND)
        # Delete
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)
        # Actions
        self.assertEqual(self.client.post(self.confirm_url(self.appointment_1.id)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(self.cancel_url(self.appointment_1.id)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(self.complete_url(self.appointment_1.id)).status_code, status.HTTP_404_NOT_FOUND)

        # Verify DB row is completely unchanged
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.reason, 'General Checkup')
        self.assertEqual(self.appointment_1.status, 'pending')

    def test_list_scoping_per_participant(self):
        """Listing appointments returns only participant's own appointments."""
        # Patient 1 only sees appointment_1
        self.client.force_authenticate(user=self.patient_1)
        res1 = self.client.get(self.list_url)
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        results1 = res1.data.get('results', res1.data)
        ids1 = [str(r['id']) for r in results1]
        self.assertIn(str(self.appointment_1.id), ids1)
        self.assertNotIn(str(self.appointment_2.id), ids1)

        # Doctor 2 only sees appointment_2
        self.client.force_authenticate(user=self.doctor_2)
        res2 = self.client.get(self.list_url)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        results2 = res2.data.get('results', res2.data)
        ids2 = [str(r['id']) for r in results2]
        self.assertNotIn(str(self.appointment_1.id), ids2)
        self.assertIn(str(self.appointment_2.id), ids2)

        # Admin sees all appointments
        self.client.force_authenticate(user=self.admin)
        res_admin = self.client.get(self.list_url)
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        results_admin = res_admin.data.get('results', res_admin.data)
        ids_admin = [str(r['id']) for r in results_admin]
        self.assertIn(str(self.appointment_1.id), ids_admin)
        self.assertIn(str(self.appointment_2.id), ids_admin)


class UnauthenticatedAndUnsupportedRoleTests(BaseAppointmentTestCase):
    """
    Deny unsupported roles (403) and unauthenticated callers (401).
    """

    def test_unauthenticated_caller_denied_with_401(self):
        """Unauthenticated requests are denied with 401."""
        url = self.detail_url(self.appointment_1.id)

        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(self.list_url, {}).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.patch(url, {'reason': 'Unauth'}).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(self.confirm_url(self.appointment_1.id)).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(self.cancel_url(self.appointment_1.id)).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(self.complete_url(self.appointment_1.id)).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unsupported_role_caller_denied_with_403(self):
        """User with unsupported role (nurse) is denied with 403."""
        self.client.force_authenticate(user=self.nurse)
        url = self.detail_url(self.appointment_1.id)

        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(self.list_url, {}).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.patch(url, {'reason': 'Nurse'}).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(self.confirm_url(self.appointment_1.id)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(self.cancel_url(self.appointment_1.id)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(self.complete_url(self.appointment_1.id)).status_code, status.HTTP_403_FORBIDDEN)

    def test_appointment_access_permission_unit_logic(self):
        """Unit verification of AppointmentAccessPermission methods."""
        perm = AppointmentAccessPermission()
        factory = APIRequestFactory()

        # Unauthenticated
        req_unauth = factory.get('/')
        req_unauth.user = None
        self.assertFalse(perm.has_permission(req_unauth, None))
        self.assertFalse(perm.has_object_permission(req_unauth, None, self.appointment_1))

        # Unsupported role
        req_nurse = factory.get('/')
        req_nurse.user = self.nurse
        self.assertFalse(perm.has_permission(req_nurse, None))
        self.assertFalse(perm.has_object_permission(req_nurse, None, self.appointment_1))

        # Patient assigned vs unassigned
        req_pat1 = factory.get('/')
        req_pat1.user = self.patient_1
        self.assertTrue(perm.has_permission(req_pat1, None))
        self.assertTrue(perm.has_object_permission(req_pat1, None, self.appointment_1))
        self.assertFalse(perm.has_object_permission(req_pat1, None, self.appointment_2))

        # Doctor assigned vs unassigned
        req_doc1 = factory.get('/')
        req_doc1.user = self.doctor_1
        self.assertTrue(perm.has_permission(req_doc1, None))
        self.assertTrue(perm.has_object_permission(req_doc1, None, self.appointment_1))
        self.assertFalse(perm.has_object_permission(req_doc1, None, self.appointment_2))

        # Admin
        req_admin = factory.get('/')
        req_admin.user = self.admin
        self.assertTrue(perm.has_permission(req_admin, None))
        self.assertTrue(perm.has_object_permission(req_admin, None, self.appointment_1))
        self.assertTrue(perm.has_object_permission(req_admin, None, self.appointment_2))


class MalformedBodiesAndTimeConflictTests(BaseAppointmentTestCase):
    """
    Tests for malformed request bodies and existing time/conflict validation preservation.
    """

    def test_malformed_non_dict_body_rejected(self):
        """Sending a non-dict / list payload to create endpoint returns 400."""
        self.client.force_authenticate(user=self.patient_1)
        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, ['invalid', 'list'], format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Appointment.objects.count(), initial_count)

    def test_missing_required_fields_rejected(self):
        """Missing reason or scheduled_start returns 400 and does not create record."""
        self.client.force_authenticate(user=self.patient_1)
        initial_count = Appointment.objects.count()
        payload = {
            'doctor': str(self.doctor_1.id),
            'scheduled_start': (timezone.now() + timedelta(days=25)).isoformat(),
            # missing scheduled_end and reason
        }
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Appointment.objects.count(), initial_count)

    def test_invalid_datetime_format_rejected(self):
        """Malformed datetime string returns 400."""
        self.client.force_authenticate(user=self.patient_1)
        initial_count = Appointment.objects.count()
        payload = {
            'doctor': str(self.doctor_1.id),
            'scheduled_start': 'not-a-valid-date',
            'scheduled_end': 'also-not-a-date',
            'reason': 'Checkup',
        }
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Appointment.objects.count(), initial_count)

    def test_end_time_before_start_time_rejected(self):
        """Scheduled end before or equal to scheduled start is rejected."""
        self.client.force_authenticate(user=self.patient_1)
        start = timezone.now() + timedelta(days=26, hours=12)
        end = timezone.now() + timedelta(days=26, hours=11)  # 1 hour before start
        payload = {
            'doctor': str(self.doctor_1.id),
            'scheduled_start': start.isoformat(),
            'scheduled_end': end.isoformat(),
            'reason': 'Reversed time appointment',
        }
        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('scheduled_end', self.get_error_details(response))
        self.assertEqual(Appointment.objects.count(), initial_count)

    def test_doctor_time_conflict_rejected(self):
        """Doctor cannot be double-booked in an overlapping time window."""
        self.client.force_authenticate(user=self.patient_2)
        # appointment_1 is doctor_1 at days=2, 09:00 - 10:00
        conflict_start = self.appointment_1.scheduled_start + timedelta(minutes=15)
        conflict_end = self.appointment_1.scheduled_end + timedelta(minutes=15)
        payload = {
            'doctor': str(self.doctor_1.id),
            'scheduled_start': conflict_start.isoformat(),
            'scheduled_end': conflict_end.isoformat(),
            'reason': 'Conflicting appointment attempt',
        }
        initial_count = Appointment.objects.count()
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Appointment.objects.count(), initial_count)


class AppointmentLifecycleActionValidationTests(BaseAppointmentTestCase):
    """
    Feature 4B: Validate appointment lifecycle actions (confirm, cancel, complete).

    Requirements:
    - confirm: only pending -> confirmed.
    - cancel: only pending or confirmed -> cancelled.
    - complete: only confirmed -> completed.
    - Invalid or repeated transitions return HTTP 409 without changing stored fields, including updated_at.
    - Preserve current role restrictions and participant-scoped access.
    - Validate payloads before writes:
        - confirm/complete accept only empty objects or genuinely bodyless requests.
        - cancel accepts only an optional cancellation_reason string; allow blank, reject null and structured values.
        - Reject unknown fields and non-object JSON, including explicit null and "", with HTTP 400.
    - Perform each transition inside transaction.atomic(), locking with select_for_update() and checking status under lock.
    - Preserve unrelated fields.
    """

    # =========================================================================
    # 1. Transition Matrix: confirm (only pending -> confirmed)
    # =========================================================================

    def test_confirm_valid_transition_pending_to_confirmed(self):
        """confirm permits pending -> confirmed."""
        self.client.force_authenticate(user=self.doctor_1)
        self.assertEqual(self.appointment_1.status, 'pending')

        res = self.client.post(self.confirm_url(self.appointment_1.id))
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'confirmed')
        self.assertEqual(res.data['status'], 'confirmed')

    def test_confirm_repeated_and_invalid_transitions_return_409_without_mutation(self):
        """confirm rejects confirmed (repeated), cancelled, completed, and no_show with 409 without modifying state."""
        self.client.force_authenticate(user=self.doctor_1)

        invalid_statuses = ['confirmed', 'cancelled', 'completed', 'no_show']
        for invalid_status in invalid_statuses:
            with self.subTest(status=invalid_status):
                self.appointment_1.status = invalid_status
                self.appointment_1.notes = f'Notes before confirm on {invalid_status}'
                self.appointment_1.save()
                self.appointment_1.refresh_from_db()
                initial_updated_at = self.appointment_1.updated_at

                res = self.client.post(self.confirm_url(self.appointment_1.id))
                self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
                self.assertIn('Cannot confirm appointment', str(res.data))

                self.appointment_1.refresh_from_db()
                self.assertEqual(self.appointment_1.status, invalid_status)
                self.assertEqual(self.appointment_1.updated_at, initial_updated_at)
                self.assertEqual(self.appointment_1.notes, f'Notes before confirm on {invalid_status}')

    # =========================================================================
    # 2. Transition Matrix: cancel (only pending or confirmed -> cancelled)
    # =========================================================================

    def test_cancel_valid_transition_from_pending(self):
        """cancel permits pending -> cancelled."""
        self.client.force_authenticate(user=self.patient_1)
        self.assertEqual(self.appointment_1.status, 'pending')

        res = self.client.post(
            self.cancel_url(self.appointment_1.id),
            {'cancellation_reason': 'Patient schedule conflict'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'cancelled')
        self.assertEqual(self.appointment_1.cancellation_reason, 'Patient schedule conflict')
        self.assertEqual(res.data['status'], 'cancelled')

    def test_cancel_valid_transition_from_confirmed(self):
        """cancel permits confirmed -> cancelled."""
        self.appointment_1.status = 'confirmed'
        self.appointment_1.save()

        self.client.force_authenticate(user=self.doctor_1)
        res = self.client.post(
            self.cancel_url(self.appointment_1.id),
            {'cancellation_reason': 'Doctor emergency'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'cancelled')
        self.assertEqual(self.appointment_1.cancellation_reason, 'Doctor emergency')

    def test_cancel_repeated_and_invalid_transitions_return_409_without_mutation(self):
        """cancel rejects cancelled (repeated), completed, and no_show with 409 without modifying state."""
        self.client.force_authenticate(user=self.patient_1)

        invalid_statuses = ['cancelled', 'completed', 'no_show']
        for invalid_status in invalid_statuses:
            with self.subTest(status=invalid_status):
                self.appointment_1.status = invalid_status
                self.appointment_1.cancellation_reason = 'Original reason'
                self.appointment_1.save()
                self.appointment_1.refresh_from_db()
                initial_updated_at = self.appointment_1.updated_at

                res = self.client.post(
                    self.cancel_url(self.appointment_1.id),
                    {'cancellation_reason': 'New reason should be rejected'},
                    format='json',
                )
                self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
                self.assertIn('Cannot cancel appointment', str(res.data))

                self.appointment_1.refresh_from_db()
                self.assertEqual(self.appointment_1.status, invalid_status)
                self.assertEqual(self.appointment_1.updated_at, initial_updated_at)
                self.assertEqual(self.appointment_1.cancellation_reason, 'Original reason')

    # =========================================================================
    # 3. Transition Matrix: complete (only confirmed -> completed)
    # =========================================================================

    def test_complete_valid_transition_from_confirmed(self):
        """complete permits confirmed -> completed."""
        self.appointment_1.status = 'confirmed'
        self.appointment_1.save()

        self.client.force_authenticate(user=self.doctor_1)
        res = self.client.post(self.complete_url(self.appointment_1.id))
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'completed')
        self.assertEqual(res.data['status'], 'completed')

    def test_complete_repeated_and_invalid_transitions_return_409_without_mutation(self):
        """complete rejects pending, completed (repeated), cancelled, and no_show with 409 without modifying state."""
        self.client.force_authenticate(user=self.doctor_1)

        invalid_statuses = ['pending', 'completed', 'cancelled', 'no_show']
        for invalid_status in invalid_statuses:
            with self.subTest(status=invalid_status):
                self.appointment_1.status = invalid_status
                self.appointment_1.notes = f'Notes before complete on {invalid_status}'
                self.appointment_1.save()
                self.appointment_1.refresh_from_db()
                initial_updated_at = self.appointment_1.updated_at

                res = self.client.post(self.complete_url(self.appointment_1.id))
                self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
                self.assertIn('Cannot complete appointment', str(res.data))

                self.appointment_1.refresh_from_db()
                self.assertEqual(self.appointment_1.status, invalid_status)
                self.assertEqual(self.appointment_1.updated_at, initial_updated_at)
                self.assertEqual(self.appointment_1.notes, f'Notes before complete on {invalid_status}')

    # =========================================================================
    # 4. Payload Validation: confirm and complete
    # =========================================================================

    def test_confirm_and_complete_accept_empty_object_and_bodyless(self):
        """confirm and complete accept empty object and bodyless requests."""
        self.client.force_authenticate(user=self.doctor_1)

        # Bodyless confirm
        res1 = self.client.post(self.confirm_url(self.appointment_1.id))
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'confirmed')

        # Empty object complete
        res2 = self.client.post(self.complete_url(self.appointment_1.id), data={}, format='json')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'completed')

    def test_confirm_and_complete_reject_unexpected_fields(self):
        """confirm and complete reject unexpected fields with 400 Bad Request."""
        self.client.force_authenticate(user=self.doctor_1)

        # confirm with extra field
        res1 = self.client.post(
            self.confirm_url(self.appointment_1.id),
            data={'unexpected_field': 'value'},
            format='json',
        )
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'pending')

        # Prepare confirmed appointment for complete test
        self.appointment_1.status = 'confirmed'
        self.appointment_1.save()

        # complete with extra field
        res2 = self.client.post(
            self.complete_url(self.appointment_1.id),
            data={'cancellation_reason': 'not allowed here'},
            format='json',
        )
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'confirmed')

    def test_confirm_and_complete_reject_non_object_json(self):
        """confirm and complete reject explicit null, empty string, list, and primitives with 400."""
        self.client.force_authenticate(user=self.doctor_1)

        # 1. confirm with explicit 'null'
        res1 = self.client.post(
            self.confirm_url(self.appointment_1.id),
            data='null',
            content_type='application/json',
        )
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)

        # 2. confirm with explicit '""'
        res2 = self.client.post(
            self.confirm_url(self.appointment_1.id),
            data='""',
            content_type='application/json',
        )
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. confirm with array '[]'
        res3 = self.client.post(
            self.confirm_url(self.appointment_1.id),
            data='[]',
            content_type='application/json',
        )
        self.assertEqual(res3.status_code, status.HTTP_400_BAD_REQUEST)

        # 4. confirm with number '123'
        res4 = self.client.post(
            self.confirm_url(self.appointment_1.id),
            data='123',
            content_type='application/json',
        )
        self.assertEqual(res4.status_code, status.HTTP_400_BAD_REQUEST)

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'pending')

        # Test same on complete
        self.appointment_1.status = 'confirmed'
        self.appointment_1.save()

        res5 = self.client.post(
            self.complete_url(self.appointment_1.id),
            data='null',
            content_type='application/json',
        )
        self.assertEqual(res5.status_code, status.HTTP_400_BAD_REQUEST)

        res6 = self.client.post(
            self.complete_url(self.appointment_1.id),
            data='""',
            content_type='application/json',
        )
        self.assertEqual(res6.status_code, status.HTTP_400_BAD_REQUEST)

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'confirmed')

    # =========================================================================
    # 5. Payload Validation: cancel
    # =========================================================================

    def test_cancel_accepts_valid_string_and_blank_and_omitted(self):
        """cancel accepts optional cancellation_reason string, blank string, and omitted reason."""
        self.client.force_authenticate(user=self.patient_1)

        # 1. Blank string
        res1 = self.client.post(
            self.cancel_url(self.appointment_1.id),
            data={'cancellation_reason': ''},
            format='json',
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'cancelled')
        self.assertEqual(self.appointment_1.cancellation_reason, '')

        # Reset appointment
        self.appointment_1.status = 'pending'
        self.appointment_1.save()

        # 2. Omitted / empty object
        res2 = self.client.post(
            self.cancel_url(self.appointment_1.id),
            data={},
            format='json',
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'cancelled')

        # Reset appointment
        self.appointment_1.status = 'pending'
        self.appointment_1.save()

        # 3. Bodyless request
        res3 = self.client.post(self.cancel_url(self.appointment_1.id))
        self.assertEqual(res3.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'cancelled')

    def test_cancel_accepts_multipart_form_data(self):
        """cancel accepts multipart/form-data with or without cancellation_reason."""
        self.client.force_authenticate(user=self.patient_1)

        res = self.client.post(
            self.cancel_url(self.appointment_1.id),
            data={'cancellation_reason': 'Multipart cancelled reason'},
            format='multipart',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'cancelled')
        self.assertEqual(self.appointment_1.cancellation_reason, 'Multipart cancelled reason')

    def test_cancel_rejects_explicit_null_and_structured_values(self):
        """cancel rejects null, list, dict, bool, and numeric cancellation_reason with 400."""
        self.client.force_authenticate(user=self.patient_1)

        invalid_reasons = [
            None,
            ['array', 'of', 'reasons'],
            {'reason': 'nested object'},
            12345,
            True,
            False,
        ]

        for invalid_reason in invalid_reasons:
            with self.subTest(reason=invalid_reason):
                res = self.client.post(
                    self.cancel_url(self.appointment_1.id),
                    data={'cancellation_reason': invalid_reason},
                    format='json',
                )
                self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('cancellation_reason', self.get_error_details(res))
                self.appointment_1.refresh_from_db()
                self.assertEqual(self.appointment_1.status, 'pending')

    def test_cancel_rejects_unknown_fields_and_non_object_json(self):
        """cancel rejects unexpected fields, explicit 'null', '\"\"', and arrays with 400."""
        self.client.force_authenticate(user=self.patient_1)

        # 1. Unexpected extra field alongside cancellation_reason
        res_extra = self.client.post(
            self.cancel_url(self.appointment_1.id),
            data={'cancellation_reason': 'Valid reason', 'extra_field': 'not allowed'},
            format='json',
        )
        self.assertEqual(res_extra.status_code, status.HTTP_400_BAD_REQUEST)

        # 2. Only unexpected field
        res_unknown = self.client.post(
            self.cancel_url(self.appointment_1.id),
            data={'notes': 'some notes'},
            format='json',
        )
        self.assertEqual(res_unknown.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. Explicit 'null' JSON
        res_null = self.client.post(
            self.cancel_url(self.appointment_1.id),
            data='null',
            content_type='application/json',
        )
        self.assertEqual(res_null.status_code, status.HTTP_400_BAD_REQUEST)

        # 4. Explicit '""' JSON
        res_empty_str = self.client.post(
            self.cancel_url(self.appointment_1.id),
            data='""',
            content_type='application/json',
        )
        self.assertEqual(res_empty_str.status_code, status.HTTP_400_BAD_REQUEST)

        # 5. Array JSON
        res_arr = self.client.post(
            self.cancel_url(self.appointment_1.id),
            data='[]',
            content_type='application/json',
        )
        self.assertEqual(res_arr.status_code, status.HTTP_400_BAD_REQUEST)

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'pending')

    # =========================================================================
    # 5b. Cancellation Reason Omission & Stored Reason Preservation Regressions
    # =========================================================================

    def test_cancel_with_omitted_reason_preserves_stored_cancellation_reason(self):
        """JSON {}, empty multipart, and bodyless cancellation preserve non-empty stored reason."""
        self.client.force_authenticate(user=self.patient_1)

        # 1. JSON {} preserves stored reason
        self.appointment_1.status = 'pending'
        self.appointment_1.cancellation_reason = 'Original prior reason'
        self.appointment_1.save()

        res1 = self.client.post(
            self.cancel_url(self.appointment_1.id),
            data={},
            format='json',
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'cancelled')
        self.assertEqual(self.appointment_1.cancellation_reason, 'Original prior reason')
        self.assertEqual(res1.data['cancellation_reason'], 'Original prior reason')

        # 2. Empty multipart preserves stored reason
        self.appointment_1.status = 'confirmed'
        self.appointment_1.cancellation_reason = 'Original prior reason'
        self.appointment_1.save()

        res2 = self.client.post(
            self.cancel_url(self.appointment_1.id),
            data={},
            format='multipart',
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'cancelled')
        self.assertEqual(self.appointment_1.cancellation_reason, 'Original prior reason')
        self.assertEqual(res2.data['cancellation_reason'], 'Original prior reason')

        # 3. Bodyless cancellation preserves stored reason
        self.appointment_1.status = 'pending'
        self.appointment_1.cancellation_reason = 'Original prior reason'
        self.appointment_1.save()

        res3 = self.client.post(self.cancel_url(self.appointment_1.id))
        self.assertEqual(res3.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'cancelled')
        self.assertEqual(self.appointment_1.cancellation_reason, 'Original prior reason')
        self.assertEqual(res3.data['cancellation_reason'], 'Original prior reason')

    def test_cancel_with_explicit_blank_clears_stored_cancellation_reason(self):
        """Explicit "" clears a non-empty stored cancellation_reason."""
        self.client.force_authenticate(user=self.patient_1)
        self.appointment_1.status = 'pending'
        self.appointment_1.cancellation_reason = 'Prior reason to be cleared'
        self.appointment_1.save()

        res = self.client.post(
            self.cancel_url(self.appointment_1.id),
            data={'cancellation_reason': ''},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'cancelled')
        self.assertEqual(self.appointment_1.cancellation_reason, '')
        self.assertEqual(res.data['cancellation_reason'], '')

    def test_cancel_with_explicit_text_replaces_stored_cancellation_reason(self):
        """Explicit non-empty text replaces a non-empty stored cancellation_reason."""
        self.client.force_authenticate(user=self.patient_1)
        self.appointment_1.status = 'confirmed'
        self.appointment_1.cancellation_reason = 'Old reason'
        self.appointment_1.save()

        res = self.client.post(
            self.cancel_url(self.appointment_1.id),
            data={'cancellation_reason': 'Brand new cancellation reason'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'cancelled')
        self.assertEqual(self.appointment_1.cancellation_reason, 'Brand new cancellation reason')
        self.assertEqual(res.data['cancellation_reason'], 'Brand new cancellation reason')

    def test_cancel_invalid_payloads_and_transitions_preserve_entire_row(self):
        """Invalid payloads and invalid transitions preserve the entire row starting with a non-empty stored reason."""
        self.client.force_authenticate(user=self.patient_1)
        self.appointment_1.status = 'pending'
        self.appointment_1.reason = 'Headache check'
        self.appointment_1.cancellation_reason = 'Stored active reason'
        self.appointment_1.notes = 'Pre-existing clinical notes'
        self.appointment_1.symptoms = 'Throbbing headache'
        self.appointment_1.meeting_link = 'https://telehealth.local/meet/123'
        self.appointment_1.save()
        self.appointment_1.refresh_from_db()
        initial_updated_at = self.appointment_1.updated_at

        # 1. Invalid payload: extra unknown fields -> 400
        res1 = self.client.post(
            self.cancel_url(self.appointment_1.id),
            data={'cancellation_reason': 'New reason', 'extra_field': 'malicious'},
            format='json',
        )
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'pending')
        self.assertEqual(self.appointment_1.cancellation_reason, 'Stored active reason')
        self.assertEqual(self.appointment_1.notes, 'Pre-existing clinical notes')
        self.assertEqual(self.appointment_1.symptoms, 'Throbbing headache')
        self.assertEqual(self.appointment_1.reason, 'Headache check')
        self.assertEqual(self.appointment_1.meeting_link, 'https://telehealth.local/meet/123')
        self.assertEqual(self.appointment_1.updated_at, initial_updated_at)

        # 2. Invalid payload: non-string (numeric, null, structured) -> 400
        for bad_val in [None, 1234, {'key': 'val'}, ['list']]:
            res = self.client.post(
                self.cancel_url(self.appointment_1.id),
                data={'cancellation_reason': bad_val},
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.appointment_1.refresh_from_db()
            self.assertEqual(self.appointment_1.status, 'pending')
            self.assertEqual(self.appointment_1.cancellation_reason, 'Stored active reason')
            self.assertEqual(self.appointment_1.updated_at, initial_updated_at)

        # 3. Invalid payload: non-object JSON ("" or "null" or "[]") -> 400
        for bad_body in ['""', 'null', '[]']:
            res = self.client.post(
                self.cancel_url(self.appointment_1.id),
                data=bad_body,
                content_type='application/json',
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.appointment_1.refresh_from_db()
            self.assertEqual(self.appointment_1.status, 'pending')
            self.assertEqual(self.appointment_1.cancellation_reason, 'Stored active reason')
            self.assertEqual(self.appointment_1.updated_at, initial_updated_at)

        # 4. Invalid transition: completed appointment cannot be cancelled -> 409
        self.appointment_1.status = 'completed'
        self.appointment_1.save()
        self.appointment_1.refresh_from_db()
        completed_updated_at = self.appointment_1.updated_at

        res_trans1 = self.client.post(
            self.cancel_url(self.appointment_1.id),
            data={'cancellation_reason': 'Attempt to cancel completed'},
            format='json',
        )
        self.assertEqual(res_trans1.status_code, status.HTTP_409_CONFLICT)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'completed')
        self.assertEqual(self.appointment_1.cancellation_reason, 'Stored active reason')
        self.assertEqual(self.appointment_1.notes, 'Pre-existing clinical notes')
        self.assertEqual(self.appointment_1.symptoms, 'Throbbing headache')
        self.assertEqual(self.appointment_1.reason, 'Headache check')
        self.assertEqual(self.appointment_1.meeting_link, 'https://telehealth.local/meet/123')
        self.assertEqual(self.appointment_1.updated_at, completed_updated_at)

        # 5. Invalid transition: cancelled appointment cannot be cancelled again -> 409
        self.appointment_1.status = 'cancelled'
        self.appointment_1.save()
        self.appointment_1.refresh_from_db()
        cancelled_updated_at = self.appointment_1.updated_at

        res_trans2 = self.client.post(
            self.cancel_url(self.appointment_1.id),
            data={},
            format='json',
        )
        self.assertEqual(res_trans2.status_code, status.HTTP_409_CONFLICT)
        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'cancelled')
        self.assertEqual(self.appointment_1.cancellation_reason, 'Stored active reason')
        self.assertEqual(self.appointment_1.notes, 'Pre-existing clinical notes')
        self.assertEqual(self.appointment_1.symptoms, 'Throbbing headache')
        self.assertEqual(self.appointment_1.reason, 'Headache check')
        self.assertEqual(self.appointment_1.meeting_link, 'https://telehealth.local/meet/123')
        self.assertEqual(self.appointment_1.updated_at, cancelled_updated_at)

    # =========================================================================
    # 6. Preserved Role Restrictions & Participant-Scoped Access
    # =========================================================================

    def test_confirm_action_role_restrictions(self):
        """confirm is restricted to assigned doctor and admin; patient, unassigned doctor, and nurse denied."""
        # Patient cannot confirm (403)
        self.client.force_authenticate(user=self.patient_1)
        self.assertEqual(self.client.post(self.confirm_url(self.appointment_1.id)).status_code, status.HTTP_403_FORBIDDEN)

        # Unassigned Doctor 2 receives 404 (participant scoping)
        self.client.force_authenticate(user=self.doctor_2)
        self.assertEqual(self.client.post(self.confirm_url(self.appointment_1.id)).status_code, status.HTTP_404_NOT_FOUND)

        # Nurse receives 403
        self.client.force_authenticate(user=self.nurse)
        self.assertEqual(self.client.post(self.confirm_url(self.appointment_1.id)).status_code, status.HTTP_403_FORBIDDEN)

        # Unauthenticated receives 401
        self.client.logout()
        self.assertEqual(self.client.post(self.confirm_url(self.appointment_1.id)).status_code, status.HTTP_401_UNAUTHORIZED)

        # Admin can confirm any appointment (200)
        self.client.force_authenticate(user=self.admin)
        res_admin = self.client.post(self.confirm_url(self.appointment_1.id))
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)

    def test_cancel_action_role_restrictions(self):
        """cancel permits assigned patient, assigned doctor, and admin; unassigned participants receive 404."""
        # Unassigned patient receives 404
        self.client.force_authenticate(user=self.patient_2)
        self.assertEqual(self.client.post(self.cancel_url(self.appointment_1.id)).status_code, status.HTTP_404_NOT_FOUND)

        # Unassigned doctor receives 404
        self.client.force_authenticate(user=self.doctor_2)
        self.assertEqual(self.client.post(self.cancel_url(self.appointment_1.id)).status_code, status.HTTP_404_NOT_FOUND)

        # Nurse receives 403
        self.client.force_authenticate(user=self.nurse)
        self.assertEqual(self.client.post(self.cancel_url(self.appointment_1.id)).status_code, status.HTTP_403_FORBIDDEN)

        # Assigned patient can cancel (200)
        self.client.force_authenticate(user=self.patient_1)
        res_pat = self.client.post(self.cancel_url(self.appointment_1.id))
        self.assertEqual(res_pat.status_code, status.HTTP_200_OK)

    def test_complete_action_role_restrictions(self):
        """complete is restricted to assigned doctor and admin; patient and unassigned doctor denied."""
        self.appointment_1.status = 'confirmed'
        self.appointment_1.save()

        # Patient cannot complete (403)
        self.client.force_authenticate(user=self.patient_1)
        self.assertEqual(self.client.post(self.complete_url(self.appointment_1.id)).status_code, status.HTTP_403_FORBIDDEN)

        # Unassigned doctor receives 404
        self.client.force_authenticate(user=self.doctor_2)
        self.assertEqual(self.client.post(self.complete_url(self.appointment_1.id)).status_code, status.HTTP_404_NOT_FOUND)

        # Assigned doctor can complete (200)
        self.client.force_authenticate(user=self.doctor_1)
        res_doc = self.client.post(self.complete_url(self.appointment_1.id))
        self.assertEqual(res_doc.status_code, status.HTTP_200_OK)

    # =========================================================================
    # 7. Preserve Unrelated Fields
    # =========================================================================

    def test_transitions_preserve_all_unrelated_fields(self):
        """confirm, cancel, and complete preserve all unrelated fields on Appointment."""
        self.appointment_1.reason = 'Preserved Reason'
        self.appointment_1.notes = 'Preserved Notes'
        self.appointment_1.symptoms = ['cough', 'fever']
        self.appointment_1.meeting_link = 'https://telemed.example.com/rooms/test-room'
        self.appointment_1.save()

        # 1. confirm preserves fields
        self.client.force_authenticate(user=self.doctor_1)
        res_confirm = self.client.post(self.confirm_url(self.appointment_1.id))
        self.assertEqual(res_confirm.status_code, status.HTTP_200_OK)

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.reason, 'Preserved Reason')
        self.assertEqual(self.appointment_1.notes, 'Preserved Notes')
        self.assertEqual(self.appointment_1.symptoms, ['cough', 'fever'])
        self.assertEqual(self.appointment_1.meeting_link, 'https://telemed.example.com/rooms/test-room')
        self.assertEqual(self.appointment_1.patient, self.patient_1)
        self.assertEqual(self.appointment_1.doctor, self.doctor_1)

        # 2. cancel preserves fields
        res_cancel = self.client.post(
            self.cancel_url(self.appointment_1.id),
            {'cancellation_reason': 'Patient emergency'},
            format='json',
        )
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.reason, 'Preserved Reason')
        self.assertEqual(self.appointment_1.notes, 'Preserved Notes')
        self.assertEqual(self.appointment_1.symptoms, ['cough', 'fever'])
        self.assertEqual(self.appointment_1.meeting_link, 'https://telemed.example.com/rooms/test-room')
        self.assertEqual(self.appointment_1.cancellation_reason, 'Patient emergency')


class DoctorAvailabilitySecurityTests(BaseAppointmentTestCase):
    """
    Tests for Feature 4C: Secure doctor availability ownership and access.

    Covers:
    - Doctors can manage only their own availability, including inactive windows.
    - Doctor creation derives doctor from the caller before validation. Omission succeeds; conflicting doctor IDs return 400.
    - Admins can manage all availability, including inactive windows. Creation requires role='doctor'.
    - Doctor ownership is immutable after creation for every role. Accept unchanged values on PUT/PATCH.
    - Patients have read-only access to active availability. Inactive detail requests return 404.
    - Unsupported roles receive 403; unauthenticated callers receive 401.
    - Non-object payloads return 400 without database changes.
    - Preserve weekday validation, end_time > start_time, filtering, ordering, and existing duplicate-window validation.
    """

    def setUp(self):
        super().setUp()
        DoctorAvailability.objects.all().delete()

    def test_doctor_creation_derives_doctor_when_omitted(self):
        """Doctor creation derives doctor from caller when omitted."""
        self.client.force_authenticate(user=self.doctor_1)

        payload = {
            'weekday': 0,
            'start_time': '09:00:00',
            'end_time': '17:00:00',
        }
        res = self.client.post(self.availability_list_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(res.data['doctor']), str(self.doctor_1.id))

        avail = DoctorAvailability.objects.get(id=res.data['id'])
        self.assertEqual(avail.doctor, self.doctor_1)
        self.assertEqual(avail.weekday, 0)
        self.assertTrue(avail.is_active)

    def test_doctor_creation_succeeds_with_matching_doctor_id(self):
        """Doctor creation succeeds when supplying own doctor ID."""
        self.client.force_authenticate(user=self.doctor_1)

        payload = {
            'doctor': str(self.doctor_1.id),
            'weekday': 1,
            'start_time': '09:00:00',
            'end_time': '17:00:00',
        }
        res = self.client.post(self.availability_list_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(res.data['doctor']), str(self.doctor_1.id))

        avail = DoctorAvailability.objects.get(id=res.data['id'])
        self.assertEqual(avail.doctor, self.doctor_1)

    def test_doctor_creation_rejects_conflicting_doctor_id_spoofing(self):
        """Doctor creation rejects conflicting doctor ID with 400 and does not write to DB."""
        initial_count = DoctorAvailability.objects.count()
        self.client.force_authenticate(user=self.doctor_1)

        payload = {
            'doctor': str(self.doctor_2.id),
            'weekday': 2,
            'start_time': '09:00:00',
            'end_time': '17:00:00',
        }
        res = self.client.post(self.availability_list_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(res))
        self.assertEqual(DoctorAvailability.objects.count(), initial_count)

    def test_admin_creation_requires_doctor_field(self):
        """Admin creation requires doctor field in payload."""
        initial_count = DoctorAvailability.objects.count()
        self.client.force_authenticate(user=self.admin)

        # Omitted doctor
        payload = {
            'weekday': 0,
            'start_time': '08:00:00',
            'end_time': '12:00:00',
        }
        res = self.client.post(self.availability_list_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(res))
        self.assertEqual(DoctorAvailability.objects.count(), initial_count)

        # Blank doctor
        payload['doctor'] = ''
        res2 = self.client.post(self.availability_list_url, payload, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(res2))
        self.assertEqual(DoctorAvailability.objects.count(), initial_count)

    def test_admin_creation_validates_doctor_role(self):
        """Admin creation requires that the specified user has role='doctor'."""
        initial_count = DoctorAvailability.objects.count()
        self.client.force_authenticate(user=self.admin)

        # 1. Specifying a patient user
        res1 = self.client.post(
            self.availability_list_url,
            {
                'doctor': str(self.patient_1.id),
                'weekday': 0,
                'start_time': '08:00:00',
                'end_time': '12:00:00',
            },
            format='json',
        )
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Selected user must be a doctor', str(self.get_error_details(res1)))

        # 2. Specifying a nurse user
        res2 = self.client.post(
            self.availability_list_url,
            {
                'doctor': str(self.nurse.id),
                'weekday': 0,
                'start_time': '08:00:00',
                'end_time': '12:00:00',
            },
            format='json',
        )
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Selected user must be a doctor', str(self.get_error_details(res2)))

        # 3. Specifying an admin user
        res3 = self.client.post(
            self.availability_list_url,
            {
                'doctor': str(self.admin.id),
                'weekday': 0,
                'start_time': '08:00:00',
                'end_time': '12:00:00',
            },
            format='json',
        )
        self.assertEqual(res3.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Selected user must be a doctor', str(self.get_error_details(res3)))

        self.assertEqual(DoctorAvailability.objects.count(), initial_count)

    def test_admin_can_create_and_manage_all_availability_including_inactive(self):
        """Admin can create and manage availability for any doctor, including inactive windows."""
        self.client.force_authenticate(user=self.admin)

        # Create inactive window for doctor_1
        payload = {
            'doctor': str(self.doctor_1.id),
            'weekday': 4,
            'start_time': '08:00:00',
            'end_time': '12:00:00',
            'is_active': False,
        }
        res = self.client.post(self.availability_list_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        avail_id = res.data['id']
        self.assertFalse(res.data['is_active'])

        # Admin can retrieve inactive detail
        res_get = self.client.get(self.availability_detail_url(avail_id))
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        self.assertFalse(res_get.data['is_active'])

        # Admin sees inactive window in list
        res_list = self.client.get(self.availability_list_url)
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        results = res_list.data.get('results', res_list.data)
        ids = [str(r['id']) for r in results]
        self.assertIn(str(avail_id), ids)

        # Admin can update inactive window to active
        res_patch = self.client.patch(
            self.availability_detail_url(avail_id),
            {'is_active': True},
            format='json',
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertTrue(res_patch.data['is_active'])

        # Admin can delete window
        res_del = self.client.delete(self.availability_detail_url(avail_id))
        self.assertEqual(res_del.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(DoctorAvailability.objects.filter(id=avail_id).exists())

    def test_doctor_ownership_immutable_after_creation_for_doctor(self):
        """Doctor ownership is immutable after creation for doctor; accepts unchanged doctor."""
        avail = DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=1,
            start_time='09:00:00',
            end_time='17:00:00',
            is_active=True,
        )
        self.client.force_authenticate(user=self.doctor_1)

        # 1. PATCH with conflicting doctor returns 400
        res_patch_conflict = self.client.patch(
            self.availability_detail_url(avail.id),
            {'doctor': str(self.doctor_2.id)},
            format='json',
        )
        self.assertEqual(res_patch_conflict.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(res_patch_conflict))
        avail.refresh_from_db()
        self.assertEqual(avail.doctor, self.doctor_1)

        # 2. PUT with unchanged doctor succeeds
        res_put = self.client.put(
            self.availability_detail_url(avail.id),
            {
                'doctor': str(self.doctor_1.id),
                'weekday': 2,
                'start_time': '09:00:00',
                'end_time': '17:00:00',
                'is_active': True,
            },
            format='json',
        )
        self.assertEqual(res_put.status_code, status.HTTP_200_OK)
        avail.refresh_from_db()
        self.assertEqual(avail.weekday, 2)
        self.assertEqual(avail.doctor, self.doctor_1)

        # 3. PATCH with omitted doctor succeeds
        res_patch_ok = self.client.patch(
            self.availability_detail_url(avail.id),
            {'weekday': 3},
            format='json',
        )
        self.assertEqual(res_patch_ok.status_code, status.HTTP_200_OK)
        avail.refresh_from_db()
        self.assertEqual(avail.weekday, 3)
        self.assertEqual(avail.doctor, self.doctor_1)

    def test_doctor_ownership_immutable_after_creation_for_admin(self):
        """Doctor ownership is immutable after creation for admin; accepts unchanged doctor."""
        avail = DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=2,
            start_time='09:00:00',
            end_time='17:00:00',
            is_active=True,
        )
        self.client.force_authenticate(user=self.admin)

        # 1. PATCH with conflicting doctor returns 400
        res_patch = self.client.patch(
            self.availability_detail_url(avail.id),
            {'doctor': str(self.doctor_2.id)},
            format='json',
        )
        self.assertEqual(res_patch.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(res_patch))
        avail.refresh_from_db()
        self.assertEqual(avail.doctor, self.doctor_1)

        # 2. PUT with conflicting doctor returns 400
        res_put_bad = self.client.put(
            self.availability_detail_url(avail.id),
            {
                'doctor': str(self.doctor_2.id),
                'weekday': 2,
                'start_time': '09:00:00',
                'end_time': '17:00:00',
                'is_active': True,
            },
            format='json',
        )
        self.assertEqual(res_put_bad.status_code, status.HTTP_400_BAD_REQUEST)
        avail.refresh_from_db()
        self.assertEqual(avail.doctor, self.doctor_1)

        # 3. PUT with unchanged doctor succeeds
        res_put_ok = self.client.put(
            self.availability_detail_url(avail.id),
            {
                'doctor': str(self.doctor_1.id),
                'weekday': 4,
                'start_time': '09:00:00',
                'end_time': '17:00:00',
                'is_active': True,
            },
            format='json',
        )
        self.assertEqual(res_put_ok.status_code, status.HTTP_200_OK)
        avail.refresh_from_db()
        self.assertEqual(avail.weekday, 4)
        self.assertEqual(avail.doctor, self.doctor_1)

    def test_cross_doctor_access_boundaries(self):
        """Doctor 1 cannot view, edit, or delete Doctor 2's availability."""
        w1 = DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=1,
            start_time='09:00:00',
            end_time='12:00:00',
            is_active=True,
        )
        w2 = DoctorAvailability.objects.create(
            doctor=self.doctor_2,
            weekday=1,
            start_time='13:00:00',
            end_time='17:00:00',
            is_active=True,
        )

        self.client.force_authenticate(user=self.doctor_1)

        # List returns only doctor 1's windows
        res_list = self.client.get(self.availability_list_url)
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        results = res_list.data.get('results', res_list.data)
        ids = [str(r['id']) for r in results]
        self.assertIn(str(w1.id), ids)
        self.assertNotIn(str(w2.id), ids)

        # Detail GET on Doctor 2's window returns 404
        self.assertEqual(
            self.client.get(self.availability_detail_url(w2.id)).status_code,
            status.HTTP_404_NOT_FOUND,
        )

        # PATCH on Doctor 2's window returns 404
        self.assertEqual(
            self.client.patch(
                self.availability_detail_url(w2.id),
                {'weekday': 5},
                format='json',
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        w2.refresh_from_db()
        self.assertEqual(w2.weekday, 1)

        # DELETE on Doctor 2's window returns 404
        self.assertEqual(
            self.client.delete(self.availability_detail_url(w2.id)).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertTrue(DoctorAvailability.objects.filter(id=w2.id).exists())

    def test_doctor_can_manage_own_inactive_windows(self):
        """Doctors can view and manage their own inactive windows."""
        w = DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=2,
            start_time='10:00:00',
            end_time='14:00:00',
            is_active=False,
        )
        self.client.force_authenticate(user=self.doctor_1)

        # List includes own inactive window
        res_list = self.client.get(self.availability_list_url)
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        results = res_list.data.get('results', res_list.data)
        ids = [str(r['id']) for r in results]
        self.assertIn(str(w.id), ids)

        # Detail GET succeeds on own inactive window
        res_detail = self.client.get(self.availability_detail_url(w.id))
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertFalse(res_detail.data['is_active'])

        # Doctor can reactivate window
        res_patch = self.client.patch(
            self.availability_detail_url(w.id),
            {'is_active': True},
            format='json',
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        w.refresh_from_db()
        self.assertTrue(w.is_active)

    def test_patient_read_only_access_to_active_availability_only(self):
        """Patients have read-only access to active availability; inactive detail returns 404."""
        w_active = DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=1,
            start_time='09:00:00',
            end_time='12:00:00',
            is_active=True,
        )
        w_inactive = DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=1,
            start_time='13:00:00',
            end_time='17:00:00',
            is_active=False,
        )

        self.client.force_authenticate(user=self.patient_1)

        # List returns only active windows
        res_list = self.client.get(self.availability_list_url)
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        results = res_list.data.get('results', res_list.data)
        ids = [str(r['id']) for r in results]
        self.assertIn(str(w_active.id), ids)
        self.assertNotIn(str(w_inactive.id), ids)

        # Detail GET on active window succeeds
        res_detail = self.client.get(self.availability_detail_url(w_active.id))
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertTrue(res_detail.data['is_active'])

        # Detail GET on inactive window returns 404
        res_inactive = self.client.get(self.availability_detail_url(w_inactive.id))
        self.assertEqual(res_inactive.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_write_requests_denied_with_403(self):
        """Patient write requests (create, update, delete) return 403 Forbidden without DB changes."""
        w = DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=1,
            start_time='09:00:00',
            end_time='12:00:00',
            is_active=True,
        )
        initial_count = DoctorAvailability.objects.count()

        self.client.force_authenticate(user=self.patient_1)

        # 1. POST create
        res_post = self.client.post(
            self.availability_list_url,
            {'weekday': 2, 'start_time': '09:00:00', 'end_time': '12:00:00'},
            format='json',
        )
        self.assertEqual(res_post.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(DoctorAvailability.objects.count(), initial_count)

        # 2. PUT update
        res_put = self.client.put(
            self.availability_detail_url(w.id),
            {'weekday': 2, 'start_time': '09:00:00', 'end_time': '12:00:00', 'is_active': True},
            format='json',
        )
        self.assertEqual(res_put.status_code, status.HTTP_403_FORBIDDEN)
        w.refresh_from_db()
        self.assertEqual(w.weekday, 1)

        # 3. PATCH partial update
        res_patch = self.client.patch(
            self.availability_detail_url(w.id),
            {'weekday': 3},
            format='json',
        )
        self.assertEqual(res_patch.status_code, status.HTTP_403_FORBIDDEN)
        w.refresh_from_db()
        self.assertEqual(w.weekday, 1)

        # 4. DELETE
        res_del = self.client.delete(self.availability_detail_url(w.id))
        self.assertEqual(res_del.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(DoctorAvailability.objects.filter(id=w.id).exists())

    def test_unsupported_roles_and_unauthenticated_callers(self):
        """Unauthenticated callers receive 401; unsupported roles receive 403."""
        w = DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=1,
            start_time='09:00:00',
            end_time='12:00:00',
            is_active=True,
        )

        # 1. Unauthenticated (401)
        self.client.logout()
        self.assertEqual(self.client.get(self.availability_list_url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get(self.availability_detail_url(w.id)).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            self.client.post(self.availability_list_url, {'weekday': 1}, format='json').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(self.client.delete(self.availability_detail_url(w.id)).status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Unsupported role: Nurse (403)
        self.client.force_authenticate(user=self.nurse)
        self.assertEqual(self.client.get(self.availability_list_url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(self.availability_detail_url(w.id)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.post(self.availability_list_url, {'weekday': 1}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.delete(self.availability_detail_url(w.id)).status_code, status.HTTP_403_FORBIDDEN)

    def test_non_object_payloads_return_400_and_preserve_db(self):
        """Non-object payloads (strings, null, arrays, numbers) return 400 without DB changes."""
        w = DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=1,
            start_time='09:00:00',
            end_time='12:00:00',
            is_active=True,
        )
        initial_count = DoctorAvailability.objects.count()

        self.client.force_authenticate(user=self.doctor_1)

        bad_payloads = ['""', 'null', '[]', '123']
        for bad_body in bad_payloads:
            with self.subTest(action='create', body=bad_body):
                res = self.client.post(
                    self.availability_list_url,
                    data=bad_body,
                    content_type='application/json',
                )
                self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(DoctorAvailability.objects.count(), initial_count)

            with self.subTest(action='patch', body=bad_body):
                res = self.client.patch(
                    self.availability_detail_url(w.id),
                    data=bad_body,
                    content_type='application/json',
                )
                self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
                w.refresh_from_db()
                self.assertEqual(w.weekday, 1)

        # Admin PUT with non-object JSON
        self.client.force_authenticate(user=self.admin)
        for bad_body in bad_payloads:
            with self.subTest(action='admin_put', body=bad_body):
                res = self.client.put(
                    self.availability_detail_url(w.id),
                    data=bad_body,
                    content_type='application/json',
                )
                self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
                w.refresh_from_db()
                self.assertEqual(w.weekday, 1)

    def test_weekday_and_time_validation(self):
        """Preserve weekday choice validation and end_time > start_time validation."""
        self.client.force_authenticate(user=self.doctor_1)

        # 1. Invalid weekday (> 6)
        res1 = self.client.post(
            self.availability_list_url,
            {'weekday': 7, 'start_time': '09:00:00', 'end_time': '17:00:00'},
            format='json',
        )
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('weekday', self.get_error_details(res1))

        # 2. Invalid weekday (< 0)
        res2 = self.client.post(
            self.availability_list_url,
            {'weekday': -1, 'start_time': '09:00:00', 'end_time': '17:00:00'},
            format='json',
        )
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. end_time <= start_time (end before start)
        res3 = self.client.post(
            self.availability_list_url,
            {'weekday': 0, 'start_time': '17:00:00', 'end_time': '09:00:00'},
            format='json',
        )
        self.assertEqual(res3.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('end_time', self.get_error_details(res3))

        # 4. end_time == start_time (equal)
        res4 = self.client.post(
            self.availability_list_url,
            {'weekday': 0, 'start_time': '09:00:00', 'end_time': '09:00:00'},
            format='json',
        )
        self.assertEqual(res4.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('end_time', self.get_error_details(res4))

    def test_duplicate_window_validation(self):
        """Preserve unique_together duplicate window validation."""
        DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=0,
            start_time='09:00:00',
            end_time='17:00:00',
            is_active=True,
        )

        # Doctor 1 tries to create exact duplicate -> 400
        self.client.force_authenticate(user=self.doctor_1)
        res_dup = self.client.post(
            self.availability_list_url,
            {'weekday': 0, 'start_time': '09:00:00', 'end_time': '17:00:00'},
            format='json',
        )
        self.assertEqual(res_dup.status_code, status.HTTP_400_BAD_REQUEST)

        # Doctor 2 can create same weekday/time -> 201
        self.client.force_authenticate(user=self.doctor_2)
        res_doc2 = self.client.post(
            self.availability_list_url,
            {'weekday': 0, 'start_time': '09:00:00', 'end_time': '17:00:00'},
            format='json',
        )
        self.assertEqual(res_doc2.status_code, status.HTTP_201_CREATED)

        # Admin creating duplicate for Doctor 1 -> 400
        self.client.force_authenticate(user=self.admin)
        res_admin_dup = self.client.post(
            self.availability_list_url,
            {
                'doctor': str(self.doctor_1.id),
                'weekday': 0,
                'start_time': '09:00:00',
                'end_time': '17:00:00',
            },
            format='json',
        )
        self.assertEqual(res_admin_dup.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filtering_and_ordering(self):
        """Preserve filtering by doctor, weekday, is_active and ordering by weekday, start_time."""
        w1 = DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=4,
            start_time='10:00:00',
            end_time='14:00:00',
            is_active=True,
        )
        w2 = DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=1,
            start_time='09:00:00',
            end_time='12:00:00',
            is_active=True,
        )
        w3 = DoctorAvailability.objects.create(
            doctor=self.doctor_2,
            weekday=1,
            start_time='14:00:00',
            end_time='18:00:00',
            is_active=True,
        )

        self.client.force_authenticate(user=self.admin)

        # Filter by weekday=1
        res_weekday = self.client.get(self.availability_list_url + '?weekday=1')
        self.assertEqual(res_weekday.status_code, status.HTTP_200_OK)
        results = res_weekday.data.get('results', res_weekday.data)
        ids = [str(r['id']) for r in results]
        self.assertIn(str(w2.id), ids)
        self.assertIn(str(w3.id), ids)
        self.assertNotIn(str(w1.id), ids)

        # Filter by doctor=doctor_1
        res_doc = self.client.get(f'{self.availability_list_url}?doctor={self.doctor_1.id}')
        self.assertEqual(res_doc.status_code, status.HTTP_200_OK)
        results_doc = res_doc.data.get('results', res_doc.data)
        ids_doc = [str(r['id']) for r in results_doc]
        self.assertIn(str(w1.id), ids_doc)
        self.assertIn(str(w2.id), ids_doc)
        self.assertNotIn(str(w3.id), ids_doc)

        # Ordering by weekday, start_time: w2 (weekday 1, 09:00) before w1 (weekday 4, 10:00)
        idx_w2 = ids_doc.index(str(w2.id))
        idx_w1 = ids_doc.index(str(w1.id))
        self.assertLess(idx_w2, idx_w1)


class AppointmentReschedulingAndPastBookingTests(BaseAppointmentTestCase):
    """
    Tests for Feature 4D: Reject past bookings and protect appointment rescheduling.

    Covers:
    - New appointments must have scheduled_start strictly later than timezone.now().
    - Deterministic tests with a fixed clock for past/equal/future starts.
    - Preserve scheduled_end > scheduled_start and doctor-overlap validation.
    - Distinguish actual datetime changes from unchanged values on PUT/PATCH.
    - Allow datetime changes only while the appointment is pending.
    - Reject datetime changes on confirmed, completed, cancelled, or no_show appointments with 400.
    - Rescheduling must produce a future start time.
    - Partial updates using effective existing values.
    - Unchanged timestamps remain acceptable, including equivalent timestamps expressed with different UTC offsets.
    - Unrelated updates to historical appointments must not fail merely because their existing start time is in the past.
    - All rejected requests leave the database row unchanged.
    """

    FIXED_NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=dt_timezone.utc)

    def test_new_appointment_deterministic_past_equal_future_starts(self):
        """New appointments require scheduled_start strictly later than timezone.now()."""
        self.client.force_authenticate(user=self.patient_1)

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            # 1. Past start (1 minute before fixed now) -> 400
            initial_count = Appointment.objects.count()
            res_past = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': (self.FIXED_NOW - timedelta(minutes=1)).isoformat(),
                    'scheduled_end': (self.FIXED_NOW + timedelta(hours=1)).isoformat(),
                    'reason': 'Past booking attempt',
                },
                format='json',
            )
            self.assertEqual(res_past.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res_past))
            self.assertEqual(Appointment.objects.count(), initial_count)

            # 2. Equal start (exactly fixed now) -> 400 (must be strictly later)
            res_equal = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': self.FIXED_NOW.isoformat(),
                    'scheduled_end': (self.FIXED_NOW + timedelta(hours=1)).isoformat(),
                    'reason': 'Equal booking attempt',
                },
                format='json',
            )
            self.assertEqual(res_equal.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res_equal))
            self.assertEqual(Appointment.objects.count(), initial_count)

            # 3. Future start (1 minute strictly after fixed now) -> 201
            res_future = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': (self.FIXED_NOW + timedelta(minutes=1)).isoformat(),
                    'scheduled_end': (self.FIXED_NOW + timedelta(hours=1)).isoformat(),
                    'reason': 'Future booking success',
                },
                format='json',
            )
            self.assertEqual(res_future.status_code, status.HTTP_201_CREATED)
            self.assertEqual(Appointment.objects.count(), initial_count + 1)
            created_appt = Appointment.objects.get(id=res_future.data['id'])
            self.assertEqual(created_appt.status, 'pending')

    def test_rescheduling_deterministic_past_equal_future_starts(self):
        """Rescheduling requires a future start time strictly later than timezone.now()."""
        # Create pending appointment in the future relative to FIXED_NOW
        appt = Appointment.objects.create(
            patient=self.patient_1,
            doctor=self.doctor_1,
            scheduled_start=self.FIXED_NOW + timedelta(days=2),
            scheduled_end=self.FIXED_NOW + timedelta(days=2, hours=1),
            status='pending',
            reason='Original appointment',
        )
        appt.refresh_from_db()
        initial_updated_at = appt.updated_at

        self.client.force_authenticate(user=self.patient_1)

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            # 1. Reschedule to past start -> 400
            res_past = self.client.patch(
                self.detail_url(appt.id),
                {
                    'scheduled_start': (self.FIXED_NOW - timedelta(hours=1)).isoformat(),
                    'scheduled_end': (self.FIXED_NOW + timedelta(hours=1)).isoformat(),
                },
                format='json',
            )
            self.assertEqual(res_past.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res_past))
            appt.refresh_from_db()
            self.assertEqual(appt.scheduled_start, self.FIXED_NOW + timedelta(days=2))
            self.assertEqual(appt.updated_at, initial_updated_at)

            # 2. Reschedule to equal start -> 400
            res_equal = self.client.patch(
                self.detail_url(appt.id),
                {
                    'scheduled_start': self.FIXED_NOW.isoformat(),
                    'scheduled_end': (self.FIXED_NOW + timedelta(hours=1)).isoformat(),
                },
                format='json',
            )
            self.assertEqual(res_equal.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res_equal))
            appt.refresh_from_db()
            self.assertEqual(appt.scheduled_start, self.FIXED_NOW + timedelta(days=2))
            self.assertEqual(appt.updated_at, initial_updated_at)

            # 3. Reschedule to future start -> 200
            new_start = self.FIXED_NOW + timedelta(days=5)
            new_end = self.FIXED_NOW + timedelta(days=5, hours=1)
            res_future = self.client.patch(
                self.detail_url(appt.id),
                {
                    'scheduled_start': new_start.isoformat(),
                    'scheduled_end': new_end.isoformat(),
                },
                format='json',
            )
            self.assertEqual(res_future.status_code, status.HTTP_200_OK)
            appt.refresh_from_db()
            self.assertEqual(appt.scheduled_start, new_start)
            self.assertEqual(appt.scheduled_end, new_end)

    def test_rescheduling_rejected_on_non_pending_statuses(self):
        """Reject datetime changes on confirmed, completed, cancelled, or no_show appointments with 400."""
        self.client.force_authenticate(user=self.doctor_1)

        non_pending_statuses = ['confirmed', 'completed', 'cancelled', 'no_show']
        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            for bad_status in non_pending_statuses:
                with self.subTest(status=bad_status):
                    appt = Appointment.objects.create(
                        patient=self.patient_1,
                        doctor=self.doctor_1,
                        scheduled_start=self.FIXED_NOW + timedelta(days=2),
                        scheduled_end=self.FIXED_NOW + timedelta(days=2, hours=1),
                        status=bad_status,
                        reason=f'Appointment with {bad_status}',
                    )
                    appt.refresh_from_db()
                    initial_updated_at = appt.updated_at

                    # Attempt to reschedule start time to future
                    new_start = self.FIXED_NOW + timedelta(days=10)
                    new_end = self.FIXED_NOW + timedelta(days=10, hours=1)
                    res = self.client.patch(
                        self.detail_url(appt.id),
                        {
                            'scheduled_start': new_start.isoformat(),
                            'scheduled_end': new_end.isoformat(),
                        },
                        format='json',
                    )
                    self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
                    self.assertIn('Cannot reschedule', str(res.data))

                    # Verify row remains completely unchanged
                    appt.refresh_from_db()
                    self.assertEqual(appt.status, bad_status)
                    self.assertEqual(appt.scheduled_start, self.FIXED_NOW + timedelta(days=2))
                    self.assertEqual(appt.scheduled_end, self.FIXED_NOW + timedelta(days=2, hours=1))
                    self.assertEqual(appt.updated_at, initial_updated_at)

    def test_partial_updates_use_effective_existing_values(self):
        """Partial updates (PATCH) use effective existing values for validation."""
        self.client.force_authenticate(user=self.patient_1)

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            # Baseline: Day 2 from 13:00 to 14:00 (relative to FIXED_NOW 12:00)
            start_dt = self.FIXED_NOW + timedelta(days=2, hours=1)
            end_dt = self.FIXED_NOW + timedelta(days=2, hours=2)
            appt = Appointment.objects.create(
                patient=self.patient_1,
                doctor=self.doctor_1,
                scheduled_start=start_dt,
                scheduled_end=end_dt,
                status='pending',
            )

            # 1. Update only scheduled_start to 13:30 (valid since 13:30 < existing end 14:00)
            res1 = self.client.patch(
                self.detail_url(appt.id),
                {'scheduled_start': (start_dt + timedelta(minutes=30)).isoformat()},
                format='json',
            )
            self.assertEqual(res1.status_code, status.HTTP_200_OK)
            appt.refresh_from_db()
            self.assertEqual(appt.scheduled_start, start_dt + timedelta(minutes=30))
            self.assertEqual(appt.scheduled_end, end_dt)

            # 2. Update only scheduled_start to 15:00 (invalid since 15:00 >= existing end 14:00)
            res2 = self.client.patch(
                self.detail_url(appt.id),
                {'scheduled_start': (self.FIXED_NOW + timedelta(days=2, hours=3)).isoformat()},
                format='json',
            )
            self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_end', self.get_error_details(res2))
            appt.refresh_from_db()
            self.assertEqual(appt.scheduled_start, start_dt + timedelta(minutes=30))

            # 3. Update only scheduled_end to 15:00 (valid since 15:00 > existing start 13:30)
            res3 = self.client.patch(
                self.detail_url(appt.id),
                {'scheduled_end': (self.FIXED_NOW + timedelta(days=2, hours=3)).isoformat()},
                format='json',
            )
            self.assertEqual(res3.status_code, status.HTTP_200_OK)
            appt.refresh_from_db()
            self.assertEqual(appt.scheduled_end, self.FIXED_NOW + timedelta(days=2, hours=3))

            # 4. Partial update of scheduled_end on a pending appointment with past start time fails
            past_start = self.FIXED_NOW - timedelta(days=1)
            past_appt = Appointment.objects.create(
                patient=self.patient_1,
                doctor=self.doctor_1,
                scheduled_start=past_start,
                scheduled_end=past_start + timedelta(hours=1),
                status='pending',
            )
            res4 = self.client.patch(
                self.detail_url(past_appt.id),
                {'scheduled_end': (self.FIXED_NOW + timedelta(hours=2)).isoformat()},
                format='json',
            )
            self.assertEqual(res4.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res4))
            past_appt.refresh_from_db()
            self.assertEqual(past_appt.scheduled_start, past_start)

    def test_unchanged_timestamps_and_different_utc_offsets_accepted(self):
        """Unchanged timestamps are accepted, including different UTC offset representations."""
        # Baseline appointment
        start_utc = datetime(2026, 11, 10, 10, 0, 0, tzinfo=dt_timezone.utc)
        end_utc = datetime(2026, 11, 10, 11, 0, 0, tzinfo=dt_timezone.utc)

        # Confirmed appointment (where rescheduling would normally be rejected)
        appt = Appointment.objects.create(
            patient=self.patient_1,
            doctor=self.doctor_1,
            scheduled_start=start_utc,
            scheduled_end=end_utc,
            status='confirmed',
            reason='Original reason',
        )

        self.client.force_authenticate(user=self.doctor_1)

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            # Equivalent timestamp in UTC+05:30 (10:00 UTC == 15:30 +05:30)
            offset_start = '2026-11-10T15:30:00+05:30'
            offset_end = '2026-11-10T16:30:00+05:30'

            # Full PUT with offset-equivalent timestamps on confirmed appointment
            res_put = self.client.put(
                self.detail_url(appt.id),
                {
                    'patient': str(self.patient_1.id),
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': offset_start,
                    'scheduled_end': offset_end,
                    'reason': 'Updated reason with same time',
                },
                format='json',
            )
            self.assertEqual(res_put.status_code, status.HTTP_200_OK)
            appt.refresh_from_db()
            self.assertEqual(appt.scheduled_start, start_utc)
            self.assertEqual(appt.scheduled_end, end_utc)
            self.assertEqual(appt.reason, 'Updated reason with same time')
            self.assertEqual(appt.status, 'confirmed')

            # PATCH with same UTC representation
            res_patch = self.client.patch(
                self.detail_url(appt.id),
                {
                    'scheduled_start': start_utc.isoformat(),
                    'reason': 'Patched reason with same time',
                },
                format='json',
            )
            self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
            appt.refresh_from_db()
            self.assertEqual(appt.scheduled_start, start_utc)
            self.assertEqual(appt.reason, 'Patched reason with same time')

    def test_unrelated_updates_to_historical_appointments_succeed(self):
        """Unrelated updates to historical appointments do not fail merely because start is in past."""
        past_start = self.FIXED_NOW - timedelta(days=60)
        past_end = self.FIXED_NOW - timedelta(days=60, hours=-1)

        # Historical completed appointment
        hist_appt = Appointment.objects.create(
            patient=self.patient_1,
            doctor=self.doctor_1,
            scheduled_start=past_start,
            scheduled_end=past_end,
            status='completed',
            notes='Initial clinical notes',
        )

        self.client.force_authenticate(user=self.doctor_1)

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            # 1. PATCH unrelated field 'notes'
            res_patch = self.client.patch(
                self.detail_url(hist_appt.id),
                {'notes': 'Updated addendum to historical consultation'},
                format='json',
            )
            self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
            hist_appt.refresh_from_db()
            self.assertEqual(hist_appt.notes, 'Updated addendum to historical consultation')
            self.assertEqual(hist_appt.scheduled_start, past_start)
            self.assertEqual(hist_appt.status, 'completed')

            # 2. PUT with unchanged historical past timestamps
            res_put = self.client.put(
                self.detail_url(hist_appt.id),
                {
                    'patient': str(self.patient_1.id),
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': past_start.isoformat(),
                    'scheduled_end': past_end.isoformat(),
                    'notes': 'Final historical note',
                    'reason': 'Checkup',
                },
                format='json',
            )
            self.assertEqual(res_put.status_code, status.HTTP_200_OK)
            hist_appt.refresh_from_db()
            self.assertEqual(hist_appt.notes, 'Final historical note')
            self.assertEqual(hist_appt.scheduled_start, past_start)

    def test_doctor_conflict_and_end_after_start_validation_preserved(self):
        """Preserve scheduled_end > scheduled_start and doctor-overlap validation."""
        self.client.force_authenticate(user=self.doctor_1)

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            # 1. scheduled_end <= scheduled_start on creation
            res_end_before = self.client.post(
                self.list_url,
                {
                    'patient': str(self.patient_1.id),
                    'scheduled_start': (self.FIXED_NOW + timedelta(days=1, hours=2)).isoformat(),
                    'scheduled_end': (self.FIXED_NOW + timedelta(days=1, hours=1)).isoformat(),
                    'reason': 'Invalid end before start',
                },
                format='json',
            )
            self.assertEqual(res_end_before.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_end', self.get_error_details(res_end_before))

            # 2. Conflicting appointment window for doctor
            Appointment.objects.create(
                patient=self.patient_1,
                doctor=self.doctor_1,
                scheduled_start=self.FIXED_NOW + timedelta(days=3, hours=10),
                scheduled_end=self.FIXED_NOW + timedelta(days=3, hours=11),
                status='confirmed',
                reason='Existing confirmed booking',
            )

            # Try to book overlapping window for same doctor
            res_overlap = self.client.post(
                self.list_url,
                {
                    'patient': str(self.patient_2.id),
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': (self.FIXED_NOW + timedelta(days=3, hours=10, minutes=30)).isoformat(),
                    'scheduled_end': (self.FIXED_NOW + timedelta(days=3, hours=11, minutes=30)).isoformat(),
                    'reason': 'Overlapping booking',
                },
                format='json',
            )
            self.assertEqual(res_overlap.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('already has an appointment', str(res_overlap.data))


class AppointmentAvailabilityValidationTests(BaseAppointmentTestCase):
    """
    Tests for Feature 4E: Require bookings to fit active doctor availability.

    Covers:
    - Entire appointment must fit inside one active availability window belonging to its doctor.
    - Match weekday and times using Django's configured default timezone (settings.TIME_ZONE, currently UTC).
    - Allow exact window boundaries: appointment start >= window start and appointment end <= window end.
    - Reject missing availability, inactive windows, wrong weekday/doctor, and appointments extending outside a window.
    - Reject appointments crossing midnight in the configured timezone. Do not combine separate windows.
    - Apply same rules to patients, doctors, and admins.
    - Unrelated updates and unchanged timestamps must not revalidate availability on existing appointments.
    - Rejections return HTTP 400 without database changes.
    - Boundaries, gaps between windows, offset conversion across weekdays, partial rescheduling, unchanged historical edits.
    """

    FIXED_NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=dt_timezone.utc)  # Sunday 12:00:00 UTC

    def setUp(self):
        super().setUp()
        # Clear default all-day windows so availability validation tests control their exact setup
        DoctorAvailability.objects.all().delete()

    def test_exact_window_boundaries_succeeds(self):
        """Appointment start and end exactly matching active availability window boundaries succeeds."""
        # Window: Tuesday (1) 09:00:00 to 17:00:00
        DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=1,
            start_time=time(9, 0, 0),
            end_time=time(17, 0, 0),
            is_active=True,
        )

        self.client.force_authenticate(user=self.patient_1)
        initial_count = Appointment.objects.count()

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': '2026-11-03T09:00:00Z',
                    'scheduled_end': '2026-11-03T17:00:00Z',
                    'reason': 'Exact boundary appointment',
                },
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            self.assertEqual(Appointment.objects.count(), initial_count + 1)
            appt = Appointment.objects.get(id=res.data['id'])
            self.assertEqual(appt.status, 'pending')
            self.assertEqual(appt.scheduled_start, datetime(2026, 11, 3, 9, 0, 0, tzinfo=dt_timezone.utc))
            self.assertEqual(appt.scheduled_end, datetime(2026, 11, 3, 17, 0, 0, tzinfo=dt_timezone.utc))

    def test_strictly_inside_window_boundaries_succeeds(self):
        """Appointment strictly inside active availability window boundaries succeeds."""
        DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=1,
            start_time=time(9, 0, 0),
            end_time=time(17, 0, 0),
            is_active=True,
        )

        self.client.force_authenticate(user=self.patient_1)
        initial_count = Appointment.objects.count()

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': '2026-11-03T10:00:00Z',
                    'scheduled_end': '2026-11-03T16:00:00Z',
                    'reason': 'Interior appointment',
                },
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            self.assertEqual(Appointment.objects.count(), initial_count + 1)

    def test_appointment_start_before_window_start_rejected(self):
        """Appointment starting before active window start time is rejected with 400 and leaves DB unchanged."""
        DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=1,
            start_time=time(9, 0, 0),
            end_time=time(17, 0, 0),
            is_active=True,
        )

        self.client.force_authenticate(user=self.patient_1)
        initial_count = Appointment.objects.count()

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': '2026-11-03T08:59:00Z',
                    'scheduled_end': '2026-11-03T11:00:00Z',
                    'reason': 'Early start attempt',
                },
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res))
            self.assertEqual(Appointment.objects.count(), initial_count)

    def test_appointment_end_after_window_end_rejected(self):
        """Appointment ending after active window end time is rejected with 400 and leaves DB unchanged."""
        DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=1,
            start_time=time(9, 0, 0),
            end_time=time(17, 0, 0),
            is_active=True,
        )

        self.client.force_authenticate(user=self.patient_1)
        initial_count = Appointment.objects.count()

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': '2026-11-03T15:00:00Z',
                    'scheduled_end': '2026-11-03T17:01:00Z',
                    'reason': 'Late end attempt',
                },
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res))
            self.assertEqual(Appointment.objects.count(), initial_count)

    def test_appointment_in_gap_between_separate_windows_rejected(self):
        """Appointment falling in gap between separate availability windows is rejected with 400."""
        # Wednesday (2) has two windows with a 1-hour gap
        DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=2,
            start_time=time(9, 0, 0),
            end_time=time(12, 0, 0),
            is_active=True,
        )
        DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=2,
            start_time=time(13, 0, 0),
            end_time=time(17, 0, 0),
            is_active=True,
        )

        self.client.force_authenticate(user=self.patient_1)
        initial_count = Appointment.objects.count()

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': '2026-11-04T12:15:00Z',
                    'scheduled_end': '2026-11-04T12:45:00Z',
                    'reason': 'Gap appointment attempt',
                },
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res))
            self.assertEqual(Appointment.objects.count(), initial_count)

    def test_do_not_combine_separate_windows_rejected(self):
        """Appointment spanning across multiple separate windows cannot combine them and is rejected with 400."""
        DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=2,
            start_time=time(9, 0, 0),
            end_time=time(12, 0, 0),
            is_active=True,
        )
        DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=2,
            start_time=time(13, 0, 0),
            end_time=time(17, 0, 0),
            is_active=True,
        )

        self.client.force_authenticate(user=self.patient_1)
        initial_count = Appointment.objects.count()

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': '2026-11-04T11:00:00Z',
                    'scheduled_end': '2026-11-04T14:00:00Z',
                    'reason': 'Spanning windows attempt',
                },
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res))
            self.assertEqual(Appointment.objects.count(), initial_count)

    def test_inactive_window_rejected(self):
        """Inactive doctor availability window is rejected with 400."""
        DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=3,
            start_time=time(9, 0, 0),
            end_time=time(17, 0, 0),
            is_active=False,
        )

        self.client.force_authenticate(user=self.patient_1)
        initial_count = Appointment.objects.count()

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': '2026-11-05T10:00:00Z',
                    'scheduled_end': '2026-11-05T11:00:00Z',
                    'reason': 'Inactive window attempt',
                },
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res))
            self.assertEqual(Appointment.objects.count(), initial_count)

    def test_wrong_doctor_availability_rejected(self):
        """Active window belonging to another doctor cannot be used; rejected with 400."""
        # Active window belongs to doctor_2
        DoctorAvailability.objects.create(
            doctor=self.doctor_2,
            weekday=4,
            start_time=time(9, 0, 0),
            end_time=time(17, 0, 0),
            is_active=True,
        )

        self.client.force_authenticate(user=self.patient_1)
        initial_count = Appointment.objects.count()

        # Attempt to book doctor_1
        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': '2026-11-06T10:00:00Z',
                    'scheduled_end': '2026-11-06T11:00:00Z',
                    'reason': 'Wrong doctor window attempt',
                },
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res))
            self.assertEqual(Appointment.objects.count(), initial_count)

    def test_missing_availability_on_weekday_rejected(self):
        """Requesting appointment on weekday where doctor has no availability is rejected with 400."""
        DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=0,  # Monday only
            start_time=time(9, 0, 0),
            end_time=time(17, 0, 0),
            is_active=True,
        )

        self.client.force_authenticate(user=self.patient_1)
        initial_count = Appointment.objects.count()

        # Attempt booking on Saturday Nov 7
        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': '2026-11-07T10:00:00Z',
                    'scheduled_end': '2026-11-07T11:00:00Z',
                    'reason': 'Missing availability day attempt',
                },
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res))
            self.assertEqual(Appointment.objects.count(), initial_count)

    def test_appointment_crossing_midnight_in_configured_timezone_rejected(self):
        """Appointments crossing midnight in the configured default timezone (UTC) are rejected with 400."""
        # Windows on Monday night and Tuesday morning
        DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=0,
            start_time=time(20, 0, 0),
            end_time=time(23, 59, 59),
            is_active=True,
        )
        DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=1,
            start_time=time(0, 0, 0),
            end_time=time(6, 0, 0),
            is_active=True,
        )

        self.client.force_authenticate(user=self.patient_1)
        initial_count = Appointment.objects.count()

        # 23:00 Monday to 01:00 Tuesday UTC
        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': '2026-11-02T23:00:00Z',
                    'scheduled_end': '2026-11-03T01:00:00Z',
                    'reason': 'Midnight crossing attempt',
                },
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_end', self.get_error_details(res))
            self.assertIn('crossing midnight', str(self.get_error_details(res)['scheduled_end']))
            self.assertEqual(Appointment.objects.count(), initial_count)

    def test_offset_conversion_across_weekdays_matches_utc_window(self):
        """
        Aware appointment datetimes are converted to configured default timezone (UTC) before matching.
        A datetime that appears as Wednesday in +05:30 matches Tuesday UTC availability.
        """
        # Active availability on Tuesday (1) from 18:00:00 to 22:00:00 UTC
        DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=1,
            start_time=time(18, 0, 0),
            end_time=time(22, 0, 0),
            is_active=True,
        )

        self.client.force_authenticate(user=self.patient_1)
        initial_count = Appointment.objects.count()

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            # Wednesday Nov 4 at 01:00:00+05:30 == Tuesday Nov 3 at 19:30:00 UTC
            # Wednesday Nov 4 at 02:00:00+05:30 == Tuesday Nov 3 at 20:30:00 UTC
            res_valid = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': '2026-11-04T01:00:00+05:30',
                    'scheduled_end': '2026-11-04T02:00:00+05:30',
                    'reason': 'Offset conversion across weekdays test',
                },
                format='json',
            )
            self.assertEqual(res_valid.status_code, status.HTTP_201_CREATED)
            self.assertEqual(Appointment.objects.count(), initial_count + 1)
            appt = Appointment.objects.get(id=res_valid.data['id'])
            # Stored start must equal 19:30:00 UTC
            self.assertEqual(appt.scheduled_start, datetime(2026, 11, 3, 19, 30, 0, tzinfo=dt_timezone.utc))

            # Wednesday in +05:30 that converts to Tuesday 04:30:00 UTC (outside 18:00-22:00 window)
            res_invalid = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': '2026-11-03T10:00:00+05:30',
                    'scheduled_end': '2026-11-03T11:00:00+05:30',
                    'reason': 'Offset conversion outside window test',
                },
                format='json',
            )
            self.assertEqual(res_invalid.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res_invalid))
            self.assertEqual(Appointment.objects.count(), initial_count + 1)

    def test_partial_rescheduling_validates_against_availability(self):
        """Partial rescheduling (PATCH) validates effective start and end against active doctor availability."""
        # Tuesday 09:00:00 to 12:00:00 window
        DoctorAvailability.objects.create(
            doctor=self.doctor_1,
            weekday=1,
            start_time=time(9, 0, 0),
            end_time=time(12, 0, 0),
            is_active=True,
        )

        appt = Appointment.objects.create(
            patient=self.patient_1,
            doctor=self.doctor_1,
            scheduled_start=datetime(2026, 11, 3, 10, 0, 0, tzinfo=dt_timezone.utc),
            scheduled_end=datetime(2026, 11, 3, 11, 0, 0, tzinfo=dt_timezone.utc),
            status='pending',
            reason='Initial booking',
        )
        initial_updated_at = appt.updated_at

        self.client.force_authenticate(user=self.patient_1)

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            # 1. Valid partial update to scheduled_start: 09:30:00 (inside window)
            res1 = self.client.patch(
                self.detail_url(appt.id),
                {'scheduled_start': '2026-11-03T09:30:00Z'},
                format='json',
            )
            self.assertEqual(res1.status_code, status.HTTP_200_OK)
            appt.refresh_from_db()
            self.assertEqual(appt.scheduled_start, datetime(2026, 11, 3, 9, 30, 0, tzinfo=dt_timezone.utc))

            # 2. Invalid partial update to scheduled_start: 08:30:00 (before window start 09:00)
            res2 = self.client.patch(
                self.detail_url(appt.id),
                {'scheduled_start': '2026-11-03T08:30:00Z'},
                format='json',
            )
            self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res2))
            appt.refresh_from_db()
            self.assertEqual(appt.scheduled_start, datetime(2026, 11, 3, 9, 30, 0, tzinfo=dt_timezone.utc))

            # 3. Invalid partial update to scheduled_end: 12:30:00 (after window end 12:00)
            res3 = self.client.patch(
                self.detail_url(appt.id),
                {'scheduled_end': '2026-11-03T12:30:00Z'},
                format='json',
            )
            self.assertEqual(res3.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res3))
            appt.refresh_from_db()
            self.assertEqual(appt.scheduled_end, datetime(2026, 11, 3, 11, 0, 0, tzinfo=dt_timezone.utc))

    def test_unchanged_historical_and_unrelated_updates_do_not_revalidate(self):
        """Unrelated updates and unchanged timestamps on existing appointments do not revalidate availability."""
        # Historical appointment in past
        past_start = datetime(2026, 9, 2, 10, 0, 0, tzinfo=dt_timezone.utc)
        past_end = datetime(2026, 9, 2, 11, 0, 0, tzinfo=dt_timezone.utc)
        hist_appt = Appointment.objects.create(
            patient=self.patient_1,
            doctor=self.doctor_1,
            scheduled_start=past_start,
            scheduled_end=past_end,
            status='completed',
            notes='Initial clinical notes',
            reason='Historical visit',
        )

        # Ensure NO doctor availability exists in DB at all
        self.assertEqual(DoctorAvailability.objects.count(), 0)

        self.client.force_authenticate(user=self.doctor_1)

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            # 1. PATCH unrelated field 'notes'
            res_patch = self.client.patch(
                self.detail_url(hist_appt.id),
                {'notes': 'Updated addendum with no availability records'},
                format='json',
            )
            self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
            hist_appt.refresh_from_db()
            self.assertEqual(hist_appt.notes, 'Updated addendum with no availability records')
            self.assertEqual(hist_appt.scheduled_start, past_start)

            # 2. PUT with unchanged historical timestamps
            res_put = self.client.put(
                self.detail_url(hist_appt.id),
                {
                    'patient': str(self.patient_1.id),
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': past_start.isoformat(),
                    'scheduled_end': past_end.isoformat(),
                    'notes': 'Final note with no availability records',
                    'reason': 'Historical visit',
                },
                format='json',
            )
            self.assertEqual(res_put.status_code, status.HTTP_200_OK)
            hist_appt.refresh_from_db()
            self.assertEqual(hist_appt.notes, 'Final note with no availability records')

            # 3. PUT with offset-equivalent timestamp (+05:30)
            offset_start = '2026-09-02T15:30:00+05:30'  # 10:00 UTC
            offset_end = '2026-09-02T16:30:00+05:30'    # 11:00 UTC
            res_offset = self.client.put(
                self.detail_url(hist_appt.id),
                {
                    'patient': str(self.patient_1.id),
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': offset_start,
                    'scheduled_end': offset_end,
                    'notes': 'Offset note with no availability records',
                    'reason': 'Historical visit',
                },
                format='json',
            )
            self.assertEqual(res_offset.status_code, status.HTTP_200_OK)
            hist_appt.refresh_from_db()
            self.assertEqual(hist_appt.notes, 'Offset note with no availability records')
            self.assertEqual(hist_appt.scheduled_start, past_start)

    def test_availability_validation_applies_identically_to_patient_doctor_admin(self):
        """Patients, doctors, and admins are all subject to doctor availability validation."""
        # Ensure doctor_1 has NO availability on Sunday Nov 8, 2026
        target_start = '2026-11-08T14:00:00Z'
        target_end = '2026-11-08T15:00:00Z'
        initial_count = Appointment.objects.count()

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            # 1. Patient attempt
            self.client.force_authenticate(user=self.patient_1)
            res_patient = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': target_start,
                    'scheduled_end': target_end,
                    'reason': 'Patient booking without availability',
                },
                format='json',
            )
            self.assertEqual(res_patient.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res_patient))
            self.assertEqual(Appointment.objects.count(), initial_count)

            # 2. Doctor attempt
            self.client.force_authenticate(user=self.doctor_1)
            res_doctor = self.client.post(
                self.list_url,
                {
                    'patient': str(self.patient_1.id),
                    'scheduled_start': target_start,
                    'scheduled_end': target_end,
                    'reason': 'Doctor booking without availability',
                },
                format='json',
            )
            self.assertEqual(res_doctor.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res_doctor))
            self.assertEqual(Appointment.objects.count(), initial_count)

            # 3. Admin attempt
            self.client.force_authenticate(user=self.admin)
            res_admin = self.client.post(
                self.list_url,
                {
                    'patient': str(self.patient_1.id),
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': target_start,
                    'scheduled_end': target_end,
                    'reason': 'Admin booking without availability',
                },
                format='json',
            )
            self.assertEqual(res_admin.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res_admin))
            self.assertEqual(Appointment.objects.count(), initial_count)


class AppointmentConcurrencyAndLifecycleCoordinationTests(BaseAppointmentTransactionTestCase):
    """
    Tests for backend concurrency, locking, and lifecycle coordination:
    - Inherits from BaseAppointmentTransactionTestCase (APITransactionTestCase) with committed fixtures.
    - Prevents concurrent overlapping bookings and rescheduling for the same doctor.
    - Validates and persists within consistent transaction/locking strategy with select_for_update().
    - Coordinates rescheduling with confirm/cancel/complete so stale updates cannot undo lifecycle changes.
    - Uses independent connections, bounded synchronization (Barrier with timeout), thread exception capture, and guaranteed cleanup.
    - Freezes time consistently across threads.
    - Accurately reports unsupported database skips when PostgreSQL is unavailable.
    """

    FIXED_NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=dt_timezone.utc)

    def test_stale_reschedule_rejected_if_appointment_confirmed_in_between(self):
        """If an appointment is confirmed while reschedule is in-flight, stale reschedule cannot undo confirmation."""
        self.assertEqual(self.appointment_1.status, 'pending')

        # Simulate confirm action taking place before reschedule commits
        self.appointment_1.status = 'confirmed'
        self.appointment_1.save(update_fields=['status'])

        self.client.force_authenticate(user=self.patient_1)
        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res = self.client.patch(
                self.detail_url(self.appointment_1.id),
                {
                    'scheduled_start': (self.FIXED_NOW + timedelta(days=5, hours=10)).isoformat(),
                    'scheduled_end': (self.FIXED_NOW + timedelta(days=5, hours=11)).isoformat(),
                },
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('Cannot reschedule', str(res.data))
            self.appointment_1.refresh_from_db()
            self.assertEqual(self.appointment_1.status, 'confirmed')

    def test_stale_reschedule_rejected_if_appointment_cancelled_in_between(self):
        """If an appointment is cancelled, stale reschedule cannot resurrect it or update timestamps."""
        self.appointment_1.status = 'cancelled'
        self.appointment_1.save(update_fields=['status'])

        self.client.force_authenticate(user=self.patient_1)
        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res = self.client.patch(
                self.detail_url(self.appointment_1.id),
                {
                    'scheduled_start': (self.FIXED_NOW + timedelta(days=5, hours=10)).isoformat(),
                    'scheduled_end': (self.FIXED_NOW + timedelta(days=5, hours=11)).isoformat(),
                },
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('Cannot reschedule', str(res.data))
            self.appointment_1.refresh_from_db()
            self.assertEqual(self.appointment_1.status, 'cancelled')

    def test_stale_reschedule_rejected_if_appointment_completed_in_between(self):
        """If an appointment is completed, stale reschedule cannot modify timestamps."""
        self.appointment_1.status = 'completed'
        self.appointment_1.save(update_fields=['status'])

        self.client.force_authenticate(user=self.patient_1)
        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res = self.client.patch(
                self.detail_url(self.appointment_1.id),
                {
                    'scheduled_start': (self.FIXED_NOW + timedelta(days=5, hours=10)).isoformat(),
                    'scheduled_end': (self.FIXED_NOW + timedelta(days=5, hours=11)).isoformat(),
                },
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('Cannot reschedule', str(res.data))
            self.appointment_1.refresh_from_db()
            self.assertEqual(self.appointment_1.status, 'completed')

    def test_postgresql_concurrent_booking_same_doctor_slot(self):
        """
        PostgreSQL concurrency test: Two patients attempt concurrent booking for the same doctor slot.
        Verifies that row-level locking serializes bookings and prevents duplicate bookings.
        Bounded sync, thread exception capture, guaranteed connection cleanup, and accurate DB engine skip report.
        """
        from django.db import connection
        if connection.vendor != 'postgresql':
            self.skipTest(
                f"Active database vendor is '{connection.vendor}'. "
                "Multi-threaded independent connection concurrency tests require PostgreSQL."
            )

        import threading
        from rest_framework.test import APIClient
        from django.db import connection as thread_conn

        results = []
        thread_exceptions = []
        barrier = threading.Barrier(2, timeout=5.0)
        target_start = self.FIXED_NOW + timedelta(days=3, hours=14)
        target_end = self.FIXED_NOW + timedelta(days=3, hours=15)

        def attempt_booking(patient_user):
            try:
                client = APIClient()
                client.force_authenticate(user=patient_user)
                barrier.wait()
                res = client.post(
                    self.list_url,
                    {
                        'doctor': str(self.doctor_1.id),
                        'scheduled_start': target_start.isoformat(),
                        'scheduled_end': target_end.isoformat(),
                        'reason': 'Concurrent booking slot',
                    },
                    format='json',
                )
                results.append(res.status_code)
            except Exception as exc:
                thread_exceptions.append(exc)
            finally:
                thread_conn.close()

        t1 = threading.Thread(target=attempt_booking, args=(self.patient_1,))
        t2 = threading.Thread(target=attempt_booking, args=(self.patient_2,))

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            t1.start()
            t2.start()
            t1.join(timeout=10.0)
            t2.join(timeout=10.0)

        self.assertFalse(t1.is_alive(), "Worker thread 1 failed to terminate within timeout.")
        self.assertFalse(t2.is_alive(), "Worker thread 2 failed to terminate within timeout.")

        if thread_exceptions:
            self.fail(f"Worker thread exception during concurrent booking: {thread_exceptions}")

        self.assertIn(status.HTTP_201_CREATED, results)
        self.assertIn(status.HTTP_400_BAD_REQUEST, results)
        self.assertEqual(
            Appointment.objects.filter(
                doctor=self.doctor_1,
                scheduled_start=target_start,
                scheduled_end=target_end,
            ).count(),
            1,
        )

    def test_postgresql_concurrent_rescheduling_same_doctor_slot(self):
        """
        PostgreSQL concurrency test: Two distinct pending appointments attempt concurrent rescheduling
        into the exact same future doctor slot.
        Verifies doctor-level row lock prevents overlapping reschedules.
        """
        from django.db import connection
        if connection.vendor != 'postgresql':
            self.skipTest(
                f"Active database vendor is '{connection.vendor}'. "
                "Multi-threaded independent connection concurrency tests require PostgreSQL."
            )

        import threading
        from rest_framework.test import APIClient
        from django.db import connection as thread_conn

        # Create second pending appointment with doctor_1
        appt_extra = Appointment.objects.create(
            patient=self.patient_2,
            doctor=self.doctor_1,
            scheduled_start=self.FIXED_NOW + timedelta(days=2, hours=16),
            scheduled_end=self.FIXED_NOW + timedelta(days=2, hours=17),
            status='pending',
            reason='Second pending appointment',
        )

        results = []
        thread_exceptions = []
        barrier = threading.Barrier(2, timeout=5.0)
        target_start = self.FIXED_NOW + timedelta(days=4, hours=10)
        target_end = self.FIXED_NOW + timedelta(days=4, hours=11)

        def attempt_reschedule(appt_id, patient_user):
            try:
                client = APIClient()
                client.force_authenticate(user=patient_user)
                barrier.wait()
                res = client.patch(
                    self.detail_url(appt_id),
                    {
                        'scheduled_start': target_start.isoformat(),
                        'scheduled_end': target_end.isoformat(),
                    },
                    format='json',
                )
                results.append(res.status_code)
            except Exception as exc:
                thread_exceptions.append(exc)
            finally:
                thread_conn.close()

        t1 = threading.Thread(target=attempt_reschedule, args=(self.appointment_1.id, self.patient_1))
        t2 = threading.Thread(target=attempt_reschedule, args=(appt_extra.id, self.patient_2))

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            t1.start()
            t2.start()
            t1.join(timeout=10.0)
            t2.join(timeout=10.0)

        self.assertFalse(t1.is_alive(), "Worker thread 1 failed to terminate within timeout.")
        self.assertFalse(t2.is_alive(), "Worker thread 2 failed to terminate within timeout.")

        if thread_exceptions:
            self.fail(f"Worker thread exception during concurrent rescheduling: {thread_exceptions}")

        self.assertIn(status.HTTP_200_OK, results)
        self.assertIn(status.HTTP_400_BAD_REQUEST, results)
        self.assertEqual(
            Appointment.objects.filter(
                doctor=self.doctor_1,
                scheduled_start=target_start,
                scheduled_end=target_end,
            ).count(),
            1,
        )

    def test_postgresql_concurrent_reschedule_vs_lifecycle_confirm(self):
        """
        PostgreSQL concurrency test: Rescheduling versus lifecycle confirm action.
        Thread 1 attempts to reschedule appointment_1 while Thread 2 attempts to confirm it.
        Verifies that select_for_update() row locking coordinates transitions:
        - If reschedule commits first, appointment remains pending with new timestamps, and confirm then confirms it.
        - If confirm commits first, appointment becomes confirmed, and reschedule is rejected with HTTP 400.
        In neither order can a confirmed appointment be overwritten or corrupted by a stale reschedule.
        """
        from django.db import connection
        if connection.vendor != 'postgresql':
            self.skipTest(
                f"Active database vendor is '{connection.vendor}'. "
                "Multi-threaded independent connection concurrency tests require PostgreSQL."
            )

        import threading
        from rest_framework.test import APIClient
        from django.db import connection as thread_conn

        results = {}
        thread_exceptions = []
        barrier = threading.Barrier(2, timeout=5.0)
        new_start = self.FIXED_NOW + timedelta(days=5, hours=14)
        new_end = self.FIXED_NOW + timedelta(days=5, hours=15)

        def attempt_reschedule():
            try:
                client = APIClient()
                client.force_authenticate(user=self.patient_1)
                barrier.wait()
                res = client.patch(
                    self.detail_url(self.appointment_1.id),
                    {
                        'scheduled_start': new_start.isoformat(),
                        'scheduled_end': new_end.isoformat(),
                    },
                    format='json',
                )
                results['reschedule'] = res.status_code
            except Exception as exc:
                thread_exceptions.append(exc)
            finally:
                thread_conn.close()

        def attempt_confirm():
            try:
                client = APIClient()
                client.force_authenticate(user=self.doctor_1)
                barrier.wait()
                res = client.post(
                    self.confirm_url(self.appointment_1.id),
                    {},
                    format='json',
                )
                results['confirm'] = res.status_code
            except Exception as exc:
                thread_exceptions.append(exc)
            finally:
                thread_conn.close()

        t1 = threading.Thread(target=attempt_reschedule)
        t2 = threading.Thread(target=attempt_confirm)

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            t1.start()
            t2.start()
            t1.join(timeout=10.0)
            t2.join(timeout=10.0)

        self.assertFalse(t1.is_alive(), "Worker thread 1 failed to terminate within timeout.")
        self.assertFalse(t2.is_alive(), "Worker thread 2 failed to terminate within timeout.")

        if thread_exceptions:
            self.fail(f"Worker thread exception during reschedule vs confirm: {thread_exceptions}")

        self.appointment_1.refresh_from_db()
        self.assertEqual(self.appointment_1.status, 'confirmed')
        self.assertEqual(results['confirm'], status.HTTP_200_OK)
        self.assertIn(results['reschedule'], [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST])


class AppointmentConnectedEndToEndWorkflowTests(BaseAppointmentTestCase):
    """
    Connected workflow tests exercising complete user paths:
    - Path 1: Patient booking -> Doctor confirmation -> Doctor completion.
    - Path 2: Patient booking -> Pending rescheduling -> Doctor confirmation -> Completion.
    - Path 3: Patient booking -> Patient cancellation.
    - Path 4: Patient booking -> Doctor confirmation -> Doctor cancellation.
    - Path 5: Doctor manages availability (create/deactivate/reactivate/delete) impacting bookings.
    """

    FIXED_NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=dt_timezone.utc)

    def test_workflow_booking_to_confirmation_to_completion(self):
        """Full happy path: Patient books -> Doctor confirms -> Doctor completes."""
        # 1. Patient books
        self.client.force_authenticate(user=self.patient_1)
        start = self.FIXED_NOW + timedelta(days=2, hours=10)
        end = self.FIXED_NOW + timedelta(days=2, hours=11)

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res_book = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': start.isoformat(),
                    'scheduled_end': end.isoformat(),
                    'reason': 'Comprehensive checkup',
                    'symptoms': ['headache'],
                },
                format='json',
            )
            self.assertEqual(res_book.status_code, status.HTTP_201_CREATED)
            appt_id = res_book.data['id']
            self.assertEqual(res_book.data['status'], 'pending')

            # 2. Doctor lists appointments and sees pending booking
            self.client.force_authenticate(user=self.doctor_1)
            res_list = self.client.get(f"{self.list_url}?status=pending")
            self.assertEqual(res_list.status_code, status.HTTP_200_OK)
            booking_ids = [a['id'] for a in (res_list.data.get('results') or res_list.data)]
            self.assertIn(appt_id, booking_ids)

            # 3. Doctor confirms
            res_confirm = self.client.post(self.confirm_url(appt_id), {}, format='json')
            self.assertEqual(res_confirm.status_code, status.HTTP_200_OK)
            self.assertEqual(res_confirm.data['status'], 'confirmed')

            # 4. Doctor completes
            res_complete = self.client.post(self.complete_url(appt_id), {}, format='json')
            self.assertEqual(res_complete.status_code, status.HTTP_200_OK)
            self.assertEqual(res_complete.data['status'], 'completed')

            # Verify persisted row
            appt = Appointment.objects.get(id=appt_id)
            self.assertEqual(appt.status, 'completed')

    def test_workflow_booking_rescheduling_and_completion(self):
        """Workflow: Patient books -> Reschedules while pending -> Doctor confirms -> Doctor completes."""
        self.client.force_authenticate(user=self.patient_1)
        start1 = self.FIXED_NOW + timedelta(days=2, hours=10)
        end1 = self.FIXED_NOW + timedelta(days=2, hours=11)
        start2 = self.FIXED_NOW + timedelta(days=3, hours=14)
        end2 = self.FIXED_NOW + timedelta(days=3, hours=15)

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            # Book
            res_book = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': start1.isoformat(),
                    'scheduled_end': end1.isoformat(),
                    'reason': 'Initial slot',
                },
                format='json',
            )
            appt_id = res_book.data['id']

            # Patient reschedules to day 3
            res_reschedule = self.client.patch(
                self.detail_url(appt_id),
                {
                    'scheduled_start': start2.isoformat(),
                    'scheduled_end': end2.isoformat(),
                },
                format='json',
            )
            self.assertEqual(res_reschedule.status_code, status.HTTP_200_OK)
            self.assertEqual(res_reschedule.data['status'], 'pending')

            # Doctor confirms rescheduled slot
            self.client.force_authenticate(user=self.doctor_1)
            res_confirm = self.client.post(self.confirm_url(appt_id), {}, format='json')
            self.assertEqual(res_confirm.status_code, status.HTTP_200_OK)
            self.assertEqual(res_confirm.data['status'], 'confirmed')

            # Doctor completes
            res_complete = self.client.post(self.complete_url(appt_id), {}, format='json')
            self.assertEqual(res_complete.status_code, status.HTTP_200_OK)
            self.assertEqual(res_complete.data['status'], 'completed')

    def test_workflow_patient_booking_cancellation(self):
        """Workflow: Patient books -> Patient cancels pending appointment with reason."""
        self.client.force_authenticate(user=self.patient_1)
        start = self.FIXED_NOW + timedelta(days=2, hours=10)
        end = self.FIXED_NOW + timedelta(days=2, hours=11)

        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res_book = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': start.isoformat(),
                    'scheduled_end': end.isoformat(),
                    'reason': 'Consultation',
                },
                format='json',
            )
            appt_id = res_book.data['id']

            # Cancel with reason
            res_cancel = self.client.post(
                self.cancel_url(appt_id),
                {'cancellation_reason': 'Schedule conflict'},
                format='json',
            )
            self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)
            self.assertEqual(res_cancel.data['status'], 'cancelled')
            self.assertEqual(res_cancel.data['cancellation_reason'], 'Schedule conflict')

            # Verify in DB
            appt = Appointment.objects.get(id=appt_id)
            self.assertEqual(appt.status, 'cancelled')
            self.assertEqual(appt.cancellation_reason, 'Schedule conflict')

    def test_workflow_doctor_availability_lifecycle_impacts_booking(self):
        """Workflow: Doctor manages availability (create, deactivate, reactivate, delete)."""
        # Clear windows first
        DoctorAvailability.objects.all().delete()

        self.client.force_authenticate(user=self.doctor_1)

        # 1. Doctor creates availability on Tuesday 09:00 - 12:00
        res_create = self.client.post(
            self.availability_list_url,
            {
                'weekday': 1,
                'start_time': '09:00:00',
                'end_time': '12:00:00',
                'is_active': True,
            },
            format='json',
        )
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        avail_id = res_create.data['id']

        # 2. Patient books fitting slot -> succeeds
        self.client.force_authenticate(user=self.patient_1)
        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res_book1 = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': '2026-11-03T10:00:00Z',
                    'scheduled_end': '2026-11-03T11:00:00Z',
                    'reason': 'Tuesday visit',
                },
                format='json',
            )
            self.assertEqual(res_book1.status_code, status.HTTP_201_CREATED)

        # 3. Doctor deactivates the availability window
        self.client.force_authenticate(user=self.doctor_1)
        res_deactivate = self.client.patch(
            self.availability_detail_url(avail_id),
            {'is_active': False},
            format='json',
        )
        self.assertEqual(res_deactivate.status_code, status.HTTP_200_OK)
        self.assertFalse(res_deactivate.data['is_active'])

        # 4. Patient attempts booking in the now-inactive window -> rejected with 400
        self.client.force_authenticate(user=self.patient_2)
        with patch('django.utils.timezone.now', return_value=self.FIXED_NOW):
            res_book2 = self.client.post(
                self.list_url,
                {
                    'doctor': str(self.doctor_1.id),
                    'scheduled_start': '2026-11-03T11:00:00Z',
                    'scheduled_end': '2026-11-03T12:00:00Z',
                    'reason': 'Tuesday visit attempt',
                },
                format='json',
            )
            self.assertEqual(res_book2.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('scheduled_start', self.get_error_details(res_book2))

        # 5. Doctor deletes the availability window
        self.client.force_authenticate(user=self.doctor_1)
        res_delete = self.client.delete(self.availability_detail_url(avail_id))
        self.assertEqual(res_delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(DoctorAvailability.objects.filter(id=avail_id).exists())






