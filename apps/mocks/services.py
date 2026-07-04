"""Mock exam completion: score, snapshot, calibration, plan adaptation."""
from django.utils import timezone

from apps.content.models import Assignment
from apps.planning.models import PlanChangeLog
from apps.planning.services import log_plan_change, reinsert_node
from apps.progress.services import (
    calibrate_forecast,
    create_snapshot,
    predict_score,
    primary_to_scaled,
    weak_topics,
)

from .models import MockExamResult

# Predicted-vs-mock gap (scaled points) that triggers a plan adjustment.
POOR_MOCK_GAP = 10
# Дней отработки, добавляемых на слабую тему после плохого пробника.
POOR_MOCK_EXTRA_DAYS = 4


def _rescore(result: MockExamResult) -> None:
    result.scaled_score = primary_to_scaled(result.total_primary_score)


def complete_mock_part1(result: MockExamResult) -> MockExamResult:
    """Finish auto-checked part; part 2 items may still await expert review."""
    result.primary_score = result.attempts.filter(is_correct=True).count()
    _rescore(result)
    has_part2 = result.exam.assignments.filter(exam_part=Assignment.Part.PART2).exists()
    result.status = (
        MockExamResult.Status.PART1_CHECKED if has_part2 else MockExamResult.Status.COMPLETED
    )
    result.completed_at = timezone.now()
    result.save()

    if result.status == MockExamResult.Status.COMPLETED:
        _finalize(result)
    else:
        # Пока вторая часть у эксперта, балл неполный: снапшот без калибровки
        # и без адаптации плана — они произойдут в maybe_complete_mock().
        create_snapshot(result.student)
    return result


def maybe_complete_mock(result: MockExamResult) -> MockExamResult:
    """Пересчитать итог, когда эксперт закрыл очередную работу второй части."""
    reviews = result.expert_reviews.all()
    result.part2_primary_score = sum(r.total_score or 0 for r in reviews)
    _rescore(result)

    part2_count = result.exam.assignments.filter(exam_part=Assignment.Part.PART2).count()
    reviewed = reviews.filter(reviewed_at__isnull=False).count()
    all_done = part2_count and reviewed >= part2_count
    if all_done and result.status == MockExamResult.Status.PART1_CHECKED:
        result.status = MockExamResult.Status.COMPLETED
        result.save()
        _finalize(result)
    else:
        result.save()
    return result


def _finalize(result: MockExamResult) -> None:
    """Пробник — механизм пересчёта траектории: калибровка, снапшот, план."""
    calibrate_forecast(result.student, result.scaled_score or 0)
    create_snapshot(result.student)
    _adapt_plan_after_mock(result)


def _adapt_plan_after_mock(result: MockExamResult) -> None:
    predicted, _ = predict_score(result.student)
    if result.scaled_score is not None and result.scaled_score + POOR_MOCK_GAP < predicted:
        from apps.knowledge.models import KnowledgeNode

        weakest = weak_topics(result.student, limit=3)
        titles = ", ".join(t["title"] for t in weakest)
        log_plan_change(
            result.student,
            reason=PlanChangeLog.Reason.POOR_MOCK,
            description=(
                f"Пробник «{result.exam.title}» показал слабые темы: {titles}. "
                f"Добавил {POOR_MOCK_EXTRA_DAYS} дня на отработку, "
                f"потолок уточнён: {predicted}."
            ),
            is_major=True,
        )
        for topic in weakest:
            node = KnowledgeNode.objects.get(pk=topic["node_id"])
            reinsert_node(
                result.student, node,
                reason=PlanChangeLog.Reason.POOR_MOCK,
                description=f"Отработка после пробника: {node.title}",
                in_days=POOR_MOCK_EXTRA_DAYS,
            )
