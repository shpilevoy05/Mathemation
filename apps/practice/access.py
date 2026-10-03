"""Server-side isolation of ongoing assessments from practice and hints."""
from django.core.exceptions import PermissionDenied


def ensure_practice_allowed(student, assignment):
    from apps.diagnostics.models import DiagnosticResult
    from apps.mocks.models import MockExamResult
    from apps.arena.models import Match

    if (
        MockExamResult.objects.filter(student=student, status="in_progress", exam__assignments=assignment).exists()
        or DiagnosticResult.objects.filter(student=student, status="in_progress", test__assignments=assignment).exists()
        or Match.objects.filter(participants__student=student, status__in=["active", "lobby"], questions__assignment=assignment).exists()
    ):
        raise PermissionDenied("Задача участвует в текущей контрольной работе или партии. Завершите её, чтобы перейти к тренировке.")
