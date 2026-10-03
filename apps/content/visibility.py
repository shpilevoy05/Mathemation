"""Shared publication boundary for student-facing content."""
from django.db.models import Q

from .models import Assignment, Lesson, TheoryBlock


def visible_assignments():
    # Standalone assignments are used by diagnostics and the task bank.
    return Assignment.objects.filter(
        Q(lesson__isnull=True) | Q(lesson__status=Lesson.Status.PUBLISHED)
    ).distinct()


def visible_theory():
    return TheoryBlock.objects.filter(lesson__status=Lesson.Status.PUBLISHED)


def can_preview_content(user):
    return user.is_superuser or user.role in ("methodist", "expert")
