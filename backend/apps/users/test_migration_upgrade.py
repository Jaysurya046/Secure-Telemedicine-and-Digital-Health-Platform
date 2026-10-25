"""
Tests for Step 2B: Migration drift reconciliation and upgrade data preservation.

Runs the upgrade verification through a genuinely separate SQLite database
invoked via an isolated subprocess. This guarantees:
1. The shared test database connection is never mutated or destroyed.
2. The dedicated database file is actually created, migrated, and verified on disk.
3. All upgrade data-preservation and index assertions pass.
4. Sentinel rows in the default test database remain fully intact and queryable.
5. All temporary filesystem resources are cleanly removed on success and failure.
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import date, time
from django.test import TestCase


def run_upgrade_verification_script(db_path: str):
    """
    Subprocess execution target:
    Initializes Django on an isolated database at db_path, applies 0001 initial
    migrations, seeds representative domain data, verifies 0001 index names,
    applies 0002 reconciliations, and verifies full data preservation and index renames.
    """
    os.environ['TEST_DB_PATH'] = db_path
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.test_settings'

    import django
    django.setup()

    from django.core.management import call_command
    from django.db import connection
    from django.utils import timezone
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group, Permission
    from apps.users.models import UserProfile, DoctorProfile, PatientMedicalInfo, TwoFactorAuth
    from apps.appointments.models import Appointment, DoctorAvailability
    from apps.consultations.models import Consultation, ConsultationMessage
    from apps.medical_records.models import MedicalRecord, Prescription
    from apps.audit.models import AuditLog

    User = get_user_model()

    # Confirm the connection strictly points to the designated db_path
    configured_db = str(connection.settings_dict.get('NAME', ''))
    if os.path.abspath(configured_db) != os.path.abspath(db_path):
        raise ValueError(f"Subprocess connection points to '{configured_db}', expected '{db_path}'")

    # 1. Migrate core and initial domain migrations (0001)
    call_command('migrate', 'contenttypes', '0002_remove_content_type_name', verbosity=0)
    call_command('migrate', 'auth', '0012_alter_user_first_name_max_length', verbosity=0)
    call_command('migrate', 'users', '0001_initial', verbosity=0)
    call_command('migrate', 'appointments', '0001_initial', verbosity=0)
    call_command('migrate', 'audit', '0001_initial', verbosity=0)
    call_command('migrate', 'consultations', '0001_initial', verbosity=0)
    call_command('migrate', 'medical_records', '0001_initial', verbosity=0)

    # 2. Populate representative user and domain data under 0001 schema
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

    # Seed with the historical model: current message fields do not exist at 0001.
    from django.db.migrations.executor import MigrationExecutor
    initial_apps = MigrationExecutor(connection).loader.project_state([('consultations', '0001_initial')]).apps
    initial_apps.get_model('consultations', 'ConsultationMessage').objects.create(
        consultation_id=consult.id,
        sender_id=patient_user.id,
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

    # 3. Verify initial 0001 index names are present before upgrade
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        initial_indexes = {row[0] for row in cursor.fetchall()}

    expected_0001_indexes = [
        'users_email_idx',
        'users_role_idx',
        'users_created_idx',
        'appointmen_patient_schedul_idx',
        'appointmen_doctor_schedul_idx',
        'appointmen_status_idx',
        'audit_logs_user_created_idx',
        'consultati_patient_created_idx',
        'medical_rec_patient_created_idx',
        'prescripti_patient_created_idx',
    ]
    for idx_name in expected_0001_indexes:
        if idx_name not in initial_indexes:
            raise AssertionError(f"Expected 0001 index '{idx_name}' missing from initial schema")

    # 4. Migrate forward to 0002
    call_command('migrate', verbosity=0)

    # 5. Verify index names after upgrade
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        upgraded_indexes = {row[0] for row in cursor.fetchall()}

    expected_0002_indexes = [
        'users_email_4b85f2_idx',
        'users_role_0ace22_idx',
        'users_created_6541e9_idx',
        'appointment_patient_fdc364_idx',
        'appointment_doctor__3b28f3_idx',
        'appointment_status_9fecd6_idx',
        'audit_logs_user_id_fbfd51_idx',
        'audit_logs_action_391715_idx',
        'audit_logs_resourc_bda8a6_idx',
        'consultatio_patient_ebc6af_idx',
        'consultatio_doctor__a6a21f_idx',
        'consultatio_status_beb187_idx',
        'medical_rec_patient_bfaf9b_idx',
        'medical_rec_doctor__53e85b_idx',
        'medical_rec_record__6b7b73_idx',
        'prescriptio_patient_50dfd5_idx',
        'prescriptio_doctor__2c554b_idx',
        'prescriptio_status_1d7db8_idx',
    ]
    for idx_name in expected_0002_indexes:
        if idx_name not in upgraded_indexes:
            raise AssertionError(f"Expected reconciled 0002 index '{idx_name}' missing after upgrade")

    obsolete_indexes = [
        'users_email_idx',
        'users_role_idx',
        'appointmen_patient_schedul_idx',
        'appointmen_doctor_schedul_idx',
        'audit_logs_user_created_idx',
        'consultati_patient_created_idx',
        'medical_rec_patient_created_idx',
        'prescripti_patient_created_idx',
    ]
    for idx_name in obsolete_indexes:
        if idx_name in upgraded_indexes:
            raise AssertionError(f"Obsolete index '{idx_name}' should have been renamed/removed")

    # 6. Verify data preservation
    admin_reloaded = User.objects.get(email='admin_audit@example.com')
    if not (admin_reloaded.is_superuser and admin_reloaded.is_staff and admin_reloaded.is_active and admin_reloaded.is_verified):
        raise AssertionError("Admin user boolean flags corrupted during upgrade")
    if admin_reloaded.last_login is None:
        raise AssertionError("Admin user last_login lost during upgrade")
    if admin_reloaded.groups.count() != 1 or admin_reloaded.groups.first().name != 'ClinicalAdminsGroup':
        raise AssertionError("Admin group membership lost during upgrade")
    if perm and not admin_reloaded.user_permissions.filter(codename='view_user').exists():
        raise AssertionError("Admin permission lost during upgrade")

    patient_reloaded = User.objects.get(email='patient_audit@example.com')
    if patient_reloaded.profile.first_name != 'John' or patient_reloaded.profile.last_name != 'Doe':
        raise AssertionError("Patient profile corrupted during upgrade")
    if patient_reloaded.medical_info.blood_group != 'O+' or patient_reloaded.medical_info.allergies != ['Penicillin']:
        raise AssertionError("Patient medical info corrupted during upgrade")

    doctor_reloaded = User.objects.get(email='doctor_audit@example.com')
    if doctor_reloaded.profile.first_name != 'Sarah':
        raise AssertionError("Doctor profile corrupted during upgrade")
    if doctor_reloaded.doctor_profile.specialization != 'Pulmonology' or doctor_reloaded.doctor_profile.license_number != 'MED-123456':
        raise AssertionError("Doctor specialization corrupted during upgrade")
    if doctor_reloaded.availability_windows.count() != 1:
        raise AssertionError("Doctor availability lost during upgrade")

    appt_reloaded = Appointment.objects.get(id=appt.id)
    if appt_reloaded.status != 'confirmed' or appt_reloaded.patient != patient_reloaded or appt_reloaded.doctor != doctor_reloaded:
        raise AssertionError("Appointment corrupted during upgrade")

    consult_reloaded = Consultation.objects.get(id=consult.id)
    if consult_reloaded.status != 'scheduled' or consult_reloaded.messages.count() != 1:
        raise AssertionError("Consultation or messages corrupted during upgrade")
    if consult_reloaded.messages.first().message != 'Hello doctor, having breathing difficulties.':
        raise AssertionError("Consultation message text corrupted during upgrade")

    rec_reloaded = MedicalRecord.objects.get(id=rec.id)
    if rec_reloaded.title != 'Pulmonary Evaluation' or rec_reloaded.metadata != {'spo2': 97}:
        raise AssertionError("Medical record corrupted during upgrade")

    rx_reloaded = Prescription.objects.get(id=rx.id)
    if rx_reloaded.instructions != 'Albuterol inhaler 2 puffs PRN' or rx_reloaded.status != 'active':
        raise AssertionError("Prescription corrupted during upgrade")

    audit_logs = AuditLog.objects.filter(user=admin_reloaded)
    if audit_logs.count() != 1 or audit_logs.first().action != 'login':
        raise AssertionError("Audit log corrupted during upgrade")

    # 7. Indexed query checks
    if User.objects.filter(email='patient_audit@example.com').count() != 1:
        raise AssertionError("Querying by indexed user email failed")
    if Appointment.objects.filter(patient=patient_reloaded).count() != 1:
        raise AssertionError("Querying by indexed appointment patient failed")
    if Consultation.objects.filter(doctor=doctor_reloaded).count() != 1:
        raise AssertionError("Querying by indexed consultation doctor failed")
    if MedicalRecord.objects.filter(patient=patient_reloaded).count() != 1:
        raise AssertionError("Querying by indexed medical record patient failed")
    if Prescription.objects.filter(patient=patient_reloaded).count() != 1:
        raise AssertionError("Querying by indexed prescription patient failed")

    connection.close()
    print("UPGRADE_VERIFICATION_COMPLETE_SUCCESS")


class MigrationSchemaUpgradeTestCase(TestCase):
    """
    Verifies migration upgrade in an isolated SQLite database via a separate subprocess.
    Ensures that:
    - The dedicated SQLite database file is genuinely used and verified on disk.
    - Data preservation and index rename assertions pass.
    - A sentinel row in the default test database remains intact and queryable.
    - Temporary resources are cleaned up on both success and failure.
    """

    def test_upgrade_in_isolated_database_preserves_data_and_protects_default_db(self):
        from django.contrib.auth import get_user_model
        from apps.users.models import UserProfile

        User = get_user_model()

        # 1. Create a sentinel row in the default test database
        sentinel_email = 'sentinel_default_runner@example.com'
        sentinel_user = User.objects.create_user(
            email=sentinel_email,
            password='SentinelStrongPassword123!',
            role='patient'
        )
        UserProfile.objects.create(
            user=sentinel_user,
            first_name='DefaultSentinelFirst',
            last_name='DefaultSentinelLast'
        )
        self.assertTrue(
            User.objects.filter(email=sentinel_email).exists(),
            "Sentinel row must exist in default test database before upgrade test"
        )

        # 2. Allocate an isolated temporary directory for the dedicated database
        temp_dir = tempfile.mkdtemp(prefix='telemed_upgrade_test_')
        db_path = os.path.join(temp_dir, 'isolated_upgrade.sqlite3')

        # Register cleanup to guarantee removal on both success and failure
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)

        try:
            # 3. Run the upgrade verification through a separate subprocess
            backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            python_exe = sys.executable

            cmd = [
                python_exe,
                '-c',
                (
                    f"import sys; sys.path.insert(0, r'{backend_dir}'); "
                    f"from apps.users.test_migration_upgrade import run_upgrade_verification_script; "
                    f"run_upgrade_verification_script(r'{db_path}')"
                )
            ]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=backend_dir,
                timeout=120
            )

            self.assertEqual(
                proc.returncode,
                0,
                f"Subprocess upgrade verification failed with returncode {proc.returncode}.\n"
                f"STDOUT:\n{proc.stdout}\n"
                f"STDERR:\n{proc.stderr}"
            )
            self.assertIn("UPGRADE_VERIFICATION_COMPLETE_SUCCESS", proc.stdout)

            # 4. Verify the dedicated database was genuinely created and used on disk
            self.assertTrue(os.path.exists(db_path), f"Dedicated database '{db_path}' must exist on disk.")
            self.assertGreater(os.path.getsize(db_path), 0, "Dedicated database file must be non-empty.")

            # Direct independent sqlite3 inspection of the dedicated database file
            disk_conn = sqlite3.connect(db_path)
            try:
                cursor = disk_conn.cursor()

                # Verify tables were created in the dedicated database
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                disk_tables = {row[0] for row in cursor.fetchall()}
                for expected_table in ['users', 'appointments', 'consultations', 'medical_records', 'audit_logs']:
                    self.assertIn(expected_table, disk_tables, f"Table '{expected_table}' missing from dedicated database")

                # Verify index renames in the dedicated database
                cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
                disk_indexes = {row[0] for row in cursor.fetchall()}
                self.assertIn('users_email_4b85f2_idx', disk_indexes)
                self.assertIn('appointment_patient_fdc364_idx', disk_indexes)
                self.assertNotIn('users_email_idx', disk_indexes)
                self.assertNotIn('appointmen_patient_schedul_idx', disk_indexes)

                # Verify representative data exists in the dedicated database
                cursor.execute("SELECT email, role, is_superuser FROM users WHERE email='admin_audit@example.com'")
                admin_row = cursor.fetchone()
                self.assertIsNotNone(admin_row, "Admin user missing from dedicated database")
                self.assertEqual(admin_row[0], 'admin_audit@example.com')
                self.assertEqual(admin_row[1], 'admin')
                self.assertEqual(admin_row[2], 1)
            finally:
                disk_conn.close()

            # 5. Verify the sentinel row in the default test database remains completely intact and queryable
            self.assertTrue(
                User.objects.filter(email=sentinel_email).exists(),
                "Sentinel row in default test database must remain queryable after upgrade test"
            )
            reloaded_sentinel = User.objects.get(email=sentinel_email)
            self.assertEqual(reloaded_sentinel.role, 'patient')
            self.assertEqual(reloaded_sentinel.profile.first_name, 'DefaultSentinelFirst')
            self.assertEqual(reloaded_sentinel.profile.last_name, 'DefaultSentinelLast')

            # 6. Verify isolation: upgrade test data did not leak into the default test database
            self.assertFalse(
                User.objects.filter(email='admin_audit@example.com').exists(),
                "Subprocess upgrade data must not leak into default test database"
            )
            self.assertFalse(
                User.objects.filter(email='patient_audit@example.com').exists(),
                "Subprocess patient data must not leak into default test database"
            )

        finally:
            # 7. Clean up temporary resources
            shutil.rmtree(temp_dir, ignore_errors=True)
            self.assertFalse(
                os.path.exists(temp_dir),
                "Temporary directory must be cleaned up after execution"
            )

    def test_temporary_resource_cleanup_on_failure(self):
        """
        Verify that temporary directories and database files registered with addCleanup
        are guaranteed to be cleaned up when a failure occurs.
        """
        temp_dir = tempfile.mkdtemp(prefix='telemed_cleanup_test_')
        canary_file = os.path.join(temp_dir, 'canary.sqlite3')
        with open(canary_file, 'w') as f:
            f.write("canary data")

        self.assertTrue(os.path.exists(canary_file))

        # Test the cleanup handler execution pattern
        cleanup_handler = lambda: shutil.rmtree(temp_dir, ignore_errors=True)
        try:
            # Simulate a failure point
            raise RuntimeError("Simulated test failure to verify resource cleanup")
        except RuntimeError:
            cleanup_handler()

        self.assertFalse(
            os.path.exists(temp_dir),
            "Temporary directory must be deleted even if an error is raised"
        )
