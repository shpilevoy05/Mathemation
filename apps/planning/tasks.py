"""Ночное обслуживание планов.

Днём план меняется по событиям: ответ, ошибка, пробник. Ночью нужно поправить
то, что события не видят, — просроченные пункты и порядок очереди, который
устарел из-за выросшего освоения.
"""

from celery import shared_task


@shared_task
def refresh_plans():
    """Перенести просрочку и переоценить очередь у активных планов."""
    from apps.accounts.models import StudentProfile

    from .models import StudyPlan
    from .services import carry_over_overdue, reprioritize_plan

    student_ids = (
        StudyPlan.objects.filter(status=StudyPlan.Status.ACTIVE)
        .values_list("student_id", flat=True)
        .distinct()
    )
    processed = 0
    for student in StudentProfile.objects.filter(
        pk__in=list(student_ids), user__is_active=True
    ):
        carry_over_overdue(student)
        reprioritize_plan(student)
        processed += 1
    return processed
