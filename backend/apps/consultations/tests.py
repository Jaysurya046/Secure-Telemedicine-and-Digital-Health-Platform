"""Tests for apps.consultations creation security and permissions."""
import datetime
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.appointments.models import Appointment
from apps.consultations.models import Consultation, ConsultationMessage
from apps.users.models import UserProfile, DoctorProfile

User = get_user_model()


class ConsultationCreationSecurityTests(APITestCase):
    """
    Feature 3D: Secure consultation creation regression tests.
    
    Requirements:
    - Require a confirmed appointment.
    - Patients may create only for their own appointment; doctors only for appointments assigned to them.
    - Admins may create for any qualifying appointment.
    - Derive patient and doctor from that appointment before serializer validation.
      Clients may omit both fields; reject supplied values that conflict.
    - Reject missing, pending, cancelled, completed, or unrelated appointments without creating rows.
    - Reject duplicate consultations for the same appointment with a controlled 4xx response.
    - Set initial status to scheduled server-side. Reject attempts to supply another status.
    - Deny unauthenticated users and unsupported roles.
    - Preserve existing consultation reads and legacy rows without appointments.
    - Malformed request bodies return 400 and leave database state unchanged.
    """

    def setUp(self):
        self.consultation_list_url = reverse('consultation-list')

        # Patients
        self.patient_1 = User.objects.create_user(
            email='pat1_f3d@example.com',
            password='Password123!@#',
            role='patient',
        )
        UserProfile.objects.create(user=self.patient_1, first_name='Patient', last_name='One')

        self.patient_2 = User.objects.create_user(
            email='pat2_f3d@example.com',
            password='Password123!@#',
            role='patient',
        )
        UserProfile.objects.create(user=self.patient_2, first_name='Patient', last_name='Two')

        # Doctors
        self.doctor_1 = User.objects.create_user(
            email='doc1_f3d@example.com',
            password='Password123!@#',
            role='doctor',
        )
        UserProfile.objects.create(user=self.doctor_1, first_name='Doctor', last_name='One')
        DoctorProfile.objects.create(user=self.doctor_1, specialization='General', license_number='DOC1_F3D')

        self.doctor_2 = User.objects.create_user(
            email='doc2_f3d@example.com',
            password='Password123!@#',
            role='doctor',
        )
        UserProfile.objects.create(user=self.doctor_2, first_name='Doctor', last_name='Two')
        DoctorProfile.objects.create(user=self.doctor_2, specialization='Neurology', license_number='DOC2_F3D')

        # Admin
        self.admin = User.objects.create_user(
            email='admin_f3d@example.com',
            password='Password123!@#',
            role='admin',
            is_staff=True,
        )

        # Unsupported role (e.g. nurse)
        self.nurse = User.objects.create_user(
            email='nurse_f3d@example.com',
            password='Password123!@#',
            role='nurse',
        )

        # Confirmed appointment for doc1 and pat1
        now = timezone.now()
        self.appt_doc1_pat1 = Appointment.objects.create(
            doctor=self.doctor_1,
            patient=self.patient_1,
            status='confirmed',
            scheduled_start=now + datetime.timedelta(days=1),
            scheduled_end=now + datetime.timedelta(days=1, hours=1),
            reason='Annual checkup',
        )

        # Confirmed appointment for doc2 and pat2
        self.appt_doc2_pat2 = Appointment.objects.create(
            doctor=self.doctor_2,
            patient=self.patient_2,
            status='confirmed',
            scheduled_start=now + datetime.timedelta(days=2),
            scheduled_end=now + datetime.timedelta(days=2, hours=1),
            reason='Headache consultation',
        )

    def detail_url(self, pk):
        return reverse('consultation-detail', kwargs={'pk': pk})

    def get_error_details(self, response):
        if isinstance(response.data, dict) and 'details' in response.data:
            return response.data['details']
        return response.data

    def test_patient_can_create_consultation_omitting_patient_and_doctor(self):
        """Patient creates consultation for their own confirmed appointment, omitting patient and doctor."""
        self.client.force_authenticate(user=self.patient_1)
        res = self.client.post(self.consultation_list_url, {
            'appointment': str(self.appt_doc1_pat1.id),
            'chief_complaint': 'Mild fever and cough',
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(res.data['patient']), str(self.patient_1.id))
        self.assertEqual(str(res.data['doctor']), str(self.doctor_1.id))
        self.assertEqual(str(res.data['appointment']), str(self.appt_doc1_pat1.id))
        self.assertEqual(res.data['status'], 'scheduled')
        self.assertEqual(res.data['chief_complaint'], 'Mild fever and cough')

    def test_doctor_can_create_consultation_omitting_patient_and_doctor(self):
        """Doctor creates consultation for appointment assigned to them, omitting patient and doctor."""
        self.client.force_authenticate(user=self.doctor_1)
        res = self.client.post(self.consultation_list_url, {
            'appointment': str(self.appt_doc1_pat1.id),
            'chief_complaint': 'Doctor initiated follow up',
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(res.data['patient']), str(self.patient_1.id))
        self.assertEqual(str(res.data['doctor']), str(self.doctor_1.id))
        self.assertEqual(res.data['status'], 'scheduled')

    def test_admin_can_create_consultation_for_any_qualifying_appointment(self):
        """Admin creates consultation for any confirmed appointment."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(self.consultation_list_url, {
            'appointment': str(self.appt_doc2_pat2.id),
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(res.data['patient']), str(self.patient_2.id))
        self.assertEqual(str(res.data['doctor']), str(self.doctor_2.id))
        self.assertEqual(res.data['status'], 'scheduled')

    def test_matching_patient_and_doctor_values_accepted(self):
        """Supplying explicit patient and doctor matching the appointment succeeds."""
        self.client.force_authenticate(user=self.patient_1)
        res = self.client.post(self.consultation_list_url, {
            'appointment': str(self.appt_doc1_pat1.id),
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_1.id),
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(res.data['patient']), str(self.patient_1.id))
        self.assertEqual(str(res.data['doctor']), str(self.doctor_1.id))

    def test_conflicting_patient_rejected_without_creating_row(self):
        """Supplying a conflicting patient is rejected with 400 and creates no rows."""
        self.client.force_authenticate(user=self.doctor_1)
        initial_count = Consultation.objects.count()

        res = self.client.post(self.consultation_list_url, {
            'appointment': str(self.appt_doc1_pat1.id),
            'patient': str(self.patient_2.id),  # Conflicts with pat1
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(res))
        self.assertEqual(Consultation.objects.count(), initial_count)

    def test_conflicting_doctor_rejected_without_creating_row(self):
        """Supplying a conflicting doctor is rejected with 400 and creates no rows."""
        self.client.force_authenticate(user=self.patient_1)
        initial_count = Consultation.objects.count()

        res = self.client.post(self.consultation_list_url, {
            'appointment': str(self.appt_doc1_pat1.id),
            'doctor': str(self.doctor_2.id),  # Conflicts with doc1
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(res))
        self.assertEqual(Consultation.objects.count(), initial_count)

    def test_missing_appointment_rejected_without_creating_row(self):
        """Creation without an appointment is rejected with 400 and creates no rows."""
        self.client.force_authenticate(user=self.patient_1)
        initial_count = Consultation.objects.count()

        # Omitted appointment
        res1 = self.client.post(self.consultation_list_url, {
            'chief_complaint': 'Headache',
        }, format='json')
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('appointment', self.get_error_details(res1))

        # None appointment
        res2 = self.client.post(self.consultation_list_url, {
            'appointment': None,
        }, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('appointment', self.get_error_details(res2))

        self.assertEqual(Consultation.objects.count(), initial_count)

    def test_non_existent_appointment_rejected_without_creating_row(self):
        """Referencing a non-existent appointment ID is rejected with 400."""
        self.client.force_authenticate(user=self.patient_1)
        initial_count = Consultation.objects.count()

        res = self.client.post(self.consultation_list_url, {
            'appointment': '00000000-0000-0000-0000-000000000000',
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('appointment', self.get_error_details(res))
        self.assertEqual(Consultation.objects.count(), initial_count)

    def test_non_confirmed_appointments_rejected_without_creating_row(self):
        """Pending, cancelled, completed, and no-show appointments are rejected with 400."""
        now = timezone.now()
        statuses = ['pending', 'cancelled', 'completed', 'no_show']
        self.client.force_authenticate(user=self.patient_1)
        initial_count = Consultation.objects.count()

        for st in statuses:
            appt = Appointment.objects.create(
                doctor=self.doctor_1,
                patient=self.patient_1,
                status=st,
                scheduled_start=now,
                scheduled_end=now + datetime.timedelta(hours=1),
                reason=f'{st} appointment',
            )
            res = self.client.post(self.consultation_list_url, {
                'appointment': str(appt.id),
            }, format='json')

            self.assertEqual(
                res.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"Expected 400 for appointment status '{st}', got {res.status_code}",
            )
            self.assertIn('appointment', self.get_error_details(res))

        self.assertEqual(Consultation.objects.count(), initial_count)

    def test_unrelated_appointment_rejected_for_patient(self):
        """Patients cannot create consultations for appointments belonging to other patients."""
        self.client.force_authenticate(user=self.patient_1)
        initial_count = Consultation.objects.count()

        # appt_doc2_pat2 belongs to patient_2
        res = self.client.post(self.consultation_list_url, {
            'appointment': str(self.appt_doc2_pat2.id),
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('appointment', self.get_error_details(res))
        self.assertEqual(Consultation.objects.count(), initial_count)

    def test_unrelated_appointment_rejected_for_doctor(self):
        """Doctors cannot create consultations for appointments assigned to other doctors."""
        self.client.force_authenticate(user=self.doctor_1)
        initial_count = Consultation.objects.count()

        # appt_doc2_pat2 is assigned to doctor_2
        res = self.client.post(self.consultation_list_url, {
            'appointment': str(self.appt_doc2_pat2.id),
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('appointment', self.get_error_details(res))
        self.assertEqual(Consultation.objects.count(), initial_count)

    def test_duplicate_consultation_rejected_with_controlled_4xx(self):
        """Attempting to create a second consultation for the same appointment returns 400."""
        self.client.force_authenticate(user=self.patient_1)
        res1 = self.client.post(self.consultation_list_url, {
            'appointment': str(self.appt_doc1_pat1.id),
        }, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Consultation.objects.count(), 1)

        # Second creation attempt (by doctor)
        self.client.force_authenticate(user=self.doctor_1)
        res2 = self.client.post(self.consultation_list_url, {
            'appointment': str(self.appt_doc1_pat1.id),
        }, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('appointment', self.get_error_details(res2))
        self.assertEqual(Consultation.objects.count(), 1)

        # Third creation attempt (by admin)
        self.client.force_authenticate(user=self.admin)
        res3 = self.client.post(self.consultation_list_url, {
            'appointment': str(self.appt_doc1_pat1.id),
        }, format='json')
        self.assertEqual(res3.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('appointment', self.get_error_details(res3))
        self.assertEqual(Consultation.objects.count(), 1)

    def test_initial_status_must_be_scheduled(self):
        """Attempts to supply a status other than 'scheduled' are rejected."""
        self.client.force_authenticate(user=self.doctor_1)
        initial_count = Consultation.objects.count()

        invalid_statuses = ['in_progress', 'completed', 'cancelled', 'arbitrary']
        for st in invalid_statuses:
            res = self.client.post(self.consultation_list_url, {
                'appointment': str(self.appt_doc1_pat1.id),
                'status': st,
            }, format='json')
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('status', self.get_error_details(res))

        self.assertEqual(Consultation.objects.count(), initial_count)

        # Supplying 'scheduled' succeeds
        res_ok = self.client.post(self.consultation_list_url, {
            'appointment': str(self.appt_doc1_pat1.id),
            'status': 'scheduled',
        }, format='json')
        self.assertEqual(res_ok.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_ok.data['status'], 'scheduled')

    def test_unauthenticated_requests_denied(self):
        """Unauthenticated requests are rejected with 401 Unauthorized."""
        initial_count = Consultation.objects.count()
        self.client.logout()

        res = self.client.post(self.consultation_list_url, {
            'appointment': str(self.appt_doc1_pat1.id),
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Consultation.objects.count(), initial_count)

    def test_unsupported_role_denied(self):
        """Unsupported roles (e.g. nurse) are rejected with 403 Forbidden."""
        self.client.force_authenticate(user=self.nurse)
        initial_count = Consultation.objects.count()

        res = self.client.post(self.consultation_list_url, {
            'appointment': str(self.appt_doc1_pat1.id),
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Consultation.objects.count(), initial_count)

    def test_malformed_payload_bodies_rejected_without_creating_row(self):
        """Malformed payloads (arrays, strings, numbers, booleans) return 400 without creating rows."""
        self.client.force_authenticate(user=self.patient_1)
        initial_count = Consultation.objects.count()

        malformed_payloads = [
            [],
            ['list', 'item'],
            'invalid_string',
            '',
            42,
            0,
            3.14,
            True,
            False,
        ]

        for payload in malformed_payloads:
            res = self.client.post(self.consultation_list_url, payload, format='json')
            self.assertEqual(
                res.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"Expected 400 for payload {payload!r}, got {res.status_code}",
            )

        self.assertEqual(Consultation.objects.count(), initial_count)

    def test_preserve_existing_consultation_reads_and_legacy_rows_without_appointment(self):
        """Existing consultation reads and legacy rows without appointments are preserved."""
        # Create legacy consultation without appointment directly in DB
        legacy_consultation = Consultation.objects.create(
            doctor=self.doctor_1,
            patient=self.patient_1,
            status='scheduled',
            appointment=None,
            chief_complaint='Legacy consultation without appointment',
        )

        detail_url = self.detail_url(legacy_consultation.id)

        # 1. Patient read
        self.client.force_authenticate(user=self.patient_1)
        res_pat_list = self.client.get(self.consultation_list_url)
        self.assertEqual(res_pat_list.status_code, status.HTTP_200_OK)
        pat_ids = [item['id'] for item in res_pat_list.data['results']]
        self.assertIn(str(legacy_consultation.id), pat_ids)

        res_pat_detail = self.client.get(detail_url)
        self.assertEqual(res_pat_detail.status_code, status.HTTP_200_OK)
        self.assertIsNone(res_pat_detail.data['appointment'])
        self.assertEqual(str(res_pat_detail.data['patient']), str(self.patient_1.id))

        # 2. Doctor read
        self.client.force_authenticate(user=self.doctor_1)
        res_doc_detail = self.client.get(detail_url)
        self.assertEqual(res_doc_detail.status_code, status.HTTP_200_OK)
        self.assertIsNone(res_doc_detail.data['appointment'])

        # 3. Admin read
        self.client.force_authenticate(user=self.admin)
        res_adm_detail = self.client.get(detail_url)
        self.assertEqual(res_adm_detail.status_code, status.HTTP_200_OK)
        self.assertIsNone(res_adm_detail.data['appointment'])


class ConsultationWriteAndOwnershipProtectionTests(APITestCase):
    """
    Feature 3E: Protect consultation writes and ownership regression tests.
    
    Requirements:
    - Patients may read their consultations, create under Feature 3D rules, and send messages.
      Deny their PUT, PATCH, DELETE, start, and end requests.
    - Reject patient-supplied diagnosis, clinical_notes, follow_up_required, and follow_up_notes during creation.
    - Assigned doctors and admins retain clinical editing and deletion.
    - After creation, appointment, patient, and doctor are immutable for every role. Accept unchanged values.
    - Generic PUT/PATCH must reject status changes; lifecycle actions control status.
    - Only assigned doctors and admins may invoke start/end.
    - Preserve scoped reads, message sending, and all Feature 3D creation checks.
    - Rejected requests must leave rows and messages unchanged.
    """

    def setUp(self):
        self.consultation_list_url = reverse('consultation-list')

        # Patients
        self.patient_1 = User.objects.create_user(
            email='pat1_f3e@example.com',
            password='Password123!@#',
            role='patient',
        )
        UserProfile.objects.create(user=self.patient_1, first_name='Pat', last_name='One')

        self.patient_2 = User.objects.create_user(
            email='pat2_f3e@example.com',
            password='Password123!@#',
            role='patient',
        )
        UserProfile.objects.create(user=self.patient_2, first_name='Pat', last_name='Two')

        # Doctors
        self.doctor_1 = User.objects.create_user(
            email='doc1_f3e@example.com',
            password='Password123!@#',
            role='doctor',
        )
        UserProfile.objects.create(user=self.doctor_1, first_name='Doc', last_name='One')
        DoctorProfile.objects.create(user=self.doctor_1, specialization='Cardiology', license_number='DOC1_F3E')

        self.doctor_2 = User.objects.create_user(
            email='doc2_f3e@example.com',
            password='Password123!@#',
            role='doctor',
        )
        UserProfile.objects.create(user=self.doctor_2, first_name='Doc', last_name='Two')
        DoctorProfile.objects.create(user=self.doctor_2, specialization='Neurology', license_number='DOC2_F3E')

        # Admin
        self.admin = User.objects.create_user(
            email='admin_f3e@example.com',
            password='Password123!@#',
            role='admin',
            is_staff=True,
        )

        now = timezone.now()
        self.appt_1 = Appointment.objects.create(
            doctor=self.doctor_1,
            patient=self.patient_1,
            status='confirmed',
            scheduled_start=now + datetime.timedelta(days=1),
            scheduled_end=now + datetime.timedelta(days=1, hours=1),
            reason='Routine Checkup',
        )

        self.appt_2 = Appointment.objects.create(
            doctor=self.doctor_2,
            patient=self.patient_2,
            status='confirmed',
            scheduled_start=now + datetime.timedelta(days=2),
            scheduled_end=now + datetime.timedelta(days=2, hours=1),
            reason='Follow-up',
        )

        # Baseline consultation for doctor 1 and patient 1
        self.consultation = Consultation.objects.create(
            appointment=self.appt_1,
            doctor=self.doctor_1,
            patient=self.patient_1,
            status='scheduled',
            chief_complaint='Initial complaint',
            diagnosis='Initial diagnosis',
            clinical_notes='Initial notes',
        )

    def detail_url(self, pk):
        return reverse('consultation-detail', kwargs={'pk': pk})

    def start_url(self, pk):
        return reverse('consultation-start', kwargs={'pk': pk})

    def end_url(self, pk):
        return reverse('consultation-end', kwargs={'pk': pk})

    def messages_url(self, pk):
        return reverse('consultation-messages', kwargs={'pk': pk})

    def get_error_details(self, response):
        if isinstance(response.data, dict) and 'details' in response.data:
            return response.data['details']
        return response.data

    def test_patient_denied_put_patch_delete_start_and_end(self):
        """Patients are denied (403 Forbidden) on PUT, PATCH, DELETE, start, and end."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.detail_url(self.consultation.id)

        # 1. PUT
        res_put = self.client.put(url, {
            'appointment': str(self.appt_1.id),
            'chief_complaint': 'Hacked complaint',
        }, format='json')
        self.assertEqual(res_put.status_code, status.HTTP_403_FORBIDDEN)

        # 2. PATCH
        res_patch = self.client.patch(url, {'chief_complaint': 'Hacked complaint'}, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_403_FORBIDDEN)

        # 3. DELETE
        res_delete = self.client.delete(url)
        self.assertEqual(res_delete.status_code, status.HTTP_403_FORBIDDEN)

        # 4. Start
        res_start = self.client.post(self.start_url(self.consultation.id))
        self.assertEqual(res_start.status_code, status.HTTP_403_FORBIDDEN)

        # 5. End
        res_end = self.client.post(self.end_url(self.consultation.id))
        self.assertEqual(res_end.status_code, status.HTTP_403_FORBIDDEN)

        # Verify consultation row remains completely unchanged
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.chief_complaint, 'Initial complaint')
        self.assertEqual(self.consultation.status, 'scheduled')

    def test_patient_can_read_and_send_messages(self):
        """Patients can retrieve their consultation and send messages."""
        self.client.force_authenticate(user=self.patient_1)

        # Retrieve
        res_get = self.client.get(self.detail_url(self.consultation.id))
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        self.assertEqual(res_get.data['id'], str(self.consultation.id))

        # Send message
        res_msg = self.client.post(self.messages_url(self.consultation.id), {
            'message': 'Hello Doctor, I have a quick question.',
        }, format='json')
        self.assertEqual(res_msg.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_msg.data['message'], 'Hello Doctor, I have a quick question.')
        self.assertEqual(self.consultation.messages.count(), 1)
        self.assertEqual(self.consultation.messages.first().sender, self.patient_1)

    def test_patient_clinical_field_injection_rejected_on_creation(self):
        """Patients cannot supply diagnosis, clinical_notes, follow_up_required, or follow_up_notes on creation."""
        now = timezone.now()
        appt_fresh = Appointment.objects.create(
            doctor=self.doctor_1,
            patient=self.patient_1,
            status='confirmed',
            scheduled_start=now + datetime.timedelta(days=3),
            scheduled_end=now + datetime.timedelta(days=3, hours=1),
            reason='New visit',
        )

        self.client.force_authenticate(user=self.patient_1)
        initial_count = Consultation.objects.count()

        injections = [
            {'diagnosis': 'Severe Hypertension'},
            {'clinical_notes': 'Patient needs immediate medication.'},
            {'follow_up_required': True},
            {'follow_up_notes': 'Schedule in 2 weeks.'},
        ]

        for payload_injection in injections:
            data = {
                'appointment': str(appt_fresh.id),
                'chief_complaint': 'Chest pain',
                **payload_injection,
            }
            res = self.client.post(self.consultation_list_url, data, format='json')
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            field_name = list(payload_injection.keys())[0]
            self.assertIn(field_name, self.get_error_details(res))
            self.assertEqual(Consultation.objects.count(), initial_count)

        # Doctor creating with clinical fields succeeds
        self.client.force_authenticate(user=self.doctor_1)
        res_doc = self.client.post(self.consultation_list_url, {
            'appointment': str(appt_fresh.id),
            'chief_complaint': 'Chest pain',
            'diagnosis': 'Severe Hypertension',
            'clinical_notes': 'Doctor clinical notes',
            'follow_up_required': True,
            'follow_up_notes': 'Follow up soon',
        }, format='json')
        self.assertEqual(res_doc.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_doc.data['diagnosis'], 'Severe Hypertension')

    def test_assigned_doctor_can_edit_clinical_fields_and_delete(self):
        """Assigned doctors can edit clinical fields via PATCH and delete the consultation."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.detail_url(self.consultation.id)

        # PATCH clinical fields
        res_patch = self.client.patch(url, {
            'diagnosis': 'Updated Diagnosis',
            'clinical_notes': 'Updated clinical notes by doctor',
            'follow_up_required': True,
            'follow_up_notes': 'See specialist',
        }, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)

        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.diagnosis, 'Updated Diagnosis')
        self.assertEqual(self.consultation.clinical_notes, 'Updated clinical notes by doctor')
        self.assertTrue(self.consultation.follow_up_required)
        self.assertEqual(self.consultation.follow_up_notes, 'See specialist')

        # DELETE
        res_del = self.client.delete(url)
        self.assertEqual(res_del.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Consultation.objects.filter(id=self.consultation.id).exists())

    def test_admin_can_edit_clinical_fields_and_delete(self):
        """Admins can edit clinical fields and delete consultations."""
        self.client.force_authenticate(user=self.admin)
        url = self.detail_url(self.consultation.id)

        # PATCH
        res_patch = self.client.patch(url, {
            'clinical_notes': 'Admin override notes',
        }, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.clinical_notes, 'Admin override notes')

        # DELETE
        res_del = self.client.delete(url)
        self.assertEqual(res_del.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Consultation.objects.filter(id=self.consultation.id).exists())

    def test_appointment_patient_and_doctor_immutable_after_creation(self):
        """Attempting to change appointment, patient, or doctor is rejected with 400 for doctor and admin."""
        url = self.detail_url(self.consultation.id)

        # 1. Doctor attempts to change appointment
        self.client.force_authenticate(user=self.doctor_1)
        res_appt = self.client.patch(url, {'appointment': str(self.appt_2.id)}, format='json')
        self.assertEqual(res_appt.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('appointment', self.get_error_details(res_appt))

        # 2. Doctor attempts to change patient
        res_pat = self.client.patch(url, {'patient': str(self.patient_2.id)}, format='json')
        self.assertEqual(res_pat.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(res_pat))

        # 3. Doctor attempts to change doctor
        res_doc = self.client.patch(url, {'doctor': str(self.doctor_2.id)}, format='json')
        self.assertEqual(res_doc.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(res_doc))

        # 4. Admin attempts to change patient or doctor
        self.client.force_authenticate(user=self.admin)
        res_adm_pat = self.client.patch(url, {'patient': str(self.patient_2.id)}, format='json')
        self.assertEqual(res_adm_pat.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(res_adm_pat))

        # 5. Supplying unchanged values succeeds
        self.client.force_authenticate(user=self.doctor_1)
        res_unchanged = self.client.patch(url, {
            'appointment': str(self.appt_1.id),
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_1.id),
            'chief_complaint': 'Updated chief complaint',
        }, format='json')
        self.assertEqual(res_unchanged.status_code, status.HTTP_200_OK)

        self.consultation.refresh_from_db()
        self.assertEqual(str(self.consultation.appointment.id), str(self.appt_1.id))
        self.assertEqual(self.consultation.patient, self.patient_1)
        self.assertEqual(self.consultation.doctor, self.doctor_1)
        self.assertEqual(self.consultation.chief_complaint, 'Updated chief complaint')

    def test_generic_put_patch_rejects_status_changes(self):
        """Generic PUT/PATCH requests attempting to change status are rejected with 400."""
        url = self.detail_url(self.consultation.id)

        # Doctor PATCH status
        self.client.force_authenticate(user=self.doctor_1)
        res_patch = self.client.patch(url, {'status': 'in_progress'}, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', self.get_error_details(res_patch))

        # Admin PATCH status
        self.client.force_authenticate(user=self.admin)
        res_admin = self.client.patch(url, {'status': 'completed'}, format='json')
        self.assertEqual(res_admin.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', self.get_error_details(res_admin))

        # Unchanged status is accepted
        self.client.force_authenticate(user=self.doctor_1)
        res_same = self.client.patch(url, {
            'status': 'scheduled',
            'chief_complaint': 'Complaint with same status',
        }, format='json')
        self.assertEqual(res_same.status_code, status.HTTP_200_OK)

        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'scheduled')

    def test_lifecycle_actions_control_status_for_assigned_doctor_and_admin(self):
        """Only assigned doctor and admin can trigger start and end actions to update status."""
        self.client.force_authenticate(user=self.doctor_1)

        # 1. Start action
        res_start = self.client.post(self.start_url(self.consultation.id))
        self.assertEqual(res_start.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'in_progress')
        self.assertIsNotNone(self.consultation.started_at)

        # 2. End action by admin
        self.client.force_authenticate(user=self.admin)
        res_end = self.client.post(self.end_url(self.consultation.id), {
            'diagnosis': 'Final Diagnosis',
            'clinical_notes': 'Final clinical notes',
        }, format='json')
        self.assertEqual(res_end.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'completed')
        self.assertIsNotNone(self.consultation.ended_at)
        self.assertEqual(self.consultation.diagnosis, 'Final Diagnosis')

    def test_cross_doctor_attempts_denied_and_leave_rows_unchanged(self):
        """An unassigned doctor receives 404 and cannot read, edit, delete, start, end, or message."""
        self.client.force_authenticate(user=self.doctor_2)
        url = self.detail_url(self.consultation.id)

        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.patch(url, {'clinical_notes': 'Hacked'}).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(self.start_url(self.consultation.id)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(self.end_url(self.consultation.id)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.post(self.messages_url(self.consultation.id), {'message': 'Hacked'}).status_code,
            status.HTTP_404_NOT_FOUND,
        )

        # Verify consultation and messages are unchanged
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.clinical_notes, 'Initial notes')
        self.assertEqual(self.consultation.status, 'scheduled')
        self.assertEqual(self.consultation.messages.count(), 0)

    def test_unrelated_patient_cannot_access_or_send_messages(self):
        """Unrelated patients cannot access or message another patient's consultation."""
        self.client.force_authenticate(user=self.patient_2)
        url = self.detail_url(self.consultation.id)

        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.post(self.messages_url(self.consultation.id), {'message': 'Cross patient'}).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.consultation.messages.count(), 0)


class ConsultationLifecycleTransitionTests(APITestCase):
    """
    Feature 3F: Validate consultation lifecycle transitions.

    Rules:
    - start permits only scheduled -> in_progress.
    - end permits only in_progress -> completed.
    - Invalid or repeated transitions return 409 without changing status, timestamps, or clinical fields.
    - Completed and cancelled consultations cannot restart.
    - Set timestamps server-side; successful completion preserves started_at.
    - Validate end-action clinical fields through a serializer. Parse follow_up_required correctly; never use bool(request.data[...]).
    - Malformed bodies and invalid fields return 400 before any writes.
    - Make transition checks and persistence atomic, with appropriate row locking.
    - Preserve Feature 3E authorization and ownership rules.
    """

    def setUp(self):
        # Patient
        self.patient = User.objects.create_user(
            email='pat_f3f@example.com',
            password='Password123!@#',
            role='patient',
        )
        UserProfile.objects.create(user=self.patient, first_name='Patient', last_name='F3F')

        # Assigned Doctor
        self.doctor = User.objects.create_user(
            email='doc_f3f@example.com',
            password='Password123!@#',
            role='doctor',
        )
        UserProfile.objects.create(user=self.doctor, first_name='Doctor', last_name='F3F')
        DoctorProfile.objects.create(user=self.doctor, specialization='General Medicine', license_number='DOC_F3F')

        # Other Doctor
        self.other_doctor = User.objects.create_user(
            email='otherdoc_f3f@example.com',
            password='Password123!@#',
            role='doctor',
        )
        UserProfile.objects.create(user=self.other_doctor, first_name='Other', last_name='Doctor')
        DoctorProfile.objects.create(user=self.other_doctor, specialization='Cardiology', license_number='OTHERDOC_F3F')

        # Admin
        self.admin = User.objects.create_user(
            email='admin_f3f@example.com',
            password='Password123!@#',
            role='admin',
            is_staff=True,
        )

        # Confirmed appointment
        now = timezone.now()
        self.appointment = Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            status='confirmed',
            scheduled_start=now + datetime.timedelta(days=1),
            scheduled_end=now + datetime.timedelta(days=1, hours=1),
            reason='Routine checkup',
        )

        # Baseline consultation in 'scheduled' status
        self.consultation = Consultation.objects.create(
            appointment=self.appointment,
            patient=self.patient,
            doctor=self.doctor,
            status='scheduled',
            chief_complaint='Persistent cough',
            diagnosis='Initial observation',
            clinical_notes='Awaiting examination',
            follow_up_required=False,
            follow_up_notes='Initial plan',
        )

    def start_url(self, pk):
        return reverse('consultation-start', kwargs={'pk': pk})

    def end_url(self, pk):
        return reverse('consultation-end', kwargs={'pk': pk})

    def detail_url(self, pk):
        return reverse('consultation-detail', kwargs={'pk': pk})

    # =========================================================================
    # 1. Transition Matrix: start permits only scheduled -> in_progress
    # =========================================================================

    def test_start_valid_transition_scheduled_to_in_progress(self):
        """start permits scheduled -> in_progress and sets started_at server-side."""
        self.client.force_authenticate(user=self.doctor)
        before = timezone.now()

        res = self.client.post(self.start_url(self.consultation.id))
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'in_progress')
        self.assertIsNotNone(self.consultation.started_at)
        self.assertGreaterEqual(self.consultation.started_at, before)
        self.assertIsNone(self.consultation.ended_at)
        self.assertEqual(res.data['status'], 'in_progress')

    def test_start_repeated_and_invalid_transitions_return_409(self):
        """start rejects in_progress, completed, and cancelled with 409 without modifying state."""
        self.client.force_authenticate(user=self.doctor)

        # Case 1: Repeated start on in_progress
        self.consultation.status = 'in_progress'
        fixed_started_at = timezone.now() - datetime.timedelta(minutes=15)
        self.consultation.started_at = fixed_started_at
        self.consultation.save()

        res_rep = self.client.post(self.start_url(self.consultation.id))
        self.assertEqual(res_rep.status_code, status.HTTP_409_CONFLICT)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'in_progress')
        self.assertEqual(self.consultation.started_at, fixed_started_at)
        self.assertIsNone(self.consultation.ended_at)

        # Case 2: Cannot restart completed consultation
        self.consultation.status = 'completed'
        fixed_ended_at = timezone.now() - datetime.timedelta(minutes=5)
        self.consultation.ended_at = fixed_ended_at
        self.consultation.save()

        res_comp = self.client.post(self.start_url(self.consultation.id))
        self.assertEqual(res_comp.status_code, status.HTTP_409_CONFLICT)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'completed')
        self.assertEqual(self.consultation.started_at, fixed_started_at)
        self.assertEqual(self.consultation.ended_at, fixed_ended_at)

        # Case 3: Cannot restart cancelled consultation
        self.consultation.status = 'cancelled'
        self.consultation.save()

        res_canc = self.client.post(self.start_url(self.consultation.id))
        self.assertEqual(res_canc.status_code, status.HTTP_409_CONFLICT)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'cancelled')

    # =========================================================================
    # 2. Transition Matrix: end permits only in_progress -> completed
    # =========================================================================

    def test_end_valid_transition_in_progress_to_completed_and_preserves_started_at(self):
        """end permits in_progress -> completed, sets ended_at, and preserves started_at."""
        self.client.force_authenticate(user=self.doctor)
        fixed_started_at = timezone.now() - datetime.timedelta(minutes=30)
        self.consultation.status = 'in_progress'
        self.consultation.started_at = fixed_started_at
        self.consultation.save()

        before = timezone.now()
        res = self.client.post(self.end_url(self.consultation.id), {
            'diagnosis': 'Acute Bronchitis',
            'clinical_notes': 'Prescribed rest and hydration.',
            'follow_up_required': True,
            'follow_up_notes': 'Return in 10 days if symptoms persist.',
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'completed')
        self.assertEqual(self.consultation.started_at, fixed_started_at)  # Preserved!
        self.assertIsNotNone(self.consultation.ended_at)
        self.assertGreaterEqual(self.consultation.ended_at, before)
        self.assertEqual(self.consultation.diagnosis, 'Acute Bronchitis')
        self.assertEqual(self.consultation.clinical_notes, 'Prescribed rest and hydration.')
        self.assertTrue(self.consultation.follow_up_required)
        self.assertEqual(self.consultation.follow_up_notes, 'Return in 10 days if symptoms persist.')

    def test_end_repeated_and_invalid_transitions_return_409(self):
        """end rejects scheduled, completed, and cancelled consultations with 409."""
        self.client.force_authenticate(user=self.doctor)

        # Case 1: end on scheduled (cannot end before start)
        self.consultation.status = 'scheduled'
        self.consultation.save()

        res_sched = self.client.post(self.end_url(self.consultation.id), {
            'diagnosis': 'Premature end',
        }, format='json')
        self.assertEqual(res_sched.status_code, status.HTTP_409_CONFLICT)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'scheduled')
        self.assertIsNone(self.consultation.started_at)
        self.assertIsNone(self.consultation.ended_at)
        self.assertEqual(self.consultation.diagnosis, 'Initial observation')

        # Case 2: Repeated end on completed
        self.consultation.status = 'completed'
        fixed_started_at = timezone.now() - datetime.timedelta(hours=1)
        fixed_ended_at = timezone.now() - datetime.timedelta(minutes=30)
        self.consultation.started_at = fixed_started_at
        self.consultation.ended_at = fixed_ended_at
        self.consultation.save()

        res_comp = self.client.post(self.end_url(self.consultation.id), {
            'diagnosis': 'Overwriting diagnosis',
        }, format='json')
        self.assertEqual(res_comp.status_code, status.HTTP_409_CONFLICT)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'completed')
        self.assertEqual(self.consultation.started_at, fixed_started_at)
        self.assertEqual(self.consultation.ended_at, fixed_ended_at)
        self.assertEqual(self.consultation.diagnosis, 'Initial observation')

        # Case 3: end on cancelled
        self.consultation.status = 'cancelled'
        self.consultation.save()

        res_canc = self.client.post(self.end_url(self.consultation.id), {
            'diagnosis': 'Cancelled end',
        }, format='json')
        self.assertEqual(res_canc.status_code, status.HTTP_409_CONFLICT)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'cancelled')

    # =========================================================================
    # 3. Boolean Validation for follow_up_required
    # =========================================================================

    def test_follow_up_required_boolean_parsing(self):
        """follow_up_required correctly handles booleans, strings 'true'/'false', 0/1, and rejects invalid strings."""
        self.client.force_authenticate(user=self.doctor)

        # Subtest 1: 'false' string must be False (not True like python bool('false'))
        self.consultation.status = 'in_progress'
        self.consultation.follow_up_required = True
        self.consultation.save()
        res = self.client.post(self.end_url(self.consultation.id), {
            'follow_up_required': 'false',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertFalse(self.consultation.follow_up_required)

        # Subtest 2: '0' string must be False
        self.consultation.status = 'in_progress'
        self.consultation.follow_up_required = True
        self.consultation.save()
        res = self.client.post(self.end_url(self.consultation.id), {
            'follow_up_required': '0',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertFalse(self.consultation.follow_up_required)

        # Subtest 3: raw boolean False
        self.consultation.status = 'in_progress'
        self.consultation.follow_up_required = True
        self.consultation.save()
        res = self.client.post(self.end_url(self.consultation.id), {
            'follow_up_required': False,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertFalse(self.consultation.follow_up_required)

        # Subtest 4: 'true' string must be True
        self.consultation.status = 'in_progress'
        self.consultation.follow_up_required = False
        self.consultation.save()
        res = self.client.post(self.end_url(self.consultation.id), {
            'follow_up_required': 'true',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertTrue(self.consultation.follow_up_required)

        # Subtest 5: '1' string must be True
        self.consultation.status = 'in_progress'
        self.consultation.follow_up_required = False
        self.consultation.save()
        res = self.client.post(self.end_url(self.consultation.id), {
            'follow_up_required': '1',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertTrue(self.consultation.follow_up_required)

        # Subtest 6: Invalid string returns 400 Bad Request without writing
        self.consultation.status = 'in_progress'
        self.consultation.follow_up_required = False
        self.consultation.save()
        res = self.client.post(self.end_url(self.consultation.id), {
            'follow_up_required': 'invalid_boolean',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'in_progress')
        self.assertFalse(self.consultation.follow_up_required)

        # Subtest 7: null/None returns 400 Bad Request
        res_null = self.client.post(self.end_url(self.consultation.id), {
            'follow_up_required': None,
        }, format='json')
        self.assertEqual(res_null.status_code, status.HTTP_400_BAD_REQUEST)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'in_progress')

    def test_end_omitted_follow_up_required_and_clinical_fields_preserve_stored_values(self):
        """Ending a consultation with omitted optional clinical fields preserves stored values.

        Starting with follow_up_required=True:
        - Multipart end omitting the flag preserves True.
        - JSON {} and bodyless end preserve True.
        - Explicit false changes it to False.
        - Invalid boolean values return 400.
        """
        self.client.force_authenticate(user=self.doctor)

        # 1. Multipart end omitting follow_up_required preserves True
        self.consultation.status = 'in_progress'
        self.consultation.follow_up_required = True
        self.consultation.diagnosis = 'Stored diagnosis'
        self.consultation.clinical_notes = 'Stored notes'
        self.consultation.follow_up_notes = 'Stored follow up notes'
        self.consultation.save()

        res_multipart = self.client.post(
            self.end_url(self.consultation.id),
            data={'diagnosis': 'Updated via multipart'},
            format='multipart',
        )
        self.assertEqual(res_multipart.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'completed')
        self.assertTrue(self.consultation.follow_up_required)
        self.assertEqual(self.consultation.diagnosis, 'Updated via multipart')
        self.assertEqual(self.consultation.clinical_notes, 'Stored notes')
        self.assertEqual(self.consultation.follow_up_notes, 'Stored follow up notes')

        # 2. JSON {} end preserves True and all stored clinical fields
        self.consultation.status = 'in_progress'
        self.consultation.follow_up_required = True
        self.consultation.diagnosis = 'Preserved diagnosis'
        self.consultation.clinical_notes = 'Preserved notes'
        self.consultation.follow_up_notes = 'Preserved follow up'
        self.consultation.save()

        res_empty_json = self.client.post(
            self.end_url(self.consultation.id),
            data={},
            format='json',
        )
        self.assertEqual(res_empty_json.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'completed')
        self.assertTrue(self.consultation.follow_up_required)
        self.assertEqual(self.consultation.diagnosis, 'Preserved diagnosis')
        self.assertEqual(self.consultation.clinical_notes, 'Preserved notes')
        self.assertEqual(self.consultation.follow_up_notes, 'Preserved follow up')

        # 3. Bodyless end preserves True and all stored clinical fields
        self.consultation.status = 'in_progress'
        self.consultation.follow_up_required = True
        self.consultation.diagnosis = 'Preserved diagnosis'
        self.consultation.clinical_notes = 'Preserved notes'
        self.consultation.follow_up_notes = 'Preserved follow up'
        self.consultation.save()

        res_bodyless = self.client.post(self.end_url(self.consultation.id))
        self.assertEqual(res_bodyless.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'completed')
        self.assertTrue(self.consultation.follow_up_required)
        self.assertEqual(self.consultation.diagnosis, 'Preserved diagnosis')
        self.assertEqual(self.consultation.clinical_notes, 'Preserved notes')
        self.assertEqual(self.consultation.follow_up_notes, 'Preserved follow up')

        # 4. Explicit false changes follow_up_required to False (tested in JSON and multipart)
        # 4a. Explicit false in JSON
        self.consultation.status = 'in_progress'
        self.consultation.follow_up_required = True
        self.consultation.save()

        res_false_json = self.client.post(
            self.end_url(self.consultation.id),
            data={'follow_up_required': False},
            format='json',
        )
        self.assertEqual(res_false_json.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'completed')
        self.assertFalse(self.consultation.follow_up_required)

        # 4b. Explicit false in multipart ('false')
        self.consultation.status = 'in_progress'
        self.consultation.follow_up_required = True
        self.consultation.save()

        res_false_multipart = self.client.post(
            self.end_url(self.consultation.id),
            data={'follow_up_required': 'false'},
            format='multipart',
        )
        self.assertEqual(res_false_multipart.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'completed')
        self.assertFalse(self.consultation.follow_up_required)

        # 5. Invalid boolean values must still return 400 and preserve stored state
        self.consultation.status = 'in_progress'
        self.consultation.follow_up_required = True
        self.consultation.save()

        res_invalid_multipart = self.client.post(
            self.end_url(self.consultation.id),
            data={'follow_up_required': 'not_a_boolean'},
            format='multipart',
        )
        self.assertEqual(res_invalid_multipart.status_code, status.HTTP_400_BAD_REQUEST)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'in_progress')
        self.assertTrue(self.consultation.follow_up_required)

    # =========================================================================
    # 4. Malformed Bodies and Invalid Fields Return 400 Before Any Writes
    # =========================================================================

    def test_start_malformed_bodies_and_invalid_fields_return_400(self):
        """start returns 400 before any writes when body is non-mapping or contains invalid fields."""
        self.client.force_authenticate(user=self.doctor)

        # Array body
        res_list = self.client.post(self.start_url(self.consultation.id), data=[], format='json')
        self.assertEqual(res_list.status_code, status.HTTP_400_BAD_REQUEST)

        # String body
        res_str = self.client.post(self.start_url(self.consultation.id), data='invalid', format='json')
        self.assertEqual(res_str.status_code, status.HTTP_400_BAD_REQUEST)

        # Number body
        res_num = self.client.post(self.start_url(self.consultation.id), data=42, format='json')
        self.assertEqual(res_num.status_code, status.HTTP_400_BAD_REQUEST)

        # Unexpected/invalid field
        res_field = self.client.post(
            self.start_url(self.consultation.id),
            data={'unexpected_param': 'test'},
            format='json',
        )
        self.assertEqual(res_field.status_code, status.HTTP_400_BAD_REQUEST)

        # State remains scheduled and unwritten
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'scheduled')
        self.assertIsNone(self.consultation.started_at)

    def test_end_malformed_bodies_and_invalid_fields_return_400(self):
        """end returns 400 before any writes when body is non-mapping or contains invalid fields."""
        self.client.force_authenticate(user=self.doctor)
        self.consultation.status = 'in_progress'
        fixed_started_at = timezone.now() - datetime.timedelta(minutes=20)
        self.consultation.started_at = fixed_started_at
        self.consultation.save()

        # Array body
        res_list = self.client.post(self.end_url(self.consultation.id), data=[], format='json')
        self.assertEqual(res_list.status_code, status.HTTP_400_BAD_REQUEST)

        # String body
        res_str = self.client.post(self.end_url(self.consultation.id), data='invalid', format='json')
        self.assertEqual(res_str.status_code, status.HTTP_400_BAD_REQUEST)

        # Number body
        res_num = self.client.post(self.end_url(self.consultation.id), data=42, format='json')
        self.assertEqual(res_num.status_code, status.HTTP_400_BAD_REQUEST)

        # Unexpected/invalid field
        res_field = self.client.post(
            self.end_url(self.consultation.id),
            data={'invalid_field_name': 'value'},
            format='json',
        )
        self.assertEqual(res_field.status_code, status.HTTP_400_BAD_REQUEST)

        # State remains in_progress and clinical fields untouched
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'in_progress')
        self.assertEqual(self.consultation.started_at, fixed_started_at)
        self.assertIsNone(self.consultation.ended_at)
        self.assertEqual(self.consultation.diagnosis, 'Initial observation')

    def test_start_and_end_reject_explicit_json_empty_strings_and_null(self):
        """start and end reject raw application/json bodies '\"\"' and 'null' with 400 without modifying state."""
        self.client.force_authenticate(user=self.doctor)

        # 1. start with '""'
        res_start_str = self.client.post(
            self.start_url(self.consultation.id),
            data='""',
            content_type='application/json',
        )
        self.assertEqual(res_start_str.status_code, status.HTTP_400_BAD_REQUEST)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'scheduled')
        self.assertIsNone(self.consultation.started_at)
        self.assertIsNone(self.consultation.ended_at)
        self.assertEqual(self.consultation.diagnosis, 'Initial observation')
        self.assertEqual(self.consultation.clinical_notes, 'Awaiting examination')
        self.assertFalse(self.consultation.follow_up_required)
        self.assertEqual(self.consultation.follow_up_notes, 'Initial plan')

        # 2. start with 'null'
        res_start_null = self.client.post(
            self.start_url(self.consultation.id),
            data='null',
            content_type='application/json',
        )
        self.assertEqual(res_start_null.status_code, status.HTTP_400_BAD_REQUEST)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'scheduled')
        self.assertIsNone(self.consultation.started_at)
        self.assertIsNone(self.consultation.ended_at)
        self.assertEqual(self.consultation.diagnosis, 'Initial observation')
        self.assertEqual(self.consultation.clinical_notes, 'Awaiting examination')
        self.assertFalse(self.consultation.follow_up_required)
        self.assertEqual(self.consultation.follow_up_notes, 'Initial plan')

        # Advance consultation to in_progress to test end
        fixed_started_at = timezone.now() - datetime.timedelta(minutes=10)
        self.consultation.status = 'in_progress'
        self.consultation.started_at = fixed_started_at
        self.consultation.save()

        # 3. end with '""'
        res_end_str = self.client.post(
            self.end_url(self.consultation.id),
            data='""',
            content_type='application/json',
        )
        self.assertEqual(res_end_str.status_code, status.HTTP_400_BAD_REQUEST)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'in_progress')
        self.assertEqual(self.consultation.started_at, fixed_started_at)
        self.assertIsNone(self.consultation.ended_at)
        self.assertEqual(self.consultation.diagnosis, 'Initial observation')
        self.assertEqual(self.consultation.clinical_notes, 'Awaiting examination')
        self.assertFalse(self.consultation.follow_up_required)
        self.assertEqual(self.consultation.follow_up_notes, 'Initial plan')

        # 4. end with 'null'
        res_end_null = self.client.post(
            self.end_url(self.consultation.id),
            data='null',
            content_type='application/json',
        )
        self.assertEqual(res_end_null.status_code, status.HTTP_400_BAD_REQUEST)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'in_progress')
        self.assertEqual(self.consultation.started_at, fixed_started_at)
        self.assertIsNone(self.consultation.ended_at)
        self.assertEqual(self.consultation.diagnosis, 'Initial observation')
        self.assertEqual(self.consultation.clinical_notes, 'Awaiting examination')
        self.assertFalse(self.consultation.follow_up_required)
        self.assertEqual(self.consultation.follow_up_notes, 'Initial plan')

    def test_start_and_end_accept_bodyless_and_empty_dict(self):
        """Genuinely bodyless requests and {} are accepted."""
        self.client.force_authenticate(user=self.doctor)

        # 1. Bodyless start
        res_bodyless = self.client.post(self.start_url(self.consultation.id))
        self.assertEqual(res_bodyless.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'in_progress')
        self.assertIsNotNone(self.consultation.started_at)

        # 2. Empty dict end
        res_dict = self.client.post(self.end_url(self.consultation.id), data={}, format='json')
        self.assertEqual(res_dict.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'completed')
        self.assertIsNotNone(self.consultation.ended_at)

    # =========================================================================
    # 5. Role Permissions and Authorization (Feature 3E Rules Preserved)
    # =========================================================================

    def test_role_authorization_preserved_on_start_and_end(self):
        """Patients, unassigned doctors, and unauthenticated users cannot invoke start/end."""
        # Patient
        self.client.force_authenticate(user=self.patient)
        self.assertEqual(self.client.post(self.start_url(self.consultation.id)).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(self.end_url(self.consultation.id)).status_code, status.HTTP_403_FORBIDDEN)

        # Unassigned doctor (returns 404 because scoped queryset hides it)
        self.client.force_authenticate(user=self.other_doctor)
        self.assertEqual(self.client.post(self.start_url(self.consultation.id)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(self.end_url(self.consultation.id)).status_code, status.HTTP_404_NOT_FOUND)

        # Unauthenticated
        self.client.logout()
        self.assertEqual(self.client.post(self.start_url(self.consultation.id)).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(self.end_url(self.consultation.id)).status_code, status.HTTP_401_UNAUTHORIZED)

        # Admin can start and end
        self.client.force_authenticate(user=self.admin)
        res_start = self.client.post(self.start_url(self.consultation.id))
        self.assertEqual(res_start.status_code, status.HTTP_200_OK)
        res_end = self.client.post(self.end_url(self.consultation.id), {
            'diagnosis': 'Admin completed consultation',
        }, format='json')
        self.assertEqual(res_end.status_code, status.HTTP_200_OK)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.status, 'completed')

