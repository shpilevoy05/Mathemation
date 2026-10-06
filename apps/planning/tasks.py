"""Ночное обслуживание планов.

Днём выполненные пункты только закрываются, а срочные добавляются отдельно.
Просрочка и переоценка будущих недель выполняются здесь один раз в сутки.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def refresh_plans():
    """Refresh future plans and warm their student-facing contracts."""
    from apps.accounts.models import StudentProfile
    from apps.progress.services import plan_contract

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
        try:
            carry_over_overdue(student)
            reprioritize_plan(student)
        except Exception:
            logger.exception("Nightly plan refresh failed for student %s", student.pk)
            continue
        processed += 1
        try:
            # The contract is a daily forecast. Warming this date-based key
            # keeps the first daytime request cheap; a missed warm-up is safe
            # because that request computes and stores the same daily value.
            plan_contract(student)
        except Exception:
            logger.exception("Contract cache warm-up failed for student %s", student.pk)
    return processed
