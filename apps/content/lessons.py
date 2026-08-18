"""Занятие как последовательность этапов.

Урок проходится в три шага: материал (видео и конспект), задачи по теме и
отработка ошибок этой темы. Шаги считаются здесь, а не в шаблоне, потому что
одни и те же правила нужны странице, API и тестам.
"""

from __future__ import annotations

from django.utils import timezone

from .models import LessonProgress, TheoryBlock

STAGE_MATERIAL = "material"
STAGE_TASKS = "tasks"
STAGE_REVIEW = "review"


def get_progress(student, node) -> LessonProgress:
    progress, _ = LessonProgress.objects.get_or_create(student=student, node=node)
    return progress


def mark_material_viewed(student, node) -> LessonProgress:
    """Материал просмотрен. Повторный вызов не двигает отметку времени."""
    progress = get_progress(student, node)
    if progress.material_viewed_at is None:
        progress.material_viewed_at = timezone.now()
        progress.save(update_fields=["material_viewed_at", "updated_at"])
    return progress


def mark_summary_downloaded(student, node) -> LessonProgress:
    progress = get_progress(student, node)
    if progress.summary_downloaded_at is None:
        progress.summary_downloaded_at = timezone.now()
        progress.save(update_fields=["summary_downloaded_at", "updated_at"])
    return progress


def task_stats(student, node) -> dict:
    """Сколько задач темы решено верно."""
    from apps.content.models import Assignment
    from apps.practice.models import Attempt

    total = Assignment.objects.filter(skill_tags__node=node).distinct().count()
    solved = (
        Attempt.objects.filter(
            student=student, assignment__skill_tags__node=node, is_correct=True
        )
        .values("assignment_id")
        .distinct()
        .count()
    )
    return {"solved": solved, "total": total, "is_done": bool(total) and solved >= total}


def review_stats(student, node) -> dict:
    """Отработка по теме: открытые ошибки и повторы, назначенные на сегодня."""
    from apps.practice.models import MistakeBacklogItem
    from apps.practice.services import due_reviews

    open_items = MistakeBacklogItem.objects.filter(student=student, node=node).exclude(
        status=MistakeBacklogItem.Status.RESOLVED
    )
    due = list(due_reviews(student).filter(backlog_item__node=node))
    return {
        "open_count": open_items.count(),
        "due": due,
        "due_count": len(due),
        # Этап закрыт, когда на сегодня по теме нечего повторять: либо ошибок
        # нет вовсе, либо все сегодняшние повторы уже сделаны.
        "is_done": not due,
    }


def lesson_stages(student, node) -> list[dict]:
    """Три этапа занятия с состоянием каждого.

    Этап «в работе» ровно один: первый незакрытый. Так шкала сверху всегда
    показывает, где ученик находится, а не просто сколько сделано.
    """
    progress = get_progress(student, node)
    tasks = task_stats(student, node)
    review = review_stats(student, node)
    has_theory = TheoryBlock.objects.filter(lesson__node=node).exists()

    stages = [
        {
            "key": STAGE_MATERIAL,
            "title": "Материал",
            "caption": "Видео и конспект",
            "is_done": progress.material_viewed_at is not None,
            "detail": "Конспект доступен для скачивания" if has_theory else "Конспект готовится",
        },
        {
            "key": STAGE_TASKS,
            "title": "Задачи",
            "caption": f"Решено {tasks['solved']} из {tasks['total']}",
            "is_done": tasks["is_done"],
            "detail": "Разогрев на старом слабом месте, затем новая тема",
        },
        {
            "key": STAGE_REVIEW,
            "title": "Отработка",
            "caption": (
                f"Повторов на сегодня: {review['due_count']}" if review["due_count"]
                else "Повторов на сегодня нет"
            ),
            "is_done": review["is_done"],
            "open_count": review["open_count"],
            "detail": "Ошибки этой темы возвращаются по интервалам 1/3/7/30 дней",
        },
    ]
    current_assigned = False
    for stage in stages:
        stage["is_current"] = not stage["is_done"] and not current_assigned
        current_assigned = current_assigned or stage["is_current"]
    # Все этапы закрыты — занятие пройдено, текущим считается последний.
    if not current_assigned:
        stages[-1]["is_current"] = True
    return stages


def lesson_summary_text(node) -> str:
    """Конспект занятия обычным текстом — его скачивают и печатают.

    Markdown, а не PDF: файл читается где угодно, не тянет зависимостей и
    остаётся редактируемым, если ученик ведёт свой конспект.
    """
    lines = [f"# {node.title}", ""]
    if node.ege_task_numbers:
        numbers = ", ".join(str(number) for number in node.ege_task_numbers)
        lines += [f"Задания ЕГЭ: {numbers}", ""]
    blocks = TheoryBlock.objects.filter(lesson__node=node).select_related("lesson").order_by(
        "lesson__order", "order"
    )
    for block in blocks:
        lines += [f"## {block.title}", "", block.body.strip(), ""]
    if not blocks:
        lines += ["Конспект для этой темы ещё готовится.", ""]

    from apps.content.models import Assignment

    assignments = Assignment.objects.filter(skill_tags__node=node).distinct()
    if assignments:
        lines += ["## Задачи занятия", ""]
        for index, assignment in enumerate(assignments, start=1):
            lines += [f"{index}. {assignment.title}", f"   {assignment.statement.strip()}", ""]
    lines += ["---", "Матемация · конспект занятия"]
    return "\n".join(lines)
