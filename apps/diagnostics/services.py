"""Diagnostic completion → mastery map seed → study plan."""
from django.utils import timezone

from apps.knowledge.models import KnowledgeNode
from apps.knowledge.services import set_mastery
from apps.planning.services import assign_trajectory, build_study_plan
from apps.progress.services import create_snapshot, predict_score

from .models import DiagnosticResult, DiagnosticTest


def start_diagnostic(student, test: DiagnosticTest) -> DiagnosticResult:
    result = DiagnosticResult.objects.create(student=student, test=test)
    from apps.events.models import Event
    from apps.events.services import log_event

    log_event(
        Event.Type.DIAGNOSTIC_STARTED,
        student=student,
        test_id=test.id,
        result_id=result.id,
    )
    return result


def complete_diagnostic(result: DiagnosticResult) -> DiagnosticResult:
    """Seed the mastery map from diagnostic attempts, then build the plan.

    Seeding rule (MVP): per node, mastery = correct_share * 100 across the
    diagnostic attempts touching that node; untouched nodes stay at 0.
    """
    student = result.student
    per_node: dict[int, list[bool]] = {}
    for attempt in result.attempts.filter(is_correct__isnull=False).select_related("assignment"):
        for tag in attempt.assignment.skill_tags.all():
            per_node.setdefault(tag.node_id, []).append(attempt.is_correct)
    for node_id, answers in per_node.items():
        node = KnowledgeNode.objects.get(pk=node_id)
        set_mastery(student, node, 100.0 * sum(answers) / len(answers))

    result.primary_score = result.attempts.filter(is_correct=True).count()
    predicted, _ = predict_score(student)
    result.estimated_score = predicted
    result.status = DiagnosticResult.Status.COMPLETED
    result.completed_at = timezone.now()
    result.save()

    if student.start_score is None:
        student.start_score = predicted
        student.save(update_fields=["start_score"])

    assign_trajectory(student, student.target_score)
    build_study_plan(student)
    create_snapshot(student)
    from apps.events.models import Event
    from apps.events.services import log_event

    log_event(
        Event.Type.DIAGNOSTIC_SUBMITTED,
        student=student,
        test_id=result.test_id,
        result_id=result.id,
        primary_score=result.primary_score,
        estimated_score=result.estimated_score,
    )
    return result
