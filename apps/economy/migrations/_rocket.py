"""Удаление аватара «Ракета» — логика отдельно от миграции.

Миграция запускается один раз и проверить её потом нечем. Логика вынесена сюда,
чтобы у неё были тесты: она трогает инвентарь учеников, а это не тот случай,
когда «сработало на моей базе» считается доказательством.
"""

from __future__ import annotations

LEGACY_CODE = "rocket"
FALLBACK_CODE = "sigma"


def remove(shop_item_model, inventory_model) -> int:
    """Убрать «Ракету» и вернуть тем, у кого она была надета, базовый аватар.

    Возвращает число владельцев, которым понадобилась замена.
    """
    legacy = shop_item_model.objects.filter(slot="avatar", code=LEGACY_CODE).first()
    if legacy is None:
        return 0

    fallback = shop_item_model.objects.filter(slot="avatar", code=FALLBACK_CODE).first()
    owners = list(
        inventory_model.objects.filter(item=legacy).values_list(
            "student_id", "is_equipped"
        )
    )
    inventory_model.objects.filter(item=legacy).delete()
    replaced = 0
    if fallback is not None:
        for student_id, was_equipped in owners:
            inventory, _ = inventory_model.objects.get_or_create(
                student_id=student_id, item=fallback
            )
            if not was_equipped:
                continue
            # Надеваем замену, только если ученик остался вовсе без аватара:
            # другой надетый аватар трогать нельзя.
            if inventory_model.objects.filter(
                student_id=student_id, is_equipped=True, item__slot="avatar"
            ).exists():
                continue
            inventory.is_equipped = True
            inventory.save(update_fields=["is_equipped"])
            replaced += 1
    legacy.delete()
    return replaced
