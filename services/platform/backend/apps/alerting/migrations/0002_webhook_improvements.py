from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alerting', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='alertrule',
            name='webhook_secret',
            field=models.CharField(blank=True, default='', help_text='HMAC secret for webhook signature verification.', max_length=64),
        ),
        migrations.AddField(
            model_name='alertlog',
            name='delivery_status',
            field=models.CharField(choices=[('pending', 'Pending'), ('success', 'Success'), ('failed', 'Failed')], default='pending', max_length=20),
        ),
        migrations.AddField(
            model_name='alertlog',
            name='error_message',
            field=models.TextField(blank=True, default=''),
        ),
    ]
