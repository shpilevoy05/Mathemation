"""Структура ЕГЭ по профильной математике — разметкой в коде.

Структура экзамена меняется раз в год приказом Рособрнадзора, и меняется она
целиком: номера заданий, их баллы и таблица перевода связаны между собой.
Держать это в базе и править руками — гарантированный способ получить профиль,
в котором сумма баллов заданий не равна максимальному первичному баллу.

Здесь описан вариант 2027 года (демоверсия, спецификация и кодификатор ФИПИ):
20 заданий, часть 1 — задания 1–13 с кратким ответом (13 баллов), часть 2 —
задания 14–20 с развёрнутым ответом (20 баллов), максимум 33 первичных балла.

По сравнению с предыдущей версией (19 заданий, 32 балла):

* в часть 1 добавлено задание 6 — случайная величина, распределение
  вероятностей, математическое ожидание, дисперсия и стандартное отклонение;
* в часть 1 добавлено задание 13 — текстовые задачи разных типов, в том числе
  из области управления личными и семейными финансами;
* в часть 2 добавлено задание 17 — моделирование реальных ситуаций и текстовые
  задачи, в том числе из других учебных предметов;
* прежние задания 8 (производная по графику) и 12 (наибольшее и наименьшее
  значение) сведены в одно задание 9;
* остальные задания сдвинулись по номерам — карта перехода лежит в
  `apps.knowledge.numbering`.
"""

from __future__ import annotations

# (номер, часть, максимальный балл, сложность 1..5, тема)
TASKS: list[tuple[int, int, int, int, str]] = [
    (1, 1, 1, 2, "Планиметрия: углы, площади, подобие"),
    (2, 1, 1, 2, "Векторы и действия с ними"),
    (3, 1, 1, 2, "Стереометрия: углы, расстояния, объёмы"),
    (4, 1, 1, 2, "Вероятность случайного события"),
    (5, 1, 1, 3, "Вероятность: сложение, умножение, полная вероятность"),
    (6, 1, 1, 3, "Случайная величина: распределение, ожидание, дисперсия"),
    (7, 1, 1, 2, "Простейшие уравнения и неравенства"),
    (8, 1, 1, 3, "Вычисления и преобразования: степени, логарифмы, дроби"),
    (9, 1, 1, 3, "Производная и первообразная: исследование функций"),
    (10, 1, 1, 3, "Моделирование реальных ситуаций"),
    (11, 1, 1, 3, "Текстовые задачи разных типов"),
    (12, 1, 1, 4, "Зависимости между величинами и графики функций"),
    (13, 1, 1, 4, "Текстовые задачи, в том числе о личных финансах"),
    (14, 2, 2, 4, "Уравнения и системы"),
    (15, 2, 3, 4, "Стереометрия с обоснованием"),
    (16, 2, 2, 4, "Неравенства"),
    (17, 2, 2, 4, "Экономическая задача и моделирование"),
    (18, 2, 3, 5, "Планиметрия с обоснованием"),
    (19, 2, 4, 5, "Уравнения и неравенства с параметром"),
    (20, 2, 4, 5, "Числа и их свойства"),
]

YEAR = 2027
TITLE = "ЕГЭ, профильная математика"
MAX_PRIMARY_SCORE = sum(task[2] for task in TASKS)

# Предварительная шкала перевода первичных баллов в тестовые.
#
# Официальной таблицы на 33 балла на момент правки нет: Рособрнадзор публикует
# её отдельным документом. Пока её нет, шкала получена из прежней (на 32 балла)
# по структуре самого экзамена: баллы части 1 растянуты с двенадцати заданий на
# тринадцать, а часть 2 сдвинута на один балл. Профиль помечен как
# неофициальный — прогноз это показывает, и подменять им настоящую шкалу нельзя.
PRIMARY_TO_SCALED = [
    0, 5, 8, 13, 17, 20, 25, 30, 35, 41, 46, 51, 56, 62,
    68, 70, 72, 74, 76, 78, 80, 82, 84, 86, 88, 90, 92, 94, 96, 98, 99,
    100, 100, 100,
]
SCALE_IS_OFFICIAL = False


def load_blueprint(*, dry_run: bool = False, activate: bool = True) -> dict:
    """Разложить структуру экзамена по базе. Идемпотентно.

    Задания привязываются к тем узлам графа, у которых номер задания указан
    в `ege_task_numbers`: связь описывает методист в разметке навыков, а не
    этот файл. Незамапленное задание остаётся без навыков — это видно в отчёте
    и означает, что графу нечего сказать про целый номер экзамена.
    """
    from apps.knowledge.models import KnowledgeNode

    from .models import ExamProfile, ExamTask, ExamTaskSkill

    if len(PRIMARY_TO_SCALED) != MAX_PRIMARY_SCORE + 1:
        raise ValueError(
            f"Шкала перевода описывает {len(PRIMARY_TO_SCALED)} значений, "
            f"а первичных баллов {MAX_PRIMARY_SCORE + 1}."
        )

    nodes = list(KnowledgeNode.objects.only("id", "ege_task_numbers"))
    by_number: dict[int, list[int]] = {}
    for node in nodes:
        for number in node.ege_task_numbers or []:
            by_number.setdefault(int(number), []).append(node.pk)

    report = {
        "year": YEAR,
        "tasks": len(TASKS),
        "max_primary_score": MAX_PRIMARY_SCORE,
        "created": False,
        "linked": 0,
        "tasks_without_skills": [
            number for number, _part, _score, _difficulty, _title in TASKS
            if not by_number.get(number)
        ],
        "dry_run": dry_run,
    }
    if dry_run:
        return report

    profile, created = ExamProfile.objects.update_or_create(
        year=YEAR,
        defaults={
            "title": TITLE,
            "max_primary_score": MAX_PRIMARY_SCORE,
            "primary_to_scaled": list(PRIMARY_TO_SCALED),
            "scale_is_official": SCALE_IS_OFFICIAL,
            "is_active": activate,
        },
    )
    report["created"] = created
    if activate:
        ExamProfile.objects.exclude(pk=profile.pk).update(is_active=False)

    numbers = {number for number, *_rest in TASKS}
    for number, part, max_score, difficulty, title in TASKS:
        task, _ = ExamTask.objects.update_or_create(
            profile=profile, number=number,
            defaults={
                "exam_part": part,
                "max_score": max_score,
                "difficulty": difficulty,
                "title": title,
            },
        )
        wanted = set(by_number.get(number, []))
        ExamTaskSkill.objects.filter(task=task).exclude(node_id__in=wanted).delete()
        for node_id in wanted:
            _, made = ExamTaskSkill.objects.get_or_create(task=task, node_id=node_id)
            report["linked"] += int(made)
    # Задания, которых больше нет в структуре, из профиля убираем: иначе сумма
    # баллов профиля перестанет совпадать с максимальным первичным баллом.
    profile.tasks.exclude(number__in=numbers).delete()
    return report
