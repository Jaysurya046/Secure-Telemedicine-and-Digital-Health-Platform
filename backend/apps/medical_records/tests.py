"""
Regression and security tests for medical record and prescription write permissions and scoped access.
"""
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIRequestFactory

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
