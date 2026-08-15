"""Expert review lifecycle for part-2 solutions."""
from django.utils import timezone

from apps.practice.models import Attempt, MistakeBacklogItem
from apps.practice.services import process_attempt_result, register_mistake, submit_attempt

from .models import ExpertReviewRequest


def submit_solution(student, assignment, solution_file, attempt=None, mock_result=None):
    return ExpertReviewRequest.objects.create(
        student=student, assignment=assignment, solution_file=solution_file,
        attempt=attempt, mock_result=mock_result,
    )


def finish_review(request: ExpertReviewRequest, reviewer, score_by_criteria: dict,
                  comment: str = "", related_node_ids=None,
                  error_tags=None,
                  needs_resubmission: bool = False) -> ExpertReviewRequest:
    """Expert verdict is the source of truth for part 2."""
    request.reviewer = reviewer
    request.score_by_criteria = score_by_criteria
    request.total_score = sum(score_by_criteria.values())
    request.lost_points = max(request.assignment.max_score - request.total_score, 0)
    request.comment = comment
    request.error_tags = error_tags or []
    request.status = (
        ExpertReviewRequest.Status.NEEDS_RESUBMISSION
        if needs_resubmission
        else ExpertReviewRequest.Status.REVIEWED
    )
    request.reviewed_at = timezone.now()
    request.save()
    if related_node_ids:
        request.related_nodes.set(related_node_ids)

    # Propagate the verdict into mastery/backlog via the linked attempt.
    attempt = request.attempt
    if attempt is None:
        attempt = submit_attempt(
            request.student,
            request.assignment,
            "",
            context=Attempt.Context.MOCK if request.mock_result else Attempt.Context.LESSON,
            mock_result=request.mock_result,
            strict=False,
        )
        request.attempt = attempt
        request.save(update_fields=["attempt"])
    attempt.is_correct = request.lost_points == 0
    attempt.save(update_fields=["is_correct"])
    process_attempt_result(attempt)
    # Вердикт по пробнику: пересчитать итог и, если все работы проверены,
    # закрыть пробник (калибровка прогноза + адаптация плана).
    if request.mock_result:
        from apps.mocks.services import maybe_complete_mock

        maybe_complete_mock(request.mock_result)
    # Nodes named by the expert beyond the assignment tags also feed the backlog.
    if request.lost_points:
        tagged_ids = set(
            request.assignment.skill_tags.values_list("node_id", flat=True)
        )
        for node in request.related_nodes.exclude(pk__in=tagged_ids):
            register_mistake(request.student, request.assignment, node)
    apply_error_tags(request)

    from apps.events.models import Event
    from apps.events.services import log_event

    log_event(
        Event.Type.EXPERT_REVIEW_COMPLETED,
        student=request.student,
        request_id=request.id,
        criteria_scores=score_by_criteria,
        error_tags=request.error_tags,
    )
    return request


def apply_error_tags(request: ExpertReviewRequest) -> None:
    valid = set(MistakeBacklogItem.ErrorType.values)
    default_type = None
    by_node = {}
    for tag in request.error_tags:
        if isinstance(tag, str) and tag in valid and default_type is None:
            default_type = tag
        elif isinstance(tag, dict):
            error_type = tag.get("error_type", tag.get("type"))
            node_id = tag.get("node_id")
            if error_type in valid:
                if node_id is None and default_type is None:
                    default_type = error_type
                elif node_id is not None:
                    by_node[int(node_id)] = error_type

    items = MistakeBacklogItem.objects.filter(
        student=request.student,
        assignment=request.assignment,
    ).exclude(status=MistakeBacklogItem.Status.RESOLVED)
    for item in items:
        error_type = by_node.get(item.node_id, default_type)
        if error_type:
            item.error_type = error_type
            item.save(update_fields=["error_type"])
