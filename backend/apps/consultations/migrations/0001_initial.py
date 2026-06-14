import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('appointments', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Consultation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('scheduled', 'Scheduled'), ('in_progress', 'In Progress'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='scheduled', max_length=20)),
                ('room_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
                ('chief_complaint', models.CharField(blank=True, max_length=255)),
                ('diagnosis', models.TextField(blank=True)),
                ('clinical_notes', models.TextField(blank=True)),
                ('follow_up_required', models.BooleanField(default=False)),
                ('follow_up_notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('appointment', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='consultation', to='appointments.appointment')),
                ('doctor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='doctor_consultations', to=settings.AUTH_USER_MODEL)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='patient_consultations', to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'consultations', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='ConsultationMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('message', models.TextField()),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('consultation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='consultations.consultation')),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'consultation_messages', 'ordering': ['sent_at']},
        ),
        migrations.AddIndex(model_name='consultation', index=models.Index(fields=['patient', 'created_at'], name='consultati_patient_created_idx')),
        migrations.AddIndex(model_name='consultation', index=models.Index(fields=['doctor', 'created_at'], name='consultati_doctor_created_idx')),
        migrations.AddIndex(model_name='consultation', index=models.Index(fields=['status'], name='consultati_status_idx')),
    ]
