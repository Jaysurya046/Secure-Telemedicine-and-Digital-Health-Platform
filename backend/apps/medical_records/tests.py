"""
Regression and security tests for medical record and prescription write permissions and scoped access.
"""
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIRequestFactory

from apps.consultations.models import Consultation
from apps.medical_records.models import MedicalRecord, Prescription, PrescriptionItem
from apps.medical_records.permissions import ClinicalRecordPermission

User = get_user_model()


class BaseClinicalAccessTestCase(APITestCase):
    """Base setup with fixture users, medical records, and prescriptions with items."""

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

        # Unsupported role user
        self.unsupported_user = User.objects.create_user(
            email='nurse@example.com',
            password='Password123!@#',
            role='nurse',
        )

        # Records
        self.record_doc1_pat1 = MedicalRecord.objects.create(
            patient=self.patient_1,
            doctor=self.doctor_1,
            record_type='consultation',
            title='Record Doc1 Pat1 Initial',
            description='Initial consultation details',
            is_sensitive=True,
        )
        self.record_doc2_pat2 = MedicalRecord.objects.create(
            patient=self.patient_2,
            doctor=self.doctor_2,
            record_type='lab',
            title='Record Doc2 Pat2 Lab',
            description='Lab results details',
            is_sensitive=True,
        )

        # Prescriptions with items
        self.rx_doc1_pat1 = Prescription.objects.create(
            patient=self.patient_1,
            doctor=self.doctor_1,
            status='active',
            instructions='Original Rx instructions Doc1 Pat1',
        )
        self.rx_item_1 = PrescriptionItem.objects.create(
            prescription=self.rx_doc1_pat1,
            medication_name='Amoxicillin',
            dosage='500mg',
            frequency='3x daily',
            duration='7 days',
            instructions='Take after food',
        )
        self.rx_item_2 = PrescriptionItem.objects.create(
            prescription=self.rx_doc1_pat1,
            medication_name='Ibuprofen',
            dosage='400mg',
            frequency='as needed',
            duration='5 days',
            instructions='Take with water',
        )

        self.rx_doc2_pat2 = Prescription.objects.create(
            patient=self.patient_2,
            doctor=self.doctor_2,
            status='active',
            instructions='Original Rx instructions Doc2 Pat2',
        )
        self.rx2_item_1 = PrescriptionItem.objects.create(
            prescription=self.rx_doc2_pat2,
            medication_name='Metformin',
            dosage='850mg',
            frequency='2x daily',
            duration='30 days',
            instructions='Take with meals',
        )

        # URLs
        self.record_list_url = reverse('medical-record-list')
        self.prescription_list_url = reverse('prescription-list')

    def record_detail_url(self, pk):
        return reverse('medical-record-detail', kwargs={'pk': pk})

    def prescription_detail_url(self, pk):
        return reverse('prescription-detail', kwargs={'pk': pk})

    def prescription_cancel_url(self, pk):
        return reverse('prescription-cancel', kwargs={'pk': pk})

    def get_error_details(self, response):
        """Helper to extract field errors from standard or custom DRF responses."""
        if isinstance(response.data, dict) and 'details' in response.data:
            return response.data['details']
        return response.data


class PatientClinicalWritePermissionTests(BaseClinicalAccessTestCase):
    """
    Verify patients can list/retrieve their own records and prescriptions,
    but cannot POST, PUT, PATCH, DELETE, or cancel prescriptions.
    Verify database rows and prescription items remain completely unchanged.
    """

    def test_patient_cannot_post_medical_record(self):
        """Patient attempting POST /api/medical-records/ is denied with 403."""
        self.client.force_authenticate(user=self.patient_1)
        initial_count = MedicalRecord.objects.count()
        payload = {
            'patient': str(self.patient_1.id),
            'record_type': 'consultation',
            'title': 'Self Created Record',
            'description': 'Patient self note',
        }
        response = self.client.post(self.record_list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(MedicalRecord.objects.count(), initial_count)
        self.assertFalse(MedicalRecord.objects.filter(title='Self Created Record').exists())

    def test_patient_cannot_put_own_medical_record(self):
        """Patient attempting PUT on their own record is denied with 403; row unchanged."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.record_detail_url(self.record_doc1_pat1.id)
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_1.id),
            'record_type': 'consultation',
            'title': 'Overwritten Title By Patient',
            'description': 'Overwritten Description By Patient',
        }
        response = self.client.put(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.record_doc1_pat1.refresh_from_db()
        self.assertEqual(self.record_doc1_pat1.title, 'Record Doc1 Pat1 Initial')
        self.assertEqual(self.record_doc1_pat1.description, 'Initial consultation details')

    def test_patient_cannot_patch_own_medical_record(self):
        """Patient attempting PATCH on their own record is denied with 403; row unchanged."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.record_detail_url(self.record_doc1_pat1.id)
        payload = {'title': 'Patched Title By Patient'}
        response = self.client.patch(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.record_doc1_pat1.refresh_from_db()
        self.assertEqual(self.record_doc1_pat1.title, 'Record Doc1 Pat1 Initial')

    def test_patient_cannot_delete_own_medical_record(self):
        """Patient attempting DELETE on their own record is denied with 403; row still exists."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.record_detail_url(self.record_doc1_pat1.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(MedicalRecord.objects.filter(id=self.record_doc1_pat1.id).exists())

    def test_patient_cannot_post_prescription(self):
        """Patient attempting POST /api/medical-records/prescriptions/ is denied with 403."""
        self.client.force_authenticate(user=self.patient_1)
        initial_rx_count = Prescription.objects.count()
        initial_item_count = PrescriptionItem.objects.count()
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_1.id),
            'instructions': 'Patient forged prescription',
            'items': [
                {
                    'medication_name': 'Morphine',
                    'dosage': '100mg',
                    'frequency': 'hourly',
                    'duration': '30 days',
                }
            ],
        }
        response = self.client.post(self.prescription_list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Prescription.objects.count(), initial_rx_count)
        self.assertEqual(PrescriptionItem.objects.count(), initial_item_count)

    def test_patient_cannot_put_own_prescription(self):
        """Patient attempting PUT on own prescription is denied; row and items unchanged."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.prescription_detail_url(self.rx_doc1_pat1.id)
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_1.id),
            'instructions': 'Maliciously altered instructions',
            'items': [
                {
                    'medication_name': 'Forged Med',
                    'dosage': '999mg',
                    'frequency': 'continuous',
                    'duration': '99 days',
                }
            ],
        }
        response = self.client.put(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.rx_doc1_pat1.refresh_from_db()
        self.assertEqual(self.rx_doc1_pat1.instructions, 'Original Rx instructions Doc1 Pat1')

        # Check prescription items remained intact
        items = list(self.rx_doc1_pat1.items.order_by('medication_name').values_list('medication_name', 'dosage'))
        self.assertEqual(len(items), 2)
        self.assertEqual(items, [('Amoxicillin', '500mg'), ('Ibuprofen', '400mg')])

    def test_patient_cannot_patch_own_prescription(self):
        """Patient attempting PATCH on own prescription is denied; row and items unchanged."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.prescription_detail_url(self.rx_doc1_pat1.id)
        payload = {'instructions': 'Patched by patient'}
        response = self.client.patch(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.rx_doc1_pat1.refresh_from_db()
        self.assertEqual(self.rx_doc1_pat1.instructions, 'Original Rx instructions Doc1 Pat1')
        self.assertEqual(self.rx_doc1_pat1.items.count(), 2)

    def test_patient_cannot_delete_own_prescription(self):
        """Patient attempting DELETE on own prescription is denied; row and items still exist."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.prescription_detail_url(self.rx_doc1_pat1.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.assertTrue(Prescription.objects.filter(id=self.rx_doc1_pat1.id).exists())
        self.assertEqual(PrescriptionItem.objects.filter(prescription=self.rx_doc1_pat1).count(), 2)

    def test_patient_cannot_cancel_own_prescription(self):
        """Patient attempting POST cancel action is denied with 403; status remains active."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.prescription_cancel_url(self.rx_doc1_pat1.id)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.rx_doc1_pat1.refresh_from_db()
        self.assertEqual(self.rx_doc1_pat1.status, 'active')


class CrossPatientAccessTests(BaseClinicalAccessTestCase):
    """
    Verify patients can only read their own records and prescriptions.
    Cross-patient reads are strictly prevented.
    """

    def test_patient_list_medical_records_scoped_to_self(self):
        """Patient 1 only sees their own medical records in list."""
        self.client.force_authenticate(user=self.patient_1)
        response = self.client.get(self.record_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data.get('results', response.data)
        returned_ids = [str(r['id']) for r in results]
        self.assertIn(str(self.record_doc1_pat1.id), returned_ids)
        self.assertNotIn(str(self.record_doc2_pat2.id), returned_ids)

    def test_cross_patient_medical_record_retrieve_denied(self):
        """Patient 1 retrieving Patient 2's medical record is denied (404 Not Found)."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.record_detail_url(self.record_doc2_pat2.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_retrieve_own_medical_record_succeeds(self):
        """Patient 1 can successfully retrieve their own medical record."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.record_detail_url(self.record_doc1_pat1.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data['id']), str(self.record_doc1_pat1.id))

    def test_patient_list_prescriptions_scoped_to_self(self):
        """Patient 1 only sees their own prescriptions in list."""
        self.client.force_authenticate(user=self.patient_1)
        response = self.client.get(self.prescription_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data.get('results', response.data)
        returned_ids = [str(r['id']) for r in results]
        self.assertIn(str(self.rx_doc1_pat1.id), returned_ids)
        self.assertNotIn(str(self.rx_doc2_pat2.id), returned_ids)

    def test_cross_patient_prescription_retrieve_denied(self):
        """Patient 1 retrieving Patient 2's prescription is denied (404 Not Found)."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.prescription_detail_url(self.rx_doc2_pat2.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patient_retrieve_own_prescription_succeeds(self):
        """Patient 1 can successfully retrieve their own prescription with items."""
        self.client.force_authenticate(user=self.patient_1)
        url = self.prescription_detail_url(self.rx_doc1_pat1.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data['id']), str(self.rx_doc1_pat1.id))
        self.assertEqual(len(response.data['items']), 2)


class CrossDoctorAccessTests(BaseClinicalAccessTestCase):
    """
    Verify doctors can access and modify only objects assigned to them.
    Doctor 1 cannot access, modify, delete, or cancel Doctor 2's objects.
    Verify database rows and prescription items remain unchanged on denied operations.
    """

    def test_doctor_list_medical_records_scoped_to_assigned(self):
        """Doctor 1 only sees records assigned to Doctor 1."""
        self.client.force_authenticate(user=self.doctor_1)
        response = self.client.get(self.record_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data.get('results', response.data)
        returned_ids = [str(r['id']) for r in results]
        self.assertIn(str(self.record_doc1_pat1.id), returned_ids)
        self.assertNotIn(str(self.record_doc2_pat2.id), returned_ids)

    def test_doctor_retrieve_other_doctor_medical_record_denied(self):
        """Doctor 1 cannot retrieve Doctor 2's medical record."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.record_detail_url(self.record_doc2_pat2.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_doctor_patch_other_doctor_medical_record_denied(self):
        """Doctor 1 cannot modify Doctor 2's record; row unchanged."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.record_detail_url(self.record_doc2_pat2.id)
        response = self.client.patch(url, {'title': 'Modified by Doc1'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.record_doc2_pat2.refresh_from_db()
        self.assertEqual(self.record_doc2_pat2.title, 'Record Doc2 Pat2 Lab')

    def test_doctor_delete_other_doctor_medical_record_denied(self):
        """Doctor 1 cannot delete Doctor 2's record; row still exists."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.record_detail_url(self.record_doc2_pat2.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.assertTrue(MedicalRecord.objects.filter(id=self.record_doc2_pat2.id).exists())

    def test_doctor_list_prescriptions_scoped_to_assigned(self):
        """Doctor 1 only sees prescriptions assigned to Doctor 1."""
        self.client.force_authenticate(user=self.doctor_1)
        response = self.client.get(self.prescription_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data.get('results', response.data)
        returned_ids = [str(r['id']) for r in results]
        self.assertIn(str(self.rx_doc1_pat1.id), returned_ids)
        self.assertNotIn(str(self.rx_doc2_pat2.id), returned_ids)

    def test_doctor_retrieve_other_doctor_prescription_denied(self):
        """Doctor 1 cannot retrieve Doctor 2's prescription."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.prescription_detail_url(self.rx_doc2_pat2.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_doctor_patch_other_doctor_prescription_denied(self):
        """Doctor 1 cannot modify Doctor 2's prescription; row and items unchanged."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.prescription_detail_url(self.rx_doc2_pat2.id)
        response = self.client.patch(url, {'instructions': 'Tampered instructions'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.rx_doc2_pat2.refresh_from_db()
        self.assertEqual(self.rx_doc2_pat2.instructions, 'Original Rx instructions Doc2 Pat2')
        self.assertEqual(self.rx_doc2_pat2.items.count(), 1)
        self.assertEqual(self.rx_doc2_pat2.items.first().medication_name, 'Metformin')

    def test_doctor_delete_other_doctor_prescription_denied(self):
        """Doctor 1 cannot delete Doctor 2's prescription; row and items still exist."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.prescription_detail_url(self.rx_doc2_pat2.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.assertTrue(Prescription.objects.filter(id=self.rx_doc2_pat2.id).exists())
        self.assertEqual(PrescriptionItem.objects.filter(prescription=self.rx_doc2_pat2).count(), 1)

    def test_doctor_cancel_other_doctor_prescription_denied(self):
        """Doctor 1 cannot cancel Doctor 2's prescription; status remains active."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.prescription_cancel_url(self.rx_doc2_pat2.id)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.rx_doc2_pat2.refresh_from_db()
        self.assertEqual(self.rx_doc2_pat2.status, 'active')


class SuccessfulDoctorAndAdminOperationsTests(BaseClinicalAccessTestCase):
    """
    Verify successful doctor and admin read and write operations.
    """

    def test_doctor_create_medical_record_assigned_to_self(self):
        """Doctor 1 creates a medical record; it is automatically assigned to Doctor 1."""
        self.client.force_authenticate(user=self.doctor_1)
        payload = {
            'patient': str(self.patient_1.id),
            'record_type': 'consultation',
            'title': 'New Consult Record Doc1',
            'description': 'Clinical notes by doc 1',
        }
        response = self.client.post(self.record_list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        created_record = MedicalRecord.objects.get(id=response.data['id'])
        self.assertEqual(created_record.doctor, self.doctor_1)
        self.assertEqual(created_record.patient, self.patient_1)
        self.assertEqual(created_record.title, 'New Consult Record Doc1')

    def test_doctor_modify_and_delete_own_medical_record(self):
        """Doctor 1 can PATCH and DELETE their own medical record."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.record_detail_url(self.record_doc1_pat1.id)

        # PATCH
        patch_response = self.client.patch(url, {'title': 'Updated Doc1 Title'}, format='json')
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.record_doc1_pat1.refresh_from_db()
        self.assertEqual(self.record_doc1_pat1.title, 'Updated Doc1 Title')

        # DELETE
        del_response = self.client.delete(url)
        self.assertEqual(del_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(MedicalRecord.objects.filter(id=self.record_doc1_pat1.id).exists())

    def test_doctor_create_and_cancel_prescription(self):
        """Doctor 1 creates a prescription with items, then cancels it."""
        self.client.force_authenticate(user=self.doctor_1)
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_1.id),
            'instructions': 'Take after dinner',
            'items': [
                {
                    'medication_name': 'Atorvastatin',
                    'dosage': '20mg',
                    'frequency': 'once daily',
                    'duration': '60 days',
                    'instructions': 'Bedtime',
                }
            ],
        }
        create_res = self.client.post(self.prescription_list_url, payload, format='json')
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)

        new_rx_id = create_res.data['id']
        new_rx = Prescription.objects.get(id=new_rx_id)
        self.assertEqual(new_rx.doctor, self.doctor_1)
        self.assertEqual(new_rx.status, 'active')
        self.assertEqual(new_rx.items.count(), 1)
        self.assertEqual(new_rx.items.first().medication_name, 'Atorvastatin')

        # Doctor 1 cancels this prescription
        cancel_url = self.prescription_cancel_url(new_rx_id)
        cancel_res = self.client.post(cancel_url)
        self.assertEqual(cancel_res.status_code, status.HTTP_200_OK)

        new_rx.refresh_from_db()
        self.assertEqual(new_rx.status, 'cancelled')

    def test_doctor_modify_and_delete_own_prescription(self):
        """Doctor 1 can PATCH and DELETE their own prescription."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.prescription_detail_url(self.rx_doc1_pat1.id)

        # PATCH instructions
        patch_res = self.client.patch(url, {'instructions': 'Updated instructions by Doc1'}, format='json')
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.rx_doc1_pat1.refresh_from_db()
        self.assertEqual(self.rx_doc1_pat1.instructions, 'Updated instructions by Doc1')

        # DELETE
        del_res = self.client.delete(url)
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Prescription.objects.filter(id=self.rx_doc1_pat1.id).exists())
        self.assertFalse(PrescriptionItem.objects.filter(prescription_id=self.rx_doc1_pat1.id).exists())

    def test_admin_full_access_to_all_records_and_prescriptions(self):
        """Admin can list, retrieve, modify, delete, and cancel any clinical record or prescription."""
        self.client.force_authenticate(user=self.admin)

        # Admin lists all records
        rec_list_res = self.client.get(self.record_list_url)
        self.assertEqual(rec_list_res.status_code, status.HTTP_200_OK)
        rec_results = rec_list_res.data.get('results', rec_list_res.data)
        rec_ids = [str(r['id']) for r in rec_results]
        self.assertIn(str(self.record_doc1_pat1.id), rec_ids)
        self.assertIn(str(self.record_doc2_pat2.id), rec_ids)

        # Admin lists all prescriptions
        rx_list_res = self.client.get(self.prescription_list_url)
        self.assertEqual(rx_list_res.status_code, status.HTTP_200_OK)
        rx_results = rx_list_res.data.get('results', rx_list_res.data)
        rx_ids = [str(r['id']) for r in rx_results]
        self.assertIn(str(self.rx_doc1_pat1.id), rx_ids)
        self.assertIn(str(self.rx_doc2_pat2.id), rx_ids)

        # Admin can retrieve Doctor 2's record
        rec_url = self.record_detail_url(self.record_doc2_pat2.id)
        get_res = self.client.get(rec_url)
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)

        # Admin can update Doctor 2's record
        patch_res = self.client.patch(rec_url, {'title': 'Admin Edited Title'}, format='json')
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.record_doc2_pat2.refresh_from_db()
        self.assertEqual(self.record_doc2_pat2.title, 'Admin Edited Title')

        # Admin can cancel Doctor 2's prescription
        cancel_url = self.prescription_cancel_url(self.rx_doc2_pat2.id)
        cancel_res = self.client.post(cancel_url)
        self.assertEqual(cancel_res.status_code, status.HTTP_200_OK)
        self.rx_doc2_pat2.refresh_from_db()
        self.assertEqual(self.rx_doc2_pat2.status, 'cancelled')

        # Admin can delete Doctor 1's record
        del_rec_url = self.record_detail_url(self.record_doc1_pat1.id)
        del_res = self.client.delete(del_rec_url)
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(MedicalRecord.objects.filter(id=self.record_doc1_pat1.id).exists())

        # Admin can delete Doctor 1's prescription
        del_rx_url = self.prescription_detail_url(self.rx_doc1_pat1.id)
        del_rx_res = self.client.delete(del_rx_url)
        self.assertEqual(del_rx_res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Prescription.objects.filter(id=self.rx_doc1_pat1.id).exists())


class UnauthenticatedAndUnsupportedRoleAccessTests(BaseClinicalAccessTestCase):
    """
    Verify unauthenticated users and unsupported roles are completely denied.
    Verify database rows and prescription items remain unchanged.
    """

    def test_unauthenticated_requests_denied(self):
        """Unauthenticated requests return 401 Unauthorized; DB remains unchanged."""
        self.client.logout()

        # List records and prescriptions
        self.assertEqual(self.client.get(self.record_list_url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get(self.prescription_list_url).status_code, status.HTTP_401_UNAUTHORIZED)

        # Retrieve
        rec_url = self.record_detail_url(self.record_doc1_pat1.id)
        rx_url = self.prescription_detail_url(self.rx_doc1_pat1.id)
        cancel_url = self.prescription_cancel_url(self.rx_doc1_pat1.id)

        self.assertEqual(self.client.get(rec_url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get(rx_url).status_code, status.HTTP_401_UNAUTHORIZED)

        # Write attempts
        self.assertEqual(self.client.post(self.record_list_url, {}).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.put(rec_url, {}).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.patch(rec_url, {'title': 'Hacked'}).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.delete(rec_url).status_code, status.HTTP_401_UNAUTHORIZED)

        self.assertEqual(self.client.post(self.prescription_list_url, {}).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.put(rx_url, {}).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.patch(rx_url, {'instructions': 'Hacked'}).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.delete(rx_url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(cancel_url).status_code, status.HTTP_401_UNAUTHORIZED)

        # Verify database rows and items unchanged
        self.record_doc1_pat1.refresh_from_db()
        self.assertEqual(self.record_doc1_pat1.title, 'Record Doc1 Pat1 Initial')
        self.rx_doc1_pat1.refresh_from_db()
        self.assertEqual(self.rx_doc1_pat1.status, 'active')
        self.assertEqual(self.rx_doc1_pat1.instructions, 'Original Rx instructions Doc1 Pat1')
        self.assertEqual(self.rx_doc1_pat1.items.count(), 2)

    def test_unsupported_role_requests_denied(self):
        """Unsupported role (e.g. nurse) is denied with 403 Forbidden; DB remains unchanged."""
        self.client.force_authenticate(user=self.unsupported_user)

        # List
        self.assertEqual(self.client.get(self.record_list_url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(self.prescription_list_url).status_code, status.HTTP_403_FORBIDDEN)

        # Retrieve
        rec_url = self.record_detail_url(self.record_doc1_pat1.id)
        rx_url = self.prescription_detail_url(self.rx_doc1_pat1.id)
        cancel_url = self.prescription_cancel_url(self.rx_doc1_pat1.id)

        self.assertEqual(self.client.get(rec_url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(rx_url).status_code, status.HTTP_403_FORBIDDEN)

        # Writes
        self.assertEqual(self.client.post(self.record_list_url, {}).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.put(rec_url, {}).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.patch(rec_url, {'title': 'Hacked by Nurse'}).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(rec_url).status_code, status.HTTP_403_FORBIDDEN)

        self.assertEqual(self.client.post(self.prescription_list_url, {}).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.put(rx_url, {}).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.patch(rx_url, {'instructions': 'Hacked by Nurse'}).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(rx_url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(cancel_url).status_code, status.HTTP_403_FORBIDDEN)

        # Verify database rows and items unchanged
        self.record_doc1_pat1.refresh_from_db()
        self.assertEqual(self.record_doc1_pat1.title, 'Record Doc1 Pat1 Initial')
        self.rx_doc1_pat1.refresh_from_db()
        self.assertEqual(self.rx_doc1_pat1.status, 'active')
        self.assertEqual(self.rx_doc1_pat1.instructions, 'Original Rx instructions Doc1 Pat1')
        self.assertEqual(self.rx_doc1_pat1.items.count(), 2)


class ClinicalRecordPermissionUnitTests(BaseClinicalAccessTestCase):
    """
    Direct unit tests for the reusable ClinicalRecordPermission class.
    """

    def setUp(self):
        super().setUp()
        self.permission = ClinicalRecordPermission()
        self.factory = APIRequestFactory()

    def test_has_permission_roles_and_methods(self):
        """Check has_permission logic across roles and HTTP methods."""
        # Unauthenticated
        req = self.factory.get('/')
        req.user = None
        self.assertFalse(self.permission.has_permission(req, None))

        # Unsupported role
        req = self.factory.get('/')
        req.user = self.unsupported_user
        self.assertFalse(self.permission.has_permission(req, None))

        # Admin: SAFE and write methods allowed
        req = self.factory.get('/')
        req.user = self.admin
        self.assertTrue(self.permission.has_permission(req, None))
        req = self.factory.post('/')
        req.user = self.admin
        self.assertTrue(self.permission.has_permission(req, None))
        req = self.factory.delete('/')
        req.user = self.admin
        self.assertTrue(self.permission.has_permission(req, None))

        # Doctor: SAFE and write methods allowed at view level
        req = self.factory.get('/')
        req.user = self.doctor_1
        self.assertTrue(self.permission.has_permission(req, None))
        req = self.factory.post('/')
        req.user = self.doctor_1
        self.assertTrue(self.permission.has_permission(req, None))
        req = self.factory.put('/')
        req.user = self.doctor_1
        self.assertTrue(self.permission.has_permission(req, None))

        # Patient: SAFE methods allowed, write methods denied
        req = self.factory.get('/')
        req.user = self.patient_1
        self.assertTrue(self.permission.has_permission(req, None))
        req = self.factory.head('/')
        req.user = self.patient_1
        self.assertTrue(self.permission.has_permission(req, None))
        req = self.factory.options('/')
        req.user = self.patient_1
        self.assertTrue(self.permission.has_permission(req, None))

        req = self.factory.post('/')
        req.user = self.patient_1
        self.assertFalse(self.permission.has_permission(req, None))
        req = self.factory.put('/')
        req.user = self.patient_1
        self.assertFalse(self.permission.has_permission(req, None))
        req = self.factory.patch('/')
        req.user = self.patient_1
        self.assertFalse(self.permission.has_permission(req, None))
        req = self.factory.delete('/')
        req.user = self.patient_1
        self.assertFalse(self.permission.has_permission(req, None))

    def test_has_object_permission_matrix(self):
        """Check has_object_permission logic across roles and object assignments."""
        # Admin can access and modify any object
        req = self.factory.put('/')
        req.user = self.admin
        self.assertTrue(self.permission.has_object_permission(req, None, self.record_doc1_pat1))
        self.assertTrue(self.permission.has_object_permission(req, None, self.record_doc2_pat2))

        # Doctor can access and modify only assigned objects
        req_get = self.factory.get('/')
        req_get.user = self.doctor_1
        req_put = self.factory.put('/')
        req_put.user = self.doctor_1

        self.assertTrue(self.permission.has_object_permission(req_get, None, self.record_doc1_pat1))
        self.assertTrue(self.permission.has_object_permission(req_put, None, self.record_doc1_pat1))
        self.assertFalse(self.permission.has_object_permission(req_get, None, self.record_doc2_pat2))
        self.assertFalse(self.permission.has_object_permission(req_put, None, self.record_doc2_pat2))

        # Patient can read own object, but cannot read others' or write to own
        req_pat_get = self.factory.get('/')
        req_pat_get.user = self.patient_1
        req_pat_put = self.factory.put('/')
        req_pat_put.user = self.patient_1

        # Own object
        self.assertTrue(self.permission.has_object_permission(req_pat_get, None, self.record_doc1_pat1))
        self.assertFalse(self.permission.has_object_permission(req_pat_put, None, self.record_doc1_pat1))

        # Other patient's object
        self.assertFalse(self.permission.has_object_permission(req_pat_get, None, self.record_doc2_pat2))
        self.assertFalse(self.permission.has_object_permission(req_pat_put, None, self.record_doc2_pat2))


class ClinicalOwnershipAndReferenceProtectionTests(BaseClinicalAccessTestCase):
    """
    Feature 3B tests: Protect clinical ownership and related references.
    Covers:
    - On doctor creation, derive doctor from authenticated user before validation.
    - Omitting doctor must work; supplying another doctor must be rejected.
    - Admin creation validates author's doctor role.
    - Patient references must identify users with the patient role.
    - After creation, patient and doctor are immutable through PUT/PATCH (including admin).
    - Consultation must match effective patient and doctor; preserves nullable behavior.
    - Partial updates and unchanged patient/doctor values accepted.
    - Invalid requests leave records and prescription items unchanged.
    """

    def test_doctor_create_medical_record_spoofed_doctor_rejected(self):
        """Doctor 1 attempting to create record with Doctor 2 as author is rejected with 400."""
        self.client.force_authenticate(user=self.doctor_1)
        initial_count = MedicalRecord.objects.count()
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_2.id),
            'record_type': 'consultation',
            'title': 'Spoofed Doctor Record',
            'description': 'Attempting author spoofing',
        }
        response = self.client.post(self.record_list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(response))
        self.assertEqual(MedicalRecord.objects.count(), initial_count)
        self.assertFalse(MedicalRecord.objects.filter(title='Spoofed Doctor Record').exists())

    def test_doctor_create_prescription_spoofed_doctor_rejected(self):
        """Doctor 1 attempting to create prescription with Doctor 2 as author is rejected with 400."""
        self.client.force_authenticate(user=self.doctor_1)
        initial_rx_count = Prescription.objects.count()
        initial_item_count = PrescriptionItem.objects.count()
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_2.id),
            'instructions': 'Spoofed Doctor Prescription',
            'items': [
                {
                    'medication_name': 'SpoofMed',
                    'dosage': '10mg',
                    'frequency': 'once daily',
                    'duration': '5 days',
                }
            ],
        }
        response = self.client.post(self.prescription_list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(response))
        self.assertEqual(Prescription.objects.count(), initial_rx_count)
        self.assertEqual(PrescriptionItem.objects.count(), initial_item_count)
        self.assertFalse(Prescription.objects.filter(instructions='Spoofed Doctor Prescription').exists())

    def test_doctor_create_medical_record_omitting_doctor_succeeds(self):
        """Doctor 1 creates medical record omitting doctor; doctor is derived before validation."""
        self.client.force_authenticate(user=self.doctor_1)
        payload = {
            'patient': str(self.patient_1.id),
            'record_type': 'consultation',
            'title': 'Record Without Explicit Doctor',
            'description': 'Doctor field omitted by client',
        }
        response = self.client.post(self.record_list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_record = MedicalRecord.objects.get(id=response.data['id'])
        self.assertEqual(created_record.doctor, self.doctor_1)
        self.assertEqual(created_record.patient, self.patient_1)

    def test_doctor_create_prescription_omitting_doctor_succeeds(self):
        """Doctor 1 creates prescription omitting doctor; doctor is derived before validation."""
        self.client.force_authenticate(user=self.doctor_1)
        payload = {
            'patient': str(self.patient_1.id),
            'instructions': 'Prescription without explicit doctor',
            'items': [
                {
                    'medication_name': 'DerivedMed',
                    'dosage': '50mg',
                    'frequency': '2x daily',
                    'duration': '14 days',
                }
            ],
        }
        response = self.client.post(self.prescription_list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_rx = Prescription.objects.get(id=response.data['id'])
        self.assertEqual(created_rx.doctor, self.doctor_1)
        self.assertEqual(created_rx.patient, self.patient_1)
        self.assertEqual(created_rx.items.count(), 1)
        self.assertEqual(created_rx.items.first().medication_name, 'DerivedMed')

    def test_admin_create_medical_record_omitting_doctor_preserves_nullable(self):
        """Admin can create a medical record omitting doctor; doctor remains null."""
        self.client.force_authenticate(user=self.admin)
        payload = {
            'patient': str(self.patient_1.id),
            'record_type': 'lab',
            'title': 'Admin Lab Record No Doctor',
            'description': 'Created by admin without doctor',
        }
        response = self.client.post(self.record_list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_record = MedicalRecord.objects.get(id=response.data['id'])
        self.assertIsNone(created_record.doctor)
        self.assertEqual(created_record.patient, self.patient_1)

    def test_admin_create_prescription_omitting_doctor_rejected(self):
        """Admin creating a prescription without doctor is rejected; doctor is required."""
        self.client.force_authenticate(user=self.admin)
        initial_rx_count = Prescription.objects.count()
        payload = {
            'patient': str(self.patient_1.id),
            'instructions': 'Admin prescription missing doctor',
        }
        response = self.client.post(self.prescription_list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(response))
        self.assertEqual(Prescription.objects.count(), initial_rx_count)

    def test_admin_create_medical_record_wrong_doctor_role_rejected(self):
        """Admin selecting a non-doctor user (e.g. patient) as doctor is rejected with 400."""
        self.client.force_authenticate(user=self.admin)
        initial_count = MedicalRecord.objects.count()
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.patient_2.id),  # patient_2 has role='patient'
            'record_type': 'consultation',
            'title': 'Invalid Author Role Record',
            'description': 'Patient assigned as doctor',
        }
        response = self.client.post(self.record_list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(response))
        self.assertEqual(MedicalRecord.objects.count(), initial_count)

    def test_admin_create_prescription_wrong_doctor_role_rejected(self):
        """Admin selecting a non-doctor user as doctor on prescription is rejected with 400."""
        self.client.force_authenticate(user=self.admin)
        initial_rx_count = Prescription.objects.count()
        payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.patient_2.id),  # role='patient'
            'instructions': 'Invalid doctor role prescription',
            'items': [{'medication_name': 'TestMed', 'dosage': '5mg', 'frequency': '1x', 'duration': '1d'}],
        }
        response = self.client.post(self.prescription_list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(response))
        self.assertEqual(Prescription.objects.count(), initial_rx_count)

    def test_patient_reference_wrong_role_rejected_on_record_and_prescription(self):
        """Supplying a non-patient user (e.g. doctor or admin) as patient is rejected with 400."""
        self.client.force_authenticate(user=self.doctor_1)
        initial_rec_count = MedicalRecord.objects.count()
        initial_rx_count = Prescription.objects.count()

        # Doctor as patient on record
        rec_res = self.client.post(self.record_list_url, {
            'patient': str(self.doctor_2.id),  # role='doctor'
            'title': 'Doctor as Patient Record',
            'description': 'Invalid patient reference',
        }, format='json')
        self.assertEqual(rec_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(rec_res))
        self.assertEqual(MedicalRecord.objects.count(), initial_rec_count)

        # Admin as patient on prescription
        rx_res = self.client.post(self.prescription_list_url, {
            'patient': str(self.admin.id),  # role='admin'
            'instructions': 'Admin as Patient Prescription',
        }, format='json')
        self.assertEqual(rx_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(rx_res))
        self.assertEqual(Prescription.objects.count(), initial_rx_count)

    def test_doctor_cannot_reassign_patient_or_doctor_on_record(self):
        """Doctor cannot reassign patient or doctor on PUT/PATCH; row remains unchanged."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.record_detail_url(self.record_doc1_pat1.id)

        # Attempt to change patient
        patch_pat = self.client.patch(url, {'patient': str(self.patient_2.id)}, format='json')
        self.assertEqual(patch_pat.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(patch_pat))
        self.record_doc1_pat1.refresh_from_db()
        self.assertEqual(self.record_doc1_pat1.patient, self.patient_1)

        # Attempt to change doctor
        patch_doc = self.client.patch(url, {'doctor': str(self.doctor_2.id)}, format='json')
        self.assertEqual(patch_doc.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(patch_doc))
        self.record_doc1_pat1.refresh_from_db()
        self.assertEqual(self.record_doc1_pat1.doctor, self.doctor_1)

    def test_doctor_cannot_reassign_patient_or_doctor_on_prescription(self):
        """Doctor cannot reassign patient or doctor on prescription; row and items unchanged."""
        self.client.force_authenticate(user=self.doctor_1)
        url = self.prescription_detail_url(self.rx_doc1_pat1.id)

        # Attempt to change patient with altered items
        patch_pat = self.client.patch(url, {
            'patient': str(self.patient_2.id),
            'items': [{'medication_name': 'TamperedMed', 'dosage': '99mg', 'frequency': '9x', 'duration': '9d'}],
        }, format='json')
        self.assertEqual(patch_pat.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(patch_pat))

        self.rx_doc1_pat1.refresh_from_db()
        self.assertEqual(self.rx_doc1_pat1.patient, self.patient_1)
        self.assertEqual(self.rx_doc1_pat1.items.count(), 2)
        self.assertFalse(PrescriptionItem.objects.filter(medication_name='TamperedMed').exists())

        # Attempt to change doctor
        patch_doc = self.client.patch(url, {'doctor': str(self.doctor_2.id)}, format='json')
        self.assertEqual(patch_doc.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(patch_doc))
        self.rx_doc1_pat1.refresh_from_db()
        self.assertEqual(self.rx_doc1_pat1.doctor, self.doctor_1)
        self.assertEqual(self.rx_doc1_pat1.items.count(), 2)

    def test_admin_cannot_reassign_patient_or_doctor_including_after_creation(self):
        """Admin requests to reassign patient or doctor on PUT/PATCH are rejected with 400."""
        self.client.force_authenticate(user=self.admin)
        rec_url = self.record_detail_url(self.record_doc1_pat1.id)
        rx_url = self.prescription_detail_url(self.rx_doc1_pat1.id)

        # Admin tries to reassign patient on record
        rec_pat_res = self.client.patch(rec_url, {'patient': str(self.patient_2.id)}, format='json')
        self.assertEqual(rec_pat_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(rec_pat_res))
        self.record_doc1_pat1.refresh_from_db()
        self.assertEqual(self.record_doc1_pat1.patient, self.patient_1)

        # Admin tries to reassign doctor on record
        rec_doc_res = self.client.patch(rec_url, {'doctor': str(self.doctor_2.id)}, format='json')
        self.assertEqual(rec_doc_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(rec_doc_res))
        self.record_doc1_pat1.refresh_from_db()
        self.assertEqual(self.record_doc1_pat1.doctor, self.doctor_1)

        # Admin tries to reassign patient on prescription
        rx_pat_res = self.client.patch(rx_url, {'patient': str(self.patient_2.id)}, format='json')
        self.assertEqual(rx_pat_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('patient', self.get_error_details(rx_pat_res))
        self.rx_doc1_pat1.refresh_from_db()
        self.assertEqual(self.rx_doc1_pat1.patient, self.patient_1)
        self.assertEqual(self.rx_doc1_pat1.items.count(), 2)

        # Admin tries to reassign doctor on prescription
        rx_doc_res = self.client.patch(rx_url, {'doctor': str(self.doctor_2.id)}, format='json')
        self.assertEqual(rx_doc_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(rx_doc_res))
        self.rx_doc1_pat1.refresh_from_db()
        self.assertEqual(self.rx_doc1_pat1.doctor, self.doctor_1)
        self.assertEqual(self.rx_doc1_pat1.items.count(), 2)

    def test_admin_cannot_assign_doctor_to_record_created_without_doctor(self):
        """Admin cannot assign a doctor to a medical record that was created without one."""
        self.client.force_authenticate(user=self.admin)
        rec_no_doc = MedicalRecord.objects.create(
            patient=self.patient_1,
            doctor=None,
            record_type='summary',
            title='No Doctor Summary',
            description='Created without a doctor',
        )
        url = self.record_detail_url(rec_no_doc.id)
        response = self.client.patch(url, {'doctor': str(self.doctor_1.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('doctor', self.get_error_details(response))

        rec_no_doc.refresh_from_db()
        self.assertIsNone(rec_no_doc.doctor)

    def test_put_and_patch_accept_unchanged_patient_and_doctor(self):
        """PUT and PATCH requests that supply unchanged patient and doctor values succeed."""
        self.client.force_authenticate(user=self.doctor_1)
        rec_url = self.record_detail_url(self.record_doc1_pat1.id)
        rx_url = self.prescription_detail_url(self.rx_doc1_pat1.id)

        # Full PUT on medical record with unchanged patient and doctor
        put_rec_payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_1.id),
            'record_type': 'consultation',
            'title': 'Full PUT Updated Title',
            'description': 'Updated description via PUT',
        }
        put_rec_res = self.client.put(rec_url, put_rec_payload, format='json')
        self.assertEqual(put_rec_res.status_code, status.HTTP_200_OK)
        self.record_doc1_pat1.refresh_from_db()
        self.assertEqual(self.record_doc1_pat1.title, 'Full PUT Updated Title')
        self.assertEqual(self.record_doc1_pat1.patient, self.patient_1)
        self.assertEqual(self.record_doc1_pat1.doctor, self.doctor_1)

        # Full PUT on prescription with unchanged patient and doctor
        put_rx_payload = {
            'patient': str(self.patient_1.id),
            'doctor': str(self.doctor_1.id),
            'instructions': 'Updated instructions via PUT',
            'items': [
                {
                    'medication_name': 'PutUpdatedMed',
                    'dosage': '100mg',
                    'frequency': 'once daily',
                    'duration': '10 days',
                    'instructions': 'Take in morning',
                }
            ],
        }
        put_rx_res = self.client.put(rx_url, put_rx_payload, format='json')
        self.assertEqual(put_rx_res.status_code, status.HTTP_200_OK)
        self.rx_doc1_pat1.refresh_from_db()
        self.assertEqual(self.rx_doc1_pat1.instructions, 'Updated instructions via PUT')
        self.assertEqual(self.rx_doc1_pat1.items.count(), 1)
        self.assertEqual(self.rx_doc1_pat1.items.first().medication_name, 'PutUpdatedMed')

    def test_partial_updates_without_patient_and_doctor_succeed(self):
        """Partial updates omitting patient and doctor succeed without altering ownership."""
        self.client.force_authenticate(user=self.doctor_1)
        rec_url = self.record_detail_url(self.record_doc1_pat1.id)
        rx_url = self.prescription_detail_url(self.rx_doc1_pat1.id)

        # PATCH record title only
        patch_rec_res = self.client.patch(rec_url, {'title': 'Only Title Changed'}, format='json')
        self.assertEqual(patch_rec_res.status_code, status.HTTP_200_OK)
        self.record_doc1_pat1.refresh_from_db()
        self.assertEqual(self.record_doc1_pat1.title, 'Only Title Changed')
        self.assertEqual(self.record_doc1_pat1.patient, self.patient_1)
        self.assertEqual(self.record_doc1_pat1.doctor, self.doctor_1)

        # PATCH prescription instructions only
        patch_rx_res = self.client.patch(rx_url, {'instructions': 'Only Instructions Changed'}, format='json')
        self.assertEqual(patch_rx_res.status_code, status.HTTP_200_OK)
        self.rx_doc1_pat1.refresh_from_db()
        self.assertEqual(self.rx_doc1_pat1.instructions, 'Only Instructions Changed')
        self.assertEqual(self.rx_doc1_pat1.items.count(), 2)

    def test_consultation_matching_and_nullable_behavior(self):
        """
        Supplied consultation must match effective patient and doctor.
        Mismatched consultations are rejected; null consultations are preserved.
        """
        # Create consultation fixtures
        c_doc1_pat1 = Consultation.objects.create(
            doctor=self.doctor_1,
            patient=self.patient_1,
            status='completed',
        )
        c_doc2_pat2 = Consultation.objects.create(
            doctor=self.doctor_2,
            patient=self.patient_2,
            status='completed',
        )
        c_doc1_pat2 = Consultation.objects.create(
            doctor=self.doctor_1,
            patient=self.patient_2,
            status='completed',
        )

        self.client.force_authenticate(user=self.doctor_1)

        # 1. Matching consultation on record creation succeeds
        rec_res = self.client.post(self.record_list_url, {
            'patient': str(self.patient_1.id),
            'consultation': str(c_doc1_pat1.id),
            'title': 'Consult Matched Record',
            'description': 'Details',
        }, format='json')
        self.assertEqual(rec_res.status_code, status.HTTP_201_CREATED)
        rec_id = rec_res.data['id']
        self.assertEqual(str(rec_res.data['consultation']), str(c_doc1_pat1.id))

        # 2. Matching consultation on prescription creation succeeds
        rx_res = self.client.post(self.prescription_list_url, {
            'patient': str(self.patient_1.id),
            'consultation': str(c_doc1_pat1.id),
            'instructions': 'Consult Matched Prescription',
        }, format='json')
        self.assertEqual(rx_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(rx_res.data['consultation']), str(c_doc1_pat1.id))

        # 3. Mismatched patient (same doctor, different patient) on record creation rejected
        rec_bad_pat = self.client.post(self.record_list_url, {
            'patient': str(self.patient_1.id),
            'consultation': str(c_doc1_pat2.id),  # consultation patient is patient_2
            'title': 'Bad Patient Consult Record',
            'description': 'Details',
        }, format='json')
        self.assertEqual(rec_bad_pat.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('consultation', self.get_error_details(rec_bad_pat))
        self.assertFalse(MedicalRecord.objects.filter(title='Bad Patient Consult Record').exists())

        # 4. Mismatched doctor and patient on prescription creation rejected
        rx_bad = self.client.post(self.prescription_list_url, {
            'patient': str(self.patient_1.id),
            'consultation': str(c_doc2_pat2.id),  # doctor_2 and patient_2
            'instructions': 'Bad Consult Rx',
        }, format='json')
        self.assertEqual(rx_bad.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('consultation', self.get_error_details(rx_bad))
        self.assertFalse(Prescription.objects.filter(instructions='Bad Consult Rx').exists())

        # 5. Admin creating record without doctor supplying consultation is rejected
        self.client.force_authenticate(user=self.admin)
        rec_admin_no_doc = self.client.post(self.record_list_url, {
            'patient': str(self.patient_1.id),
            'consultation': str(c_doc1_pat1.id),
            'title': 'Admin Consult Record No Doctor',
            'description': 'Details',
        }, format='json')
        self.assertEqual(rec_admin_no_doc.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('consultation', self.get_error_details(rec_admin_no_doc))

        # 6. Doctor 1 updates record to clear consultation (consultation: null)
        self.client.force_authenticate(user=self.doctor_1)
        clear_url = self.record_detail_url(rec_id)
        clear_res = self.client.patch(clear_url, {'consultation': None}, format='json')
        self.assertEqual(clear_res.status_code, status.HTTP_200_OK)
        rec_cleared = MedicalRecord.objects.get(id=rec_id)
        self.assertIsNone(rec_cleared.consultation)

        # 7. Doctor 1 updates record to attach mismatched consultation is rejected
        bad_update_res = self.client.patch(clear_url, {'consultation': str(c_doc2_pat2.id)}, format='json')
        self.assertEqual(bad_update_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('consultation', self.get_error_details(bad_update_res))
        rec_cleared.refresh_from_db()
        self.assertIsNone(rec_cleared.consultation)

    def test_malformed_payload_shapes_return_400_and_leave_db_unchanged(self):
        """
        Non-object request payloads (arrays, strings, numbers, booleans) must return 400 Bad Request
        and leave medical records, prescriptions, and prescription items unchanged.
        """
        self.client.force_authenticate(user=self.doctor_1)

        initial_record_count = MedicalRecord.objects.count()
        initial_prescription_count = Prescription.objects.count()
        initial_item_count = PrescriptionItem.objects.count()

        malformed_payloads = [
            [],
            ['unexpected', 'list', 'item'],
            'invalid',
            '',
            42,
            0,
            3.14,
            True,
            False,
        ]

        for payload in malformed_payloads:
            # Test medical record creation
            rec_res = self.client.post(self.record_list_url, payload, format='json')
            self.assertEqual(
                rec_res.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"Expected 400 for medical record with payload {payload!r}, got {rec_res.status_code}",
            )

            # Test prescription creation
            rx_res = self.client.post(self.prescription_list_url, payload, format='json')
            self.assertEqual(
                rx_res.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"Expected 400 for prescription with payload {payload!r}, got {rx_res.status_code}",
            )

        # Assert no changes in database rows or prescription items
        self.assertEqual(MedicalRecord.objects.count(), initial_record_count)
        self.assertEqual(Prescription.objects.count(), initial_prescription_count)
        self.assertEqual(PrescriptionItem.objects.count(), initial_item_count)

    def test_valid_json_object_and_form_data_creation_succeed(self):
        """
        Valid JSON objects and form-data payloads succeed and correctly inject/derive doctor.
        """
        self.client.force_authenticate(user=self.doctor_1)

        # 1. Valid JSON object for record
        rec_json_res = self.client.post(self.record_list_url, {
            'patient': str(self.patient_1.id),
            'title': 'JSON Object Record',
            'description': 'Created via JSON object',
        }, format='json')
        self.assertEqual(rec_json_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(rec_json_res.data['doctor']), str(self.doctor_1.id))

        # 2. Valid form-data payload for record
        rec_form_res = self.client.post(self.record_list_url, {
            'patient': str(self.patient_1.id),
            'title': 'Form Data Record',
            'description': 'Created via form data',
        })
        self.assertEqual(rec_form_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(rec_form_res.data['doctor']), str(self.doctor_1.id))

        # 3. Valid JSON object for prescription with items
        rx_json_res = self.client.post(self.prescription_list_url, {
            'patient': str(self.patient_1.id),
            'instructions': 'Take after food',
            'items': [
                {'medication_name': 'Amoxicillin', 'dosage': '500mg', 'frequency': '3 times daily', 'duration': '7 days'}
            ],
        }, format='json')
        self.assertEqual(rx_json_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(rx_json_res.data['doctor']), str(self.doctor_1.id))
        self.assertEqual(len(rx_json_res.data.get('items', [])), 1)

        # 4. Valid form-data payload for prescription
        rx_form_res = self.client.post(self.prescription_list_url, {
            'patient': str(self.patient_1.id),
            'instructions': 'Drink plenty of fluids',
        })
        self.assertEqual(rx_form_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(rx_form_res.data['doctor']), str(self.doctor_1.id))

