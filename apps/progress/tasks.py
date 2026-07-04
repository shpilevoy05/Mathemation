from celery import shared_task


@shared_task
def generate_weekly_parent_reports():
    """Build weekly pulse reports for all students (schedule via celery beat)."""
    from apps.accounts.models import StudentProfile

    from .services import build_parent_report

    for student in StudentProfile.objects.all():
        build_parent_report(student)


@shared_task
def detect_inactivity(days: int | None = None):
    """Rebuild plans for students idle for `days`+ days (сжатое время).

    Skips students whose active plan is newer than the cutoff — their plan was
    already rebuilt during the pause.
    """
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from apps.accounts.models import StudentProfile
    from apps.planning.services import get_active_plan, rebuild_after_inactivity

    days = days or settings.INACTIVITY_REBUILD_DAYS
    cutoff = timezone.now() - timedelta(days=days)
    for student in StudentProfile.objects.exclude(attempts__created_at__gte=cutoff):
        plan = get_active_plan(student)
        if plan is None or plan.created_at >= cutoff:
            continue
        rebuild_after_inactivity(student, idle_days=days)
