from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_studentprofile_forecast_calibration"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("student", "Student"),
                    ("parent", "Parent"),
                    ("expert", "Expert"),
                    ("methodist", "Methodist"),
                ],
                default="student",
                max_length=16,
            ),
        ),
    ]
