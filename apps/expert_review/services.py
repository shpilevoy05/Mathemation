"""Expert review lifecycle for part-2 solutions."""
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError

from apps.practice.models import Attempt, MistakeBacklogItem, ReviewSchedule
from apps.practice.services import register_mistake, submit_attempt

from .evidence import apply_score_ratio, apply_step_marks
from .models import ExpertReviewRequest, SolutionStepMark


def delete_student_solution_files(student) -> int:
    """Удалить приватные файлы ученика, сохранив метаданные проверок."""
    deleted = 0
    for review in ExpertReviewRequest.objects.filter(student=student).only(
        "id", "solution_file"
    ):
        if review.solution_file.name:
            review.solution_file.delete(save=False)
            review.solution_file = ""
            review.save(update_fields=["solution_file"])
            deleted += 1
    return deleted
@transaction.atomic
def submit_solution(student, assignment, solution_file, attempt=None, mock_result=None):
    if mock_result is not None:
        from apps.mocks.models import MockExamResult
        mock_result = MockExamResult.objects.select_for_update().get(pk=mock_result.pk)
        if (mock_result.student_id != student.pk or assignment.exam_part != 2
                or not mock_result.exam.assignments.filter(pk=assignment.pk).exists()):
            raise ValidationError("Задача не принадлежит этому пробнику.")
        if mock_result.status != MockExamResult.Status.IN_PROGRESS or timezone.now() >= mock_result.deadline:
            raise ValidationError("Приём решений завершён.")
        existing = ExpertReviewRequest.objects.filter(mock_result=mock_result, assignment=assignment).first()
        if existing:
            if existing.status != ExpertReviewRequest.Status.DRAFT:
                raise ValidationError("Работа уже отправлена эксперту.")
            existing.solution_file = solution_file
            existing.save(update_fields=["solution_file"])
            return existing
    return ExpertReviewRequest.objects.create(
        student=student, assignment=assignment, solution_file=solution_file,
        attempt=attempt, mock_result=mock_result,
        status=(
            ExpertReviewRequest.Status.DRAFT
            if mock_result is not None else ExpertReviewRequest.Status.SUBMITTED
        ),
    )


@transaction.atomic
def finish_review(request: ExpertReviewRequest, reviewer, score_by_criteria: dict,
                  comment: str = "", related_node_ids=None,
                  error_tags=None, step_marks=None,
                  needs_resubmission: bool = False) -> ExpertReviewRequest:
    """Expert verdict is the source of truth for part 2.

    Если эксперт отметил шаги эталонного пути, освоение двигают именно они:
    балл говорит, сколько потеряно, а отметки — где именно. Без отметок
    остаётся прежнее поведение по тегам задачи.
    """
    request = ExpertReviewRequest.objects.select_for_update().select_related(
        "student", "assignment", "attempt", "mock_result"
    ).get(pk=request.pk)
    if request.mock_result_id:
        from apps.mocks.models import MockExamResult
        request.mock_result = MockExamResult.objects.select_for_update().get(
            pk=request.mock_result_id
        )
    # A retry from the browser or expert workstation must not apply mastery,
    # backlog changes, mock calibration, or events for a second time.
    if request.reviewed_at is not None:
        return request
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
    marks = _save_step_marks(request, step_marks or [])
    if marks:
        # Пошаговое свидетельство точнее тегов задачи: тегами двигать освоение
        # после него значило бы посчитать одно и то же действие дважды.
        apply_step_marks(request)
        _close_plan_for_done_steps(request)
    else:
        apply_score_ratio(request)
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
    else:
        open_items = MistakeBacklogItem.objects.filter(
            student=request.student, assignment=request.assignment
        ).exclude(status=MistakeBacklogItem.Status.RESOLVED)
        now = timezone.now()
        for item in open_items:
            item.status = MistakeBacklogItem.Status.RESOLVED
            item.resolved_at = now
            item.save(update_fields=["status", "resolved_at"])
            item.reviews.filter(status=ReviewSchedule.Status.PENDING).update(
                status=ReviewSchedule.Status.COMPLETED
            )
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


def _save_step_marks(request: ExpertReviewRequest, step_marks) -> list[SolutionStepMark]:
    """Сохранить отметки эксперта по шагам эталонного пути.

    Шаги обязаны принадлежать задаче этой работы: отметка по чужому пути
    двигала бы освоение навыков, которых ученик здесь не касался.
    """
    from apps.content.models import SolutionStep

    if not step_marks:
        return []
    allowed = {
        step.pk: step
        for step in SolutionStep.objects.filter(
            path__assignment=request.assignment, path__is_active=True
        )
    }
    saved = []
    for mark in step_marks:
        step = allowed.get(int(mark["step_id"]))
        if step is None:
            continue
        saved.append(
            SolutionStepMark.objects.update_or_create(
                review=request, step=step,
                defaults={
                    "outcome": mark["outcome"],
                    "comment": mark.get("comment", ""),
                },
            )[0]
        )
    return saved


def _close_plan_for_done_steps(request: ExpertReviewRequest) -> None:
    """Закрыть пункты плана по навыкам, выполненным в работе верно.

    Ученик уже сделал работу; отмечать её руками в плане — лишний шаг.
    """
    from apps.planning.services import autocomplete_items_for_node

    done_nodes = {
        mark.step.node
        for mark in request.step_marks.select_related("step__node")
        if mark.outcome == SolutionStepMark.Outcome.DONE
    }
    for node in done_nodes:
        autocomplete_items_for_node(request.student, node)
