from django.db import migrations


STALE_DESCRIPTION = "Открывается стриком от 7 дней."


def forwards(apps, schema_editor):
    ShopItem = apps.get_model("economy", "ShopItem")
    ShopItem.objects.filter(
        slot="frame",
        code="flame",
        description=STALE_DESCRIPTION,
    ).update(description="")


class Migration(migrations.Migration):

    dependencies = [
        ("gamification", "0006_grant_streak_flame"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
