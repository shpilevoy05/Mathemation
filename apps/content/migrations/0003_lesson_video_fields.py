from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0002_assignment_reference_solution"),
    ]

    operations = [
        migrations.AddField(
            model_name="lesson",
            name="video_url",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="lesson",
            name="video_duration_minutes",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
