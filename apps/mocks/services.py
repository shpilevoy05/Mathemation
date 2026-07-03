"""Mock exam completion: score, snapshot, plan adaptation."""
from django.utils import timezone

from apps.planning.models import PlanChangeLog
from apps.planning.services import log_plan_change, reinsert_node
from apps.progress.services import create_snapshot, predict_score, weak_topics

from .models import MockExamResult

# Predicted-vs-mock gap (scaled points) that triggers a plan adjustment.
POOR_MOCK_GAP = 10


def complete_mock_part1(result: MockExamResult) -> MockExamResult:
    """Finish auto-checked part; part 2 items may still await expert review."""
    result.primary_score = result.attempts.filter(is_correct=True).count()
    # TODO: real primary→scaled ЕГЭ conversion table; MVP uses share of max.
    total = result.attempts.count()
    result.scaled_score = round(100 * result.primary_score / total) if total else 0
    result.status = MockExamResult.Status.PART1_CHECKED
    result.completed_at = timezone.now()
    result.save()

    create_snapshot(result.student)
    _adapt_plan_after_mock(result)
    return result


def _adapt_plan_after_mock(result: MockExamResult) -> None:
    predicted, _ = predict_score(result.student)
    if result.scaled_score is not None and result.scaled_score + POOR_MOCK_GAP < predicted:
        log_plan_change(
            result.student,
            reason=PlanChangeLog.Reason.POOR_MOCK,
            description=(
                f"Пробник {result.exam.title}: {result.scaled_score} при прогнозе {predicted}. "
                "Слабые темы возвращены в план."
            ),
        )
        from apps.knowledge.models import KnowledgeNode

        for topic in weak_topics(result.student, limit=3):
            node = KnowledgeNode.objects.get(pk=topic["node_id"])
            reinsert_node(
                result.student, node,
                reason=PlanChangeLog.Reason.POOR_MOCK,
                description=f"Отработка после пробника: {node.title}",
            )
