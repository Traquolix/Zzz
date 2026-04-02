from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("alerting", "0002_webhook_improvements"),
    ]

    operations = [
        migrations.RenameField(
            model_name="alertrule",
            old_name="severity_filter",
            new_name="tags_filter",
        ),
    ]
