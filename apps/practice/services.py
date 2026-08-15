"""Attempt processing: mastery update, mistake backlog, spaced repetition."""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.content.models import Assignment
from apps.engine.decay import next_intervals
from apps.engine.dto import EngineParams
from apps.knowledge.services import update_mastery
from apps.planning.models import PlanChangeLog
from apps.planning.services import reinsert_node

from .models import Attempt, MistakeBacklogItem, ReviewSchedule


def _engine_params() -> EngineParams:
    return EngineParams(
        mastery_threshold=settings.MASTERY_THRESHOLD,
        decay_grace_days=settings.DECAY_GRACE_DAYS,
        decay_rate_per_day=settings.DECAY_RATE_PER_DAY,
        max_primary_score=settings.MAX_PRIMARY_SCORE,
        hours_per_node=settings.HOURS_PER_NODE,
        attainable_mastery=settings.ATTAINABLE_MASTERY,
        bkt_alpha=settings.BKT_ALPHA,
        forecast_calibration_alpha=settings.FORECAST_CALIBRATION_ALPHA,
        theta_scale=settings.IRT_THETA_SCALE,
        b_step=settings.IRT_DIFFICULTY_STEP,
        default_discrimination=settings.IRT_DEFAULT_DISCRIMINATION,
        guess=settings.IRT_GUESS,
        review_intervals_days=tuple(settings.REVIEW_INTERVALS_DAYS),
        review_ease=settings.REVIEW_EASE,
        min_review_interval_days=settings.MIN_REVIEW_INTERVAL_DAYS,
        max_review_interval_days=settings.MAX_REVIEW_INTERVAL_DAYS,
    )


class AnswerNotUnderstood(ValueError):
    """Ответ не разобран: описку нельзя записывать ученику в незнание темы."""


@transaction.atomic
def submit_attempt(student, assignment: Assignment, answer: str, context: str,
                   diagnostic_result=None, mock_result=None, *, strict: bool = True) -> Attempt:
    """Create an attempt; auto-check part 1, leave part 2 for expert review.

    Попытка привязывается к версии задания: после правки условия видно, что
    именно решал ученик.
    """
    from apps.content.services import current_version

    is_correct = None
    if assignment.exam_part == Assignment.Part.PART1:
        is_correct = assignment.check_answer(answer)
        if is_correct is None:
            # Запись не разобрана: это не ошибка решения. В занятии просим
            # переписать — иначе освоение темы падало бы за пропущенную скобку.
            if strict:
                raise AnswerNotUnderstood(
                    "Не понял запись ответа. Проверьте скобки и обозначения — "
                    "например: π/6 + 2πk; 5π/6 + 2πk"
                )
            # На диагностике и пробнике переспросить некого: работа сдаётся
            # целиком, и нечитаемый ответ засчитывается как неверный — так же,
            # как на экзамене. Сам текст остаётся в попытке для разбора.
            is_correct = False

    attempt = Attempt.objects.create(
        student=student, assignment=assignment,
        assignment_version=current_version(assignment), context=context,
        submitted_answer=answer, is_correct=is_correct,
        diagnostic_result=diagnostic_result, mock_result=mock_result,
    )
    from apps.events.models import Event
    from apps.events.services import log_event

    if is_correct:
        # Домашка закрывается сама, как только решены все её задачи.
        from apps.content.services import close_completed_homework

        close_completed_homework(attempt)

    node_ids = list(assignment.skill_tags.values_list("node_id", flat=True))
    log_event(
        Event.Type.ATTEMPT_SUBMITTED,
        student=student,
        assignment_id=assignment.id,
        node_ids=node_ids,
        context=context,
        is_correct=is_correct,
        submitted_answer=answer,
    )
    if is_correct is not None:
        process_attempt_result(attempt)
    from apps.gamification.services import record_attempt_activity

    record_attempt_activity(student, is_correct)
    return attempt


def process_attempt_result(attempt: Attempt) -> None:
    """Update mastery for tagged nodes; on mistakes feed the backlog.

    Also called by expert review once a part-2 verdict arrives.
    """
    from apps.planning.services import autocomplete_items_for_node

    for tag in attempt.assignment.skill_tags.select_related("node"):
        update_mastery(attempt.student, tag.node, bool(attempt.is_correct), tag.weight)
        if attempt.is_correct is False:
            register_mistake(attempt.student, attempt.assignment, tag.node)
        else:
            # Верная задача закрывает соответствующие пункты плана сама:
            # ученик уже сделал работу, отмечать её руками незачем.
            autocomplete_items_for_node(attempt.student, tag.node)


def register_mistake(
    student,
    assignment,
    node,
    error_type: str = MistakeBacklogItem.ErrorType.UNKNOWN,
) -> MistakeBacklogItem:
    item = (
        MistakeBacklogItem.objects
        .filter(student=student, assignment=assignment, node=node)
        .exclude(status=MistakeBacklogItem.Status.RESOLVED)
        .first()
    )
    if item:
        item.error_count += 1
        update_fields = ["error_count"]
        if error_type in MistakeBacklogItem.ErrorType.values and (
            error_type != MistakeBacklogItem.ErrorType.UNKNOWN
        ):
            item.error_type = error_type
            update_fields.append("error_type")
        item.save(update_fields=update_fields)
    else:
        item = MistakeBacklogItem.objects.create(
            student=student, assignment=assignment, node=node,
            status=MistakeBacklogItem.Status.IN_REVIEW,
            error_type=error_type,
        )
        schedule_reviews(item)

    _maybe_reinsert_topic(student, node)
    return item


def schedule_reviews(item: MistakeBacklogItem) -> list[ReviewSchedule]:
    """Create the unchanged base ladder for a new mistake."""
    return _create_review_schedule(item, settings.REVIEW_INTERVALS_DAYS)


def _create_review_schedule(
    item: MistakeBacklogItem, intervals: list[int] | tuple[int, ...]
) -> list[ReviewSchedule]:
    today = timezone.localdate()
    return [
        ReviewSchedule.objects.create(
            backlog_item=item, interval_days=days, due_date=today + timedelta(days=days)
        )
        for days in intervals
    ]


def _maybe_reinsert_topic(student, node) -> None:
    """Frequent mistakes on a node send the topic back into the plan."""
    open_errors = sum(
        MistakeBacklogItem.objects
        .filter(student=student, node=node)
        .exclude(status=MistakeBacklogItem.Status.RESOLVED)
        .values_list("error_count", flat=True)
    )
    if open_errors >= settings.FREQUENT_MISTAKE_THRESHOLD:
        reinsert_node(
            student, node,
            reason=PlanChangeLog.Reason.FREQUENT_MISTAKES,
            description=f"Частые ошибки по навыку «{node.title}» ({open_errors} открытых).",
        )
        from apps.planning.services import maybe_transition

        maybe_transition(
            student,
            PlanChangeLog.Reason.FREQUENT_MISTAKES,
            {"error_count": open_errors, "node_ids": [node.id]},
        )


@transaction.atomic
def complete_review(review: ReviewSchedule, success: bool) -> None:
    if review.status == ReviewSchedule.Status.COMPLETED:
        return
    review.status = ReviewSchedule.Status.COMPLETED
    review.save(update_fields=["status"])
    item = review.backlog_item
    if not success:
        # Failed a repetition: reset remaining schedule from today.
        item.reviews.filter(status=ReviewSchedule.Status.PENDING).delete()
        item.error_count += 1
        item.save(update_fields=["error_count"])
        _create_review_schedule(
            item, next_intervals(item.error_count, 0, _engine_params())
        )
    else:
        next_pending = item.reviews.filter(
            status=ReviewSchedule.Status.PENDING
        ).order_by("due_date", "id").first()
        if next_pending:
            params = _engine_params()
            stretched = min(
                max(
                    int(round(next_pending.interval_days * params.review_ease)),
                    params.min_review_interval_days,
                ),
                params.max_review_interval_days,
            )
            next_pending.interval_days = stretched
            next_pending.due_date = timezone.localdate() + timedelta(days=stretched)
            next_pending.save(update_fields=["interval_days", "due_date"])
        else:
            item.status = MistakeBacklogItem.Status.RESOLVED
            item.resolved_at = timezone.now()
            item.save(update_fields=["status", "resolved_at"])
    from apps.events.models import Event
    from apps.events.services import log_event

    log_event(
        Event.Type.REVIEW_COMPLETED,
        student=item.student,
        backlog_item_id=item.id,
        interval_days=review.interval_days,
        success=success,
    )
    from apps.gamification.services import record_review_activity

    record_review_activity(item.student)
    if success:
        # Успешный повтор закрывает пункт «отработка» в плане.
        from apps.planning.services import autocomplete_review_items

        autocomplete_review_items(item.student, item.node)


def practice_queue(student, node) -> dict:
    """Задачи для занятия по узлу: перед новой темой подмешиваем 1-2 задачи
    на старые слабые места (просроченные повторы с других узлов)."""
    warmup = [
        r.backlog_item.assignment
        for r in due_reviews(student).exclude(backlog_item__node=node)[:2]
    ]
    new_tasks = list(
        Assignment.objects.filter(skill_tags__node=node).distinct()
    )
    return {"warmup": warmup, "new": new_tasks}


def due_reviews(student, on_date=None):
    on_date = on_date or timezone.localdate()
    return (
        ReviewSchedule.objects
        .filter(
            backlog_item__student=student,
            status=ReviewSchedule.Status.PENDING,
            due_date__lte=on_date,
        )
        .select_related("backlog_item__assignment", "backlog_item__node")
    )
