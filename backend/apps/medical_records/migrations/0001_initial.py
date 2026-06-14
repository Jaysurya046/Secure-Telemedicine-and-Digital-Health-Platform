import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('consultations', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MedicalRecord',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('record_type', models.CharField(choices=[('consultation', 'Consultation'), ('lab', 'Lab Result'), ('imaging', 'Imaging'), ('summary', 'Summary'), ('other', 'Other')], default='summary', max_length=20)),
                ('title', models.CharField(max_length=150)),
                ('description', models.TextField()),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('is_sensitive', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('consultation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='medical_records', to='consultations.consultation')),
                ('doctor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_medical_records', to=settings.AUTH_USER_MODEL)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='medical_records', to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'medical_records', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='MedicalDocument',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('document_type', models.CharField(choices=[('report', 'Report'), ('lab', 'Lab Result'), ('imaging', 'Imaging'), ('prescription', 'Prescription'), ('insurance', 'Insurance'), ('other', 'Other')], default='other', max_length=20)),
                ('title', models.CharField(max_length=150)),
                ('file', models.FileField(upload_to='medical_documents/')),
                ('file_hash', models.CharField(blank=True, max_length=64)),
                ('is_encrypted', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='medical_documents', to=settings.AUTH_USER_MODEL)),
                ('record', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='documents', to='medical_records.medicalrecord')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uploaded_medical_documents', to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'medical_documents', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='Prescription',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('active', 'Active'), ('cancelled', 'Cancelled'), ('expired', 'Expired')], default='active', max_length=20)),
                ('instructions', models.TextField(blank=True)),
                ('valid_until', models.DateField(blank=True, null=True)),
                ('verification_code', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('consultation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='prescriptions', to='consultations.consultation')),
                ('doctor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='issued_prescriptions', to=settings.AUTH_USER_MODEL)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='prescriptions', to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'prescriptions', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='PrescriptionItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('medication_name', models.CharField(max_length=150)),
                ('dosage', models.CharField(max_length=100)),
                ('frequency', models.CharField(max_length=100)),
                ('duration', models.CharField(max_length=100)),
                ('instructions', models.TextField(blank=True)),
                ('prescription', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='medical_records.prescription')),
            ],
            options={'db_table': 'prescription_items'},
        ),
        migrations.AddIndex(model_name='medicalrecord', index=models.Index(fields=['patient', 'created_at'], name='medical_rec_patient_created_idx')),
        migrations.AddIndex(model_name='medicalrecord', index=models.Index(fields=['doctor', 'created_at'], name='medical_rec_doctor_created_idx')),
        migrations.AddIndex(model_name='medicalrecord', index=models.Index(fields=['record_type'], name='medical_rec_record_idx')),
        migrations.AddIndex(model_name='prescription', index=models.Index(fields=['patient', 'created_at'], name='prescripti_patient_created_idx')),
        migrations.AddIndex(model_name='prescription', index=models.Index(fields=['doctor', 'created_at'], name='prescripti_doctor_created_idx')),
        migrations.AddIndex(model_name='prescription', index=models.Index(fields=['status'], name='prescripti_status_idx')),
    ]
