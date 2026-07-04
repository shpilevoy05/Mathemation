"""Minimal server-rendered student dashboard. All logic lives in services."""
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.knowledge.services import apply_decay
from apps.planning.services import get_active_plan, items_for_period
from apps.practice.services import due_reviews
from apps.progress.models import ProgressSnapshot
from apps.progress.services import ceiling_forecast


@login_required
def dashboard(request):
    student = getattr(request.user, "student_profile", None)
    context = {"student": student}
    if student:
        apply_decay(student)
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        plan = get_active_plan(student)
        context.update({
            "today_items": items_for_period(student, today, today),
            "week_items": items_for_period(
                student, week_start, week_start + timedelta(days=6)
            ),
            "due_reviews": due_reviews(student),
            "snapshot": ProgressSnapshot.objects.filter(student=student).first(),
            "has_plan": plan is not None,
            # Резкие изменения плана — большое всплывающее окно до подтверждения.
            "major_changes": (
                plan.change_logs.filter(is_major=True, acknowledged=False)
                if plan else []
            ),
            "forecast": ceiling_forecast(student) if plan else None,
        })
    return render(request, "dashboard.html", context)
