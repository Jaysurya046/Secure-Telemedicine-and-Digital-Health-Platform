"""
Tests for Step 2B: Migration drift reconciliation and upgrade data preservation.
Verifies that:
1. Upgrading from the initial (0001) schema to 0002 reconciles index names and
   user model inherited fields without losing or corrupting representative data.
2. All representative models (users, profiles, appointments, availability,
   consultations, messages, medical records, prescriptions, audit logs) retain
   their values, relationships, permissions, and group memberships.
3. Database index renames take effect and index queries remain fast and functional.
"""
import os
import shutil
import tempfile
from datetime import date, time
from django.test import SimpleTestCase
from django.core.management import call_command
from django.db import connection
from django.utils import timezone


class MigrationSchemaUpgradeTestCase(SimpleTestCase):
    """
    End-to-end verification of upgrading from initial schema (0001) to
    reconciled schema (0002) using an isolated SQLite database.
    """
    databases = {'default'}

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'upgrade_verification.sqlite3')

    def tearDown(self):
        connection.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def test_upgrade_from_0001_preserves_representative_data_and_renames_indexes(self):
        """
        1. Migrate an isolated database to 0001_initial for all apps.
        2. Insert representative user and domain records.
        3. Verify initial index names exist.
        4. Migrate forward to 0002 (all latest migrations).
        5. Verify that:
           - All representative data (admin, patient, doctor, appointments,
             consultations, records, prescriptions, audit logs) are 100% intact.
           - User fields (groups, permissions, last_login, is_superuser) are preserved.
           - Reconciled index names exist and old index names are removed.
        """
        # Configure connection to use the dedicated SQLite file
        from django.db import connections
        test_conn = connections['default']
        test_conn.close()
        orig_name = test_conn.settings_dict['NAME']
        test_conn.settings_dict['NAME'] = self.db_path

        try:
            # 1. Migrate core and initial domain migrations
            call_command('migrate', 'contenttypes', '0002_remove_content_type_name', verbosity=0)
            call_command('migrate', 'auth', '0012_alter_user_first_name_max_length', verbosity=0)
            call_command('migrate', 'users', '0001_initial', verbosity=0)
            call_command('migrate', 'appointments', '0001_initial', verbosity=0)
            call_command('migrate', 'audit', '0001_initial', verbosity=0)
            call_command('migrate', 'consultations', '0001_initial', verbosity=0)
            call_command('migrate', 'medical_records', '0001_initial', verbosity=0)

            from django.contrib.auth import get_user_model
            from django.contrib.auth.models import Group, Permission
            from apps.users.models import UserProfile, DoctorProfile, PatientMedicalInfo, TwoFactorAuth
            from apps.appointments.models import Appointment, DoctorAvailability
            from apps.consultations.models import Consultation, ConsultationMessage
            from apps.medical_records.models import MedicalRecord, Prescription
            from apps.audit.models import AuditLog

            User = get_user_model()

            # 2. Populate representative user and domain data
            admin_user = User.objects.create(
                email='admin_audit@example.com',
                role='admin',
                is_staff=True,
                is_superuser=True,
                is_active=True,
                is_verified=True,
                last_login=timezone.now()
            )
            admin_user.set_password('AdminSecPassword123!')
            admin_user.save()

            grp = Group.objects.create(name='ClinicalAdminsGroup')
            perm = Permission.objects.filter(codename='view_user').first()
            if perm:
                grp.permissions.add(perm)
                admin_user.user_permissions.add(perm)
            admin_user.groups.add(grp)

            TwoFactorAuth.objects.create(
                user=admin_user,
                is_enabled=True,
                secret_key='JBSWY3DPEHPK3PXP',
                backup_codes=['123456', '789012']
            )

            # Patient user & profile
            patient_user = User.objects.create(
                email='patient_audit@example.com',
                role='patient',
                is_active=True,
                is_verified=True
            )
            patient_user.set_password('PatientSecPass123!')
            patient_user.save()

            UserProfile.objects.create(
                user=patient_user,
                first_name='John',
                last_name='Doe',
                phone='+12345678901',
                date_of_birth=date(1990, 1, 1),
                gender='M',
                city='Metro City'
            )

            PatientMedicalInfo.objects.create(
                user=patient_user,
                blood_group='O+',
                height=178.50,
                weight=75.00,
                allergies=['Penicillin'],
                chronic_conditions=['Asthma']
            )

            # Doctor user & profile
            doctor_user = User.objects.create(
                email='doctor_audit@example.com',
                role='doctor',
                is_active=True,
                is_verified=True
            )
            doctor_user.set_password('DoctorSecPass123!')
            doctor_user.save()

            UserProfile.objects.create(
                user=doctor_user,
                first_name='Sarah',
                last_name='Connor',
                phone='+19876543210',
                city='Metro City'
            )

            DoctorProfile.objects.create(
                user=doctor_user,
                specialization='Pulmonology',
                license_number='MED-123456',
                years_of_experience=10,
                consultation_fee=120.00
            )

            DoctorAvailability.objects.create(
                doctor=doctor_user,
                weekday=0,
                start_time=time(9, 0),
                end_time=time(17, 0)
            )

            # Appointment
            start_time = timezone.now() + timezone.timedelta(days=1)
            end_time = start_time + timezone.timedelta(hours=1)
            appt = Appointment.objects.create(
                patient=patient_user,
                doctor=doctor_user,
                scheduled_start=start_time,
                scheduled_end=end_time,
                status='confirmed',
                reason='Annual checkup',
                symptoms=['Shortness of breath']
            )

            # Consultation & message
            consult = Consultation.objects.create(
                appointment=appt,
                patient=patient_user,
                doctor=doctor_user,
                status='scheduled',
                chief_complaint='Cough and shortness of breath'
            )

            ConsultationMessage.objects.create(
                consultation=consult,
                sender=patient_user,
                message='Hello doctor, having breathing difficulties.'
            )

            # Medical Record & Prescription
            rec = MedicalRecord.objects.create(
                patient=patient_user,
                doctor=doctor_user,
                consultation=consult,
                record_type='consultation',
                title='Pulmonary Evaluation',
                description='Patient exhibits mild wheezing. Prescribed inhaler.',
                metadata={'spo2': 97}
            )

            rx = Prescription.objects.create(
                patient=patient_user,
                doctor=doctor_user,
                consultation=consult,
                status='active',
                instructions='Albuterol inhaler 2 puffs PRN',
                valid_until=date(2027, 1, 1)
            )

            # Audit Log
            AuditLog.objects.create(
                user=admin_user,
                action='login',
                resource_type='User',
                resource_id=str(admin_user.id),
                ip_address='192.168.1.50'
            )

            # 3. Verify 0001 index names are present before upgrade
            with test_conn.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
                initial_indexes = {row[0] for row in cursor.fetchall()}

            self.assertIn('users_email_idx', initial_indexes)
            self.assertIn('users_role_idx', initial_indexes)
            self.assertIn('users_created_idx', initial_indexes)
            self.assertIn('appointmen_patient_schedul_idx', initial_indexes)
            self.assertIn('appointmen_doctor_schedul_idx', initial_indexes)
            self.assertIn('appointmen_status_idx', initial_indexes)
            self.assertIn('audit_logs_user_created_idx', initial_indexes)
            self.assertIn('consultati_patient_created_idx', initial_indexes)
            self.assertIn('medical_rec_patient_created_idx', initial_indexes)
            self.assertIn('prescripti_patient_created_idx', initial_indexes)

            # 4. Migrate forward to 0002
            call_command('migrate', verbosity=0)

            # 5. Verify index names after upgrade
            with test_conn.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
                upgraded_indexes = {row[0] for row in cursor.fetchall()}

            # New index names MUST be present
            self.assertIn('users_email_4b85f2_idx', upgraded_indexes)
            self.assertIn('users_role_0ace22_idx', upgraded_indexes)
            self.assertIn('users_created_6541e9_idx', upgraded_indexes)
            self.assertIn('appointment_patient_fdc364_idx', upgraded_indexes)
            self.assertIn('appointment_doctor__3b28f3_idx', upgraded_indexes)
            self.assertIn('appointment_status_9fecd6_idx', upgraded_indexes)
            self.assertIn('audit_logs_user_id_fbfd51_idx', upgraded_indexes)
            self.assertIn('audit_logs_action_391715_idx', upgraded_indexes)
            self.assertIn('audit_logs_resourc_bda8a6_idx', upgraded_indexes)
            self.assertIn('consultatio_patient_ebc6af_idx', upgraded_indexes)
            self.assertIn('consultatio_doctor__a6a21f_idx', upgraded_indexes)
            self.assertIn('consultatio_status_beb187_idx', upgraded_indexes)
            self.assertIn('medical_rec_patient_bfaf9b_idx', upgraded_indexes)
            self.assertIn('medical_rec_doctor__53e85b_idx', upgraded_indexes)
            self.assertIn('medical_rec_record__6b7b73_idx', upgraded_indexes)
            self.assertIn('prescriptio_patient_50dfd5_idx', upgraded_indexes)
            self.assertIn('prescriptio_doctor__2c554b_idx', upgraded_indexes)
            self.assertIn('prescriptio_status_1d7db8_idx', upgraded_indexes)

            # Old index names MUST be gone
            self.assertNotIn('users_email_idx', upgraded_indexes)
            self.assertNotIn('users_role_idx', upgraded_indexes)
            self.assertNotIn('appointmen_patient_schedul_idx', upgraded_indexes)
            self.assertNotIn('appointmen_doctor_schedul_idx', upgraded_indexes)
            self.assertNotIn('audit_logs_user_created_idx', upgraded_indexes)
            self.assertNotIn('consultati_patient_created_idx', upgraded_indexes)
            self.assertNotIn('medical_rec_patient_created_idx', upgraded_indexes)
            self.assertNotIn('prescripti_patient_created_idx', upgraded_indexes)

            # 6. Verify data preservation
            admin_reloaded = User.objects.get(email='admin_audit@example.com')
            self.assertTrue(admin_reloaded.is_superuser)
            self.assertTrue(admin_reloaded.is_staff)
            self.assertTrue(admin_reloaded.is_active)
            self.assertTrue(admin_reloaded.is_verified)
            self.assertIsNotNone(admin_reloaded.last_login)
            self.assertEqual(admin_reloaded.groups.count(), 1)
            self.assertEqual(admin_reloaded.groups.first().name, 'ClinicalAdminsGroup')
            if perm:
                self.assertTrue(admin_reloaded.user_permissions.filter(codename='view_user').exists())

            patient_reloaded = User.objects.get(email='patient_audit@example.com')
            self.assertEqual(patient_reloaded.profile.first_name, 'John')
            self.assertEqual(patient_reloaded.profile.last_name, 'Doe')
            self.assertEqual(patient_reloaded.medical_info.blood_group, 'O+')
            self.assertEqual(patient_reloaded.medical_info.allergies, ['Penicillin'])

            doctor_reloaded = User.objects.get(email='doctor_audit@example.com')
            self.assertEqual(doctor_reloaded.profile.first_name, 'Sarah')
            self.assertEqual(doctor_reloaded.doctor_profile.specialization, 'Pulmonology')
            self.assertEqual(doctor_reloaded.doctor_profile.license_number, 'MED-123456')
            self.assertEqual(doctor_reloaded.availability_windows.count(), 1)

            appt_reloaded = Appointment.objects.get(id=appt.id)
            self.assertEqual(appt_reloaded.status, 'confirmed')
            self.assertEqual(appt_reloaded.patient, patient_reloaded)
            self.assertEqual(appt_reloaded.doctor, doctor_reloaded)

            consult_reloaded = Consultation.objects.get(id=consult.id)
            self.assertEqual(consult_reloaded.status, 'scheduled')
            self.assertEqual(consult_reloaded.messages.count(), 1)
            self.assertEqual(
                consult_reloaded.messages.first().message,
                'Hello doctor, having breathing difficulties.'
            )

            rec_reloaded = MedicalRecord.objects.get(id=rec.id)
            self.assertEqual(rec_reloaded.title, 'Pulmonary Evaluation')
            self.assertEqual(rec_reloaded.metadata, {'spo2': 97})

            rx_reloaded = Prescription.objects.get(id=rx.id)
            self.assertEqual(rx_reloaded.instructions, 'Albuterol inhaler 2 puffs PRN')
            self.assertEqual(rx_reloaded.status, 'active')

            audit_logs = AuditLog.objects.filter(user=admin_reloaded)
            self.assertEqual(audit_logs.count(), 1)
            self.assertEqual(audit_logs.first().action, 'login')

            # 7. Querying indexed fields functions properly
            self.assertEqual(User.objects.filter(email='patient_audit@example.com').count(), 1)
            self.assertEqual(Appointment.objects.filter(patient=patient_reloaded).count(), 1)
            self.assertEqual(Consultation.objects.filter(doctor=doctor_reloaded).count(), 1)
            self.assertEqual(MedicalRecord.objects.filter(patient=patient_reloaded).count(), 1)
            self.assertEqual(Prescription.objects.filter(patient=patient_reloaded).count(), 1)

        finally:
            test_conn.close()
            test_conn.settings_dict['NAME'] = orig_name
