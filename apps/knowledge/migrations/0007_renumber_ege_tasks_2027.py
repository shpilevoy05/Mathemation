"""Перевод номеров заданий ЕГЭ в структуру 2027 года.

Экзамен стал двадцатизадачным: в часть 1 добавлены задания 6 и 13, в часть 2 —
задание 17, остальные сдвинулись. Номера в графе — это ссылки на конкретную
версию экзамена, поэтому переводятся один раз и все сразу.

Обратного хода нет: прежние задания 8 и 12 сведены в новое задание 9, и
разделить их автоматически невозможно. Откат миграции оставляет номера как
есть — это честнее, чем восстанавливать их наугад.
"""

from django.db import migrations


def forward(apps, schema_editor):
    from apps.knowledge.numbering import renumber_nodes

    renumber_nodes(apps.get_model("knowledge", "KnowledgeNode"))


def backward(apps, schema_editor):
    """Ничего не делает: слияние заданий 8 и 12 необратимо."""


class Migration(migrations.Migration):

    dependencies = [
        ("knowledge", "0006_knowledgedependency_kind_and_more"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
