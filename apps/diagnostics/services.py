"""Diagnostic completion → mastery map seed → study plan."""
from django.utils import timezone

from apps.content.models import Assignment
from apps.knowledge.models import KnowledgeNode
from apps.knowledge.services import set_mastery
from apps.planning.services import assign_trajectory, build_study_plan
from apps.practice.models import Attempt
from apps.practice.services import submit_attempt
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


def get_or_start_diagnostic(student, test: DiagnosticTest) -> DiagnosticResult:
    """Resume the student's latest unfinished run of this diagnostic, if any."""
    result = (
        DiagnosticResult.objects.filter(
            student=student,
            test=test,
            status=DiagnosticResult.Status.IN_PROGRESS,
        )
        .order_by("-started_at")
        .first()
    )
    return result or start_diagnostic(student, test)


def submit_diagnostic_answers(result: DiagnosticResult, answers: dict) -> DiagnosticResult:
    """Auto-check only part 1 and complete a diagnostic result."""
    for assignment in result.test.assignments.filter(exam_part=Assignment.Part.PART1):
        submit_attempt(
            result.student,
            assignment,
            str(answers.get(str(assignment.id), "")),
            context=Attempt.Context.DIAGNOSTIC,
            diagnostic_result=result,
        )
    return complete_diagnostic(result)


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
