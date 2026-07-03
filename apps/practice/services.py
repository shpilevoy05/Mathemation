"""Attempt processing: mastery update, mistake backlog, spaced repetition."""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.content.models import Assignment
from apps.knowledge.services import update_mastery
from apps.planning.models import PlanChangeLog
from apps.planning.services import reinsert_node

from .models import Attempt, MistakeBacklogItem, ReviewSchedule


def submit_attempt(student, assignment: Assignment, answer: str, context: str,
                   diagnostic_result=None, mock_result=None) -> Attempt:
    """Create an attempt; auto-check part 1, leave part 2 for expert review."""
    is_correct = None
    if assignment.exam_part == Assignment.Part.PART1:
        is_correct = assignment.check_answer(answer)

    attempt = Attempt.objects.create(
        student=student, assignment=assignment, context=context,
        submitted_answer=answer, is_correct=is_correct,
        diagnostic_result=diagnostic_result, mock_result=mock_result,
    )
    if is_correct is not None:
        process_attempt_result(attempt)
    return attempt


def process_attempt_result(attempt: Attempt) -> None:
    """Update mastery for tagged nodes; on mistakes feed the backlog.

    Also called by expert review once a part-2 verdict arrives.
    """
    for tag in attempt.assignment.skill_tags.select_related("node"):
        update_mastery(attempt.student, tag.node, bool(attempt.is_correct), tag.weight)
        if attempt.is_correct is False:
            register_mistake(attempt.student, attempt.assignment, tag.node)


def register_mistake(student, assignment, node) -> MistakeBacklogItem:
    item = (
        MistakeBacklogItem.objects
        .filter(student=student, assignment=assignment, node=node)
        .exclude(status=MistakeBacklogItem.Status.RESOLVED)
        .first()
    )
    if item:
        item.error_count += 1
        item.save(update_fields=["error_count"])
    else:
        item = MistakeBacklogItem.objects.create(
            student=student, assignment=assignment, node=node,
            status=MistakeBacklogItem.Status.IN_REVIEW,
        )
        schedule_reviews(item)

    _maybe_reinsert_topic(student, node)
    return item


def schedule_reviews(item: MistakeBacklogItem) -> list[ReviewSchedule]:
    today = timezone.localdate()
    return [
        ReviewSchedule.objects.create(
            backlog_item=item, interval_days=days, due_date=today + timedelta(days=days)
        )
        for days in settings.REVIEW_INTERVALS_DAYS
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


def complete_review(review: ReviewSchedule, success: bool) -> None:
    review.status = ReviewSchedule.Status.COMPLETED
    review.save(update_fields=["status"])
    item = review.backlog_item
    if not success:
        # Failed a repetition: reset remaining schedule from today.
        item.reviews.filter(status=ReviewSchedule.Status.PENDING).delete()
        item.error_count += 1
        item.save(update_fields=["error_count"])
        schedule_reviews(item)
    elif not item.reviews.filter(status=ReviewSchedule.Status.PENDING).exists():
        item.status = MistakeBacklogItem.Status.RESOLVED
        item.resolved_at = timezone.now()
        item.save(update_fields=["status", "resolved_at"])


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
