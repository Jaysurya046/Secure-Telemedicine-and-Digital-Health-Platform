import django.core.validators
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(db_index=True, max_length=254, unique=True)),
                ('role', models.CharField(choices=[('patient', 'Patient'), ('doctor', 'Doctor'), ('admin', 'Admin')], default='patient', max_length=10)),
                ('is_active', models.BooleanField(default=True)),
                ('is_staff', models.BooleanField(default=False)),
                ('is_verified', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('groups', models.ManyToManyField(blank=True, related_name='user_set', related_query_name='user', to='auth.group')),
                ('user_permissions', models.ManyToManyField(blank=True, related_name='user_set', related_query_name='user', to='auth.permission')),
            ],
            options={
                'db_table': 'users',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('first_name', models.CharField(max_length=50)),
                ('last_name', models.CharField(max_length=50)),
                ('phone', models.CharField(blank=True, max_length=17, validators=[django.core.validators.RegexValidator(message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.", regex='^\\+?1?\\d{9,15}$')])),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('gender', models.CharField(blank=True, choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other'), ('N', 'Prefer not to say')], max_length=1)),
                ('address', models.TextField(blank=True)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('state', models.CharField(blank=True, max_length=100)),
                ('country', models.CharField(blank=True, max_length=100)),
                ('postal_code', models.CharField(blank=True, max_length=20)),
                ('avatar', models.ImageField(blank=True, null=True, upload_to='avatars/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to='users.user')),
            ],
            options={'db_table': 'user_profiles'},
        ),
        migrations.CreateModel(
            name='DoctorProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('specialization', models.CharField(max_length=100)),
                ('license_number', models.CharField(max_length=50, unique=True)),
                ('years_of_experience', models.PositiveIntegerField(default=0)),
                ('consultation_fee', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('bio', models.TextField(blank=True)),
                ('education', models.JSONField(blank=True, default=list)),
                ('certifications', models.JSONField(blank=True, default=list)),
                ('languages', models.JSONField(blank=True, default=list)),
                ('is_available', models.BooleanField(default=True)),
                ('consultation_duration', models.PositiveIntegerField(default=30, help_text='Duration in minutes')),
                ('average_rating', models.DecimalField(decimal_places=2, default=0.0, max_digits=3)),
                ('total_ratings', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='doctor_profile', to='users.user')),
            ],
            options={'db_table': 'doctor_profiles'},
        ),
        migrations.CreateModel(
            name='PatientMedicalInfo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('blood_group', models.CharField(blank=True, choices=[('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'), ('AB+', 'AB+'), ('AB-', 'AB-'), ('O+', 'O+'), ('O-', 'O-')], max_length=3)),
                ('height', models.DecimalField(blank=True, decimal_places=2, help_text='Height in cm', max_digits=5, null=True)),
                ('weight', models.DecimalField(blank=True, decimal_places=2, help_text='Weight in kg', max_digits=5, null=True)),
                ('allergies', models.JSONField(blank=True, default=list)),
                ('chronic_conditions', models.JSONField(blank=True, default=list)),
                ('current_medications', models.JSONField(blank=True, default=list)),
                ('emergency_contact_name', models.CharField(blank=True, max_length=100)),
                ('emergency_contact_phone', models.CharField(blank=True, max_length=17)),
                ('emergency_contact_relation', models.CharField(blank=True, max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='medical_info', to='users.user')),
            ],
            options={'db_table': 'patient_medical_info'},
        ),
        migrations.CreateModel(
            name='TwoFactorAuth',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_enabled', models.BooleanField(default=False)),
                ('secret_key', models.CharField(blank=True, max_length=32)),
                ('backup_codes', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='two_factor', to='users.user')),
            ],
            options={'db_table': 'two_factor_auth'},
        ),
        migrations.AddIndex(model_name='user', index=models.Index(fields=['email'], name='users_email_idx')),
        migrations.AddIndex(model_name='user', index=models.Index(fields=['role'], name='users_role_idx')),
        migrations.AddIndex(model_name='user', index=models.Index(fields=['created_at'], name='users_created_idx')),
    ]
