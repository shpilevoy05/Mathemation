from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai_mentor", "0002_aihintmessage_failed_claims_aihintmessage_is_blocked_and_more")]

    operations = [
        migrations.AddField(
            model_name="aihintmessage",
            name="prompt_tokens",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="aihintmessage",
            name="completion_tokens",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="aihintmessage",
            name="estimated_cost_rub",
            field=models.DecimalField(decimal_places=6, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="aihintmessage",
            name="counts_toward_daily_limit",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
