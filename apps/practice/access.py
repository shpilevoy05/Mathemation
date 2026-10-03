"""Server-side isolation of ongoing assessments from practice and hints."""
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone


class AssessmentInProgress(PermissionDenied):
    def __init__(self, message: str, *, kind: str, title: str, url: str):
        super().__init__(message)
        self.payload = {
            "detail": message,
            "code": "assessment_in_progress",
            "kind": kind,
            "title": title,
            "url": url,
        }


def ensure_practice_allowed(student, assignment):
    from apps.diagnostics.models import DiagnosticResult
    from apps.mocks.models import MockExamResult
    from apps.arena.services import blocking_match_for_practice
    from apps.mocks.services import finalize_expired_mocks_for

    now = timezone.now()
    finalize_expired_mocks_for(student, now=now)
    mock = (
        MockExamResult.objects.filter(
            student=student,
            status=MockExamResult.Status.IN_PROGRESS,
            exam__assignments=assignment,
        )
        .select_related("exam")
        .first()
    )
    if mock is not None and now < mock.deadline:
        deadline = timezone.localtime(mock.deadline).strftime("%H:%M")
        raise AssessmentInProgress(
            f"Эта задача есть в пробнике «{mock.exam.title}», который идёт сейчас "
            f"(до {deadline}). Завершите его — и задача откроется для тренировки.",
            kind="mock",
            title=mock.exam.title,
            url=reverse("mock_run", args=[mock.pk]),
        )

    diagnostic = (
        DiagnosticResult.objects.filter(
            student=student,
            status=DiagnosticResult.Status.IN_PROGRESS,
            test__assignments=assignment,
        )
        .select_related("test")
        .first()
    )
    if diagnostic is not None:
        raise AssessmentInProgress(
            f"Эта задача есть во входной диагностике «{diagnostic.test.title}», "
            "которая не завершена. Завершите её — и задача откроется для тренировки.",
            kind="diagnostic",
            title=diagnostic.test.title,
            url=reverse("diagnostic_run", args=[diagnostic.pk]),
        )

    match = blocking_match_for_practice(student, assignment, now=now)
    if match is not None:
        title = f"Партия арены: {match.get_mode_display()}"
        raise AssessmentInProgress(
            "Эта задача есть в партии арены, которая идёт сейчас. Завершите её — "
            "и задача откроется для тренировки.",
            kind="arena",
            title=title,
            url=reverse("arena_match", args=[match.pk]),
        )
