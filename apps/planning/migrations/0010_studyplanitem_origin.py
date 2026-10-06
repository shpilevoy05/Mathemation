from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0009_trajectorytransition_evidence"),
    ]

    operations = [
        migrations.AddField(
            model_name="studyplanitem",
            name="origin",
            field=models.CharField(
                choices=[
                    ("plan", "Plan"),
                    ("manual", "Manual"),
                    ("urgent", "Urgent"),
                ],
                default="plan",
                max_length=16,
            ),
        ),
    ]
