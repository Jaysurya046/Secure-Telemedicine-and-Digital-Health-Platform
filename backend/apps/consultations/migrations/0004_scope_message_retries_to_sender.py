from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('consultations', '0003_add_client_msg_id_and_room_id_index')]

    operations = [
        migrations.RemoveConstraint(
            model_name='consultationmessage', name='unique_consultation_client_msg_id',
        ),
        migrations.AddConstraint(
            model_name='consultationmessage',
            constraint=models.UniqueConstraint(
                fields=('consultation', 'sender', 'client_msg_id'),
                condition=models.Q(client_msg_id__gt=''),
                name='unique_consultation_client_msg_id',
            ),
        ),
        migrations.AlterModelOptions(
            name='consultationmessage', options={'ordering': ['-sent_at', '-id']},
        ),
        # room_id is already unique, so its unique index supports lookups.
        migrations.RemoveIndex(
            model_name='consultation', name='consultatio_room_id_8f87a9_idx',
        ),
    ]
