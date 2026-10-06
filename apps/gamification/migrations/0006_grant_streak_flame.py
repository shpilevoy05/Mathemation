from django.db import migrations

from ._streak_rewards import grant_flame_to_existing_profiles


def forwards(apps, schema_editor):
    ShopCategory = apps.get_model("economy", "ShopCategory")
    ShopItem = apps.get_model("economy", "ShopItem")
    InventoryItem = apps.get_model("economy", "InventoryItem")
    GamificationProfile = apps.get_model("gamification", "GamificationProfile")
    grant_flame_to_existing_profiles(
        ShopCategory,
        ShopItem,
        InventoryItem,
        GamificationProfile,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("economy", "0007_alter_shopitem_tier"),
        ("gamification", "0005_leaguetrophy_trophy"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
