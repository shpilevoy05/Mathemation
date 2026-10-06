"""Аватар «Ракета» уходит вместе со старым набором картинок.

В новом наборе дизайна такой вещи нет, а держать в инвентаре предмет, которому
нечего нарисовать, — это пустой кружок вместо аватара. Поэтому запись удаляется
целиком, а тем, у кого «Ракета» была надета, возвращается базовый аватар: без
этого ученик остался бы с буквой вместо картинки и без понятной причины.

Сама логика лежит в `_rocket.py` — у неё есть тесты: миграция трогает инвентарь
учеников, и «сработало на моей базе» здесь не доказательство.

Откат невозможен: картинки, к которой этот код относился, больше нет в дизайне.
"""

from django.db import migrations

from . import _rocket


def forward(apps, schema_editor):
    _rocket.remove(
        apps.get_model("economy", "ShopItem"),
        apps.get_model("economy", "InventoryItem"),
    )


def backward(apps, schema_editor):
    """Не восстанавливаем: картинки «Ракеты» больше не существует."""


class Migration(migrations.Migration):

    dependencies = [
        ("economy", "0003_shopitem_tier"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
