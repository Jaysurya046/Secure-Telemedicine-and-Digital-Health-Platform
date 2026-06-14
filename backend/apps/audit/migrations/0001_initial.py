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
            name='AuditLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('action', models.CharField(choices=[('login', 'Login'), ('logout', 'Logout'), ('create', 'Create'), ('read', 'Read'), ('update', 'Update'), ('delete', 'Delete'), ('export', 'Export'), ('system', 'System')], max_length=20)),
                ('resource_type', models.CharField(blank=True, max_length=100)),
                ('resource_id', models.CharField(blank=True, max_length=100)),
                ('path', models.CharField(blank=True, max_length=255)),
                ('method', models.CharField(blank=True, max_length=10)),
                ('status_code', models.PositiveIntegerField(blank=True, null=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'audit_logs', 'ordering': ['-created_at']},
        ),
        migrations.AddIndex(model_name='auditlog', index=models.Index(fields=['user', 'created_at'], name='audit_logs_user_created_idx')),
        migrations.AddIndex(model_name='auditlog', index=models.Index(fields=['action', 'created_at'], name='audit_logs_action_created_idx')),
        migrations.AddIndex(model_name='auditlog', index=models.Index(fields=['resource_type', 'resource_id'], name='audit_logs_resource_idx')),
    ]
