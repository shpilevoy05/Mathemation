"""Repair the 2027 task map written by knowledge.0007 and reload the profile.

Migration 0007 incorrectly merged old tasks 8 and 12 into task 9 and moved
old task 16 to task 17.  After that migration the number alone cannot reveal
the origin, so the reference nodes are repaired by stable code.
"""

from django.db import migrations


# Explicit decisions for every demo/reference node carrying 9 or 17 after 0007.
REFERENCE_NODE_NUMBERS = {
    "deriv-graph": [9],
    "extrema": [17],
    "economics": [13],
}

YEAR = 2027
TITLE = "ЕГЭ, профильная математика"
TASKS = [
    (1, 1, 1, 2, "Планиметрия: углы, площади, подобие"),
    (2, 1, 1, 2, "Векторы и действия с ними"),
    (3, 1, 1, 2, "Стереометрия: углы, расстояния, объёмы"),
    (4, 1, 1, 2, "Вероятность случайного события"),
    (5, 1, 1, 3, "Вероятность: сложение, умножение, полная вероятность"),
    (6, 1, 1, 3, "Случайная величина: распределение, ожидание, дисперсия"),
    (7, 1, 1, 2, "Простейшие уравнения и неравенства"),
    (8, 1, 1, 3, "Вычисления и преобразования: степени, логарифмы, дроби"),
    (9, 1, 1, 3, "Производная и первообразная по графику"),
    (10, 1, 1, 3, "Моделирование реальных ситуаций"),
    (11, 1, 1, 3, "Текстовые задачи разных типов"),
    (12, 1, 1, 4, "Зависимости между величинами и графики функций"),
    (13, 1, 1, 4, "Экономическая задача и финансы (краткий ответ)"),
    (14, 2, 2, 4, "Уравнения и системы"),
    (15, 2, 3, 4, "Стереометрия с обоснованием"),
    (16, 2, 2, 4, "Неравенства"),
    (17, 2, 2, 4, "Моделирование реальных ситуаций: алгебра и начала анализа"),
    (18, 2, 3, 5, "Планиметрия с обоснованием"),
    (19, 2, 4, 5, "Уравнения и неравенства с параметром"),
    (20, 2, 4, 5, "Числа и их свойства"),
]
PRIMARY_TO_SCALED = [
    0, 5, 8, 13, 17, 20, 25, 30, 35, 41, 46, 51, 56, 62,
    68, 70, 72, 74, 76, 78, 80, 82, 84, 86, 88, 90, 92, 94, 96, 98, 99,
    100, 100, 100,
]


def repair_reference_nodes(node_model, *, using="default"):
    """Apply the code-based decisions; return how many rows changed."""
    changed = 0
    nodes = node_model.objects.using(using).filter(code__in=REFERENCE_NODE_NUMBERS)
    for node in nodes.only("pk", "code", "ege_task_numbers"):
        wanted = REFERENCE_NODE_NUMBERS[node.code]
        if list(node.ege_task_numbers or []) != wanted:
            node_model.objects.using(using).filter(pk=node.pk).update(
                ege_task_numbers=list(wanted)
            )
            changed += 1
    return changed


def sync_exam_profile(apps, *, using="default"):
    """Historical-model equivalent of load_blueprint for the corrected snapshot."""
    KnowledgeNode = apps.get_model("knowledge", "KnowledgeNode")
    ExamProfile = apps.get_model("exams", "ExamProfile")
    ExamTask = apps.get_model("exams", "ExamTask")
    ExamTaskSkill = apps.get_model("exams", "ExamTaskSkill")

    by_number = {}
    for node in KnowledgeNode.objects.using(using).only("pk", "ege_task_numbers"):
        for number in node.ege_task_numbers or []:
            by_number.setdefault(int(number), []).append(node.pk)

    # Avoid the conditional unique constraint if another year is active.
    ExamProfile.objects.using(using).exclude(year=YEAR).update(is_active=False)
    profile, _ = ExamProfile.objects.using(using).update_or_create(
        year=YEAR,
        defaults={
            "title": TITLE,
            "max_primary_score": 33,
            "primary_to_scaled": list(PRIMARY_TO_SCALED),
            "scale_is_official": False,
            "is_active": True,
        },
    )

    numbers = {number for number, *_rest in TASKS}
    for number, part, max_score, difficulty, title in TASKS:
        task, _ = ExamTask.objects.using(using).update_or_create(
            profile=profile,
            number=number,
            defaults={
                "exam_part": part,
                "max_score": max_score,
                "difficulty": difficulty,
                "title": title,
            },
        )
        wanted = set(by_number.get(number, []))
        links = ExamTaskSkill.objects.using(using).filter(task=task)
        links.exclude(node_id__in=wanted).delete()
        for node_id in wanted:
            ExamTaskSkill.objects.using(using).get_or_create(
                task=task, node_id=node_id
            )

    ExamTask.objects.using(using).filter(profile=profile).exclude(
        number__in=numbers
    ).delete()


def forward(apps, schema_editor):
    using = schema_editor.connection.alias
    KnowledgeNode = apps.get_model("knowledge", "KnowledgeNode")
    repair_reference_nodes(KnowledgeNode, using=using)
    sync_exam_profile(apps, using=using)


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0002_examprofile_scale_is_official_examtask_title"),
        ("knowledge", "0009_skillmastery_last_retention_failure_at"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
