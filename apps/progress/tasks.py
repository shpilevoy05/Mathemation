from celery import shared_task


@shared_task
def generate_weekly_parent_reports():
    """Build weekly pulse reports for all students (schedule via celery beat)."""
    from apps.accounts.models import StudentProfile

    from .services import build_parent_report

    for student in StudentProfile.objects.all():
        build_parent_report(student)


@shared_task
def detect_inactivity(days: int = 7):
    """Log a plan change for students with no attempts for `days` days."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.accounts.models import StudentProfile
    from apps.planning.models import PlanChangeLog
    from apps.planning.services import log_plan_change

    cutoff = timezone.now() - timedelta(days=days)
    for student in StudentProfile.objects.exclude(attempts__created_at__gte=cutoff):
        log_plan_change(
            student,
            reason=PlanChangeLog.Reason.INACTIVITY,
            description=f"Нет активности {days}+ дней — план требует пересмотра.",
        )
