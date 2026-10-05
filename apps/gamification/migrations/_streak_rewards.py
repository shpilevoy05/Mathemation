def grant_flame_to_existing_profiles(
    ShopCategory,
    ShopItem,
    InventoryItem,
    GamificationProfile,
) -> int:
    category, _ = ShopCategory.objects.update_or_create(
        title="Рамки", defaults={"order": 1}
    )
    flame, _ = ShopItem.objects.update_or_create(
        slot="frame",
        code="flame",
        defaults={
            "category": category,
            "title": "Рамка «Пламя»",
            "tier": "reward",
            "price_coins": 0,
            "is_active": True,
            "effect": "none",
        },
    )
    student_ids = (
        GamificationProfile.objects.filter(streak_best__gte=7)
        .values_list("student_id", flat=True)
        .distinct()
    )
    granted = 0
    for student_id in student_ids:
        _, created = InventoryItem.objects.get_or_create(
            student_id=student_id,
            item=flame,
        )
        granted += int(created)
    return granted
