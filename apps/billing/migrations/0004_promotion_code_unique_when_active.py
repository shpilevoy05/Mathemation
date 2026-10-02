from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("billing", "0003_addon")]

    operations = [
        migrations.RemoveConstraint(
            model_name="promotion",
            name="uniq_promotion_code",
        ),
        migrations.AddConstraint(
            model_name="promotion",
            constraint=models.UniqueConstraint(
                fields=("code",),
                condition=models.Q(is_active=True) & ~models.Q(code=""),
                name="uniq_promotion_code",
            ),
        ),
    ]
