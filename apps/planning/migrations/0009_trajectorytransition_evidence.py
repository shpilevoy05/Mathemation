from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("planning", "0008_studyplan_unplanned_nodes"),
    ]

    operations = [
        migrations.AddField(
            model_name="trajectorytransition",
            name="evidence",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
