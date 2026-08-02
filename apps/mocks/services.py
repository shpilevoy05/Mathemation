"""Mock exam completion: score, snapshot, calibration, plan adaptation."""
from django.utils import timezone

from apps.content.models import Assignment
from apps.planning.models import PlanChangeLog
from apps.planning.services import log_plan_change, maybe_transition, reinsert_node
from apps.progress.services import (
    calibrate_forecast,
    create_snapshot,
    predict_score,
    primary_to_scaled,
    weak_topics,
)

from .models import MockExam, MockExamResult

# Predicted-vs-mock gap (scaled points) that triggers a plan adjustment.
POOR_MOCK_GAP = 10
# Дней отработки, добавляемых на слабую тему после плохого пробника.
POOR_MOCK_EXTRA_DAYS = 4


class MockDeadlineExpired(Exception):
    """The server-side exam deadline has passed."""


def start_mock(student, exam: MockExam) -> MockExamResult:
    result = MockExamResult.objects.create(student=student, exam=exam)
    from apps.events.models import Event
    from apps.events.services import log_event

    log_event(
        Event.Type.MOCK_STARTED,
        student=student,
        exam_id=exam.id,
        result_id=result.id,
    )
    return result


def _rescore(result: MockExamResult) -> None:
    result.scaled_score = primary_to_scaled(result.total_primary_score)


def complete_mock_part1(result: MockExamResult) -> MockExamResult:
    """Finish auto-checked part; part 2 items may still await expert review."""
    result.primary_score = result.attempts.filter(is_correct=True).count()
    _rescore(result)
    # Ждать эксперта имеет смысл только по тем работам, которые ученик реально
    # загрузил: пропущенная задача второй части — это ноль, как на экзамене, а
    # не повод держать пробник незавершённым вечно.
    awaits_expert = result.expert_reviews.exists()
    result.status = (
        MockExamResult.Status.PART1_CHECKED if awaits_expert
        else MockExamResult.Status.COMPLETED
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


def submit_mock(result: MockExamResult, answers: dict) -> MockExamResult:
    """Validate the server deadline, record part 1 and close its automatic check."""
    if timezone.now() > result.deadline:
        result.time_expired = True
        result.save(update_fields=["time_expired"])
        raise MockDeadlineExpired("Время пробника истекло. Ответы не приняты.")
    if result.status != MockExamResult.Status.IN_PROGRESS:
        raise ValueError("Пробник уже отправлен.")

    from apps.practice.models import Attempt
    from apps.practice.services import submit_attempt

    for assignment in result.exam.assignments.filter(exam_part=Assignment.Part.PART1):
        submit_attempt(
            result.student,
            assignment,
            str(answers.get(str(assignment.id), "")),
            context=Attempt.Context.MOCK,
            mock_result=result,
        )
    return complete_mock_part1(result)


def maybe_complete_mock(result: MockExamResult) -> MockExamResult:
    """Пересчитать итог, когда эксперт закрыл очередную работу второй части."""
    reviews = result.expert_reviews.all()
    result.part2_primary_score = sum(r.total_score or 0 for r in reviews)
    _rescore(result)

    submitted = reviews.count()
    reviewed = reviews.filter(reviewed_at__isnull=False).count()
    all_done = submitted and reviewed >= submitted
    if all_done and result.status == MockExamResult.Status.PART1_CHECKED:
        result.status = MockExamResult.Status.COMPLETED
        result.save()
        _finalize(result)
    else:
        result.save()
    return result


def _finalize(result: MockExamResult) -> None:
    """Пробник — механизм пересчёта траектории: калибровка, снапшот, план."""
    # Калибруем в первичных баллах: это то, что реально измерил пробник.
    calibrate_forecast(result.student, result.total_primary_score, mock_result=result)
    create_snapshot(result.student)
    weakest = weak_topics(result.student, limit=3)
    maybe_transition(
        result.student,
        PlanChangeLog.Reason.POOR_MOCK,
        {
            "scaled_score": result.scaled_score,
            "primary_score": result.total_primary_score,
            "node_ids": [topic["node_id"] for topic in weakest],
        },
    )
    _adapt_plan_after_mock(result)
    from apps.events.models import Event
    from apps.events.services import log_event

    log_event(
        Event.Type.MOCK_SUBMITTED,
        student=result.student,
        exam_id=result.exam_id,
        result_id=result.id,
        primary_score=result.primary_score,
        part2_primary_score=result.part2_primary_score,
        total_primary_score=result.total_primary_score,
        scaled_score=result.scaled_score,
    )


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
