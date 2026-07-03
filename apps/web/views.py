"""Minimal server-rendered student dashboard. All logic lives in services."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.planning.services import get_active_plan, items_for_period
from apps.practice.services import due_reviews
from apps.progress.models import ProgressSnapshot


@login_required
def dashboard(request):
    student = getattr(request.user, "student_profile", None)
    context = {"student": student}
    if student:
        today = timezone.localdate()
        context.update({
            "today_items": items_for_period(student, today, today),
            "due_reviews": due_reviews(student),
            "snapshot": ProgressSnapshot.objects.filter(student=student).first(),
            "has_plan": get_active_plan(student) is not None,
        })
    return render(request, "dashboard.html", context)
