"""Diagnostic completion → mastery map seed → study plan."""
from django.utils import timezone

from apps.knowledge.models import KnowledgeNode
from apps.knowledge.services import set_mastery
from apps.planning.services import build_study_plan
from apps.progress.services import create_snapshot, predict_score

from .models import DiagnosticResult


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

    build_study_plan(student)
    create_snapshot(student)
    return result
