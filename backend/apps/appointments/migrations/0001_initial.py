import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Appointment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('scheduled_start', models.DateTimeField(db_index=True)),
                ('scheduled_end', models.DateTimeField(db_index=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('confirmed', 'Confirmed'), ('cancelled', 'Cancelled'), ('completed', 'Completed'), ('no_show', 'No Show')], default='pending', max_length=20)),
                ('reason', models.CharField(max_length=255)),
                ('symptoms', models.JSONField(blank=True, default=list)),
                ('notes', models.TextField(blank=True)),
                ('cancellation_reason', models.TextField(blank=True)),
                ('meeting_link', models.URLField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('doctor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='doctor_appointments', to=settings.AUTH_USER_MODEL)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='patient_appointments', to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'appointments', 'ordering': ['scheduled_start']},
        ),
        migrations.CreateModel(
            name='DoctorAvailability',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('weekday', models.PositiveSmallIntegerField(choices=[(0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'), (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday')])),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('doctor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='availability_windows', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'doctor_availability',
                'ordering': ['doctor', 'weekday', 'start_time'],
                'unique_together': {('doctor', 'weekday', 'start_time', 'end_time')},
            },
        ),
        migrations.AddIndex(model_name='appointment', index=models.Index(fields=['patient', 'scheduled_start'], name='appointmen_patient_schedul_idx')),
        migrations.AddIndex(model_name='appointment', index=models.Index(fields=['doctor', 'scheduled_start'], name='appointmen_doctor_schedul_idx')),
        migrations.AddIndex(model_name='appointment', index=models.Index(fields=['status'], name='appointmen_status_idx')),
    ]
