"""Add denormalized channel_count field to FiberCable and populate from coordinates."""

from django.db import migrations, models


def populate_channel_count(apps, schema_editor):
    FiberCable = apps.get_model("fibers", "FiberCable")
    for cable in FiberCable.objects.all():
        cable.channel_count = len(cable.coordinates) if cable.coordinates else 0
        cable.save(update_fields=["channel_count"])


class Migration(migrations.Migration):
    dependencies = [
        ("fibers", "0003_seed_fiber_cables"),
    ]

    operations = [
        migrations.AddField(
            model_name="fibercable",
            name="channel_count",
            field=models.IntegerField(
                default=0,
                help_text="Number of DAS channels (= len(coordinates)).",
            ),
        ),
        migrations.RunPython(populate_channel_count, migrations.RunPython.noop),
    ]
