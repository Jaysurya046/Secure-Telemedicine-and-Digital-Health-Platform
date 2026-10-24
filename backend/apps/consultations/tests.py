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

