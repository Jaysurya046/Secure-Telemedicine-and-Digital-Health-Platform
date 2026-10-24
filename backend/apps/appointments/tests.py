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
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIRequestFactory

from apps.appointments.models import Appointment
from apps.appointments.permissions import AppointmentAccessPermission

User = get_user_model()


class BaseAppointmentTestCase(APITestCase):
    """Base test setup with patients, doctors, admin, and unsupported role fixtures."""

    def setUp(self):
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

    def get_error_details(self, response):
        """Helper to extract field errors from standard or custom DRF responses."""
        if isinstance(response.data, dict) and 'details' in response.data:
            return response.data['details']
        return response.data


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

