"""Mock exam completion: score, snapshot, calibration, plan adaptation."""
from django.db import transaction
from django.utils import timezone
from django.db import transaction

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


@transaction.atomic
def save_mock_exam(exam: MockExam, *, title, is_active, duration_minutes,
                   add_assignments=()):
    exam.title = title
    exam.is_active = is_active
    exam.duration_minutes = duration_minutes
    exam.full_clean()
    exam.save()
    if add_assignments:
        exam.assignments.add(*add_assignments)
    return exam


def remove_mock_assignment(exam: MockExam, assignment) -> None:
    exam.assignments.remove(assignment)

# Predicted-vs-mock gap (scaled points) that triggers a plan adjustment.
POOR_MOCK_GAP = 10
# Дней отработки, добавляемых на слабую тему после плохого пробника.
POOR_MOCK_EXTRA_DAYS = 4


class MockDeadlineExpired(Exception):
    """The server-side exam deadline has passed."""


def forecast_snapshot(student):
    from dataclasses import asdict
    from django.conf import settings
    from apps.knowledge.models import SkillMastery
    from apps.progress.services import expected_primary, _engine_params, active_exam_profile
    profile = active_exam_profile()
    raw = expected_primary(student)
    return {
        "raw_primary": raw,
        "calibrated_primary": raw + student.primary_calibration,
        "calibration": student.primary_calibration,
        "engine_version": "ema-irt-v1",
        "params": asdict(_engine_params(profile)),
        "profile_id": profile.pk if profile else None,
        "year": profile.year if profile else None,
        "primary_to_scaled": list(profile.primary_to_scaled if profile else settings.PRIMARY_TO_SCALED),
        "mastery": list(SkillMastery.objects.filter(student=student).values("node_id", "mastery")),
    }


@transaction.atomic
def start_mock(student, exam: MockExam) -> MockExamResult:
    result = MockExamResult.objects.create(student=student, exam=exam, forecast_at_start=forecast_snapshot(student))
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
    from apps.engine.forecast import scaled_score
    table = result.forecast_at_start.get("primary_to_scaled")
    result.scaled_score = scaled_score(result.total_primary_score, table) if table else primary_to_scaled(result.total_primary_score)


def complete_mock_part1(result: MockExamResult) -> MockExamResult:
    """Finish auto-checked part; part 2 items may still await expert review."""
    result.expert_reviews.filter(status="draft").update(status="submitted")
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


def validate_answers(result, answers):
    if not isinstance(answers, dict):
        raise ValueError("Ответы должны быть объектом.")
    allowed = {str(pk) for pk in result.exam.assignments.filter(exam_part=1).values_list("pk", flat=True)}
    if any(key not in allowed or not isinstance(value, str) or len(value) > 500 for key, value in answers.items()):
        raise ValueError("Неизвестная задача или недопустимая запись ответа.")
    return answers


@transaction.atomic
def save_draft(result, answers, revision=None):
    caller = result
    result = MockExamResult.objects.select_for_update().get(pk=result.pk)
    if result.status != MockExamResult.Status.IN_PROGRESS or timezone.now() >= result.deadline:
        raise MockDeadlineExpired("Приём изменений завершён. Сохранённые ответы будут проверены.")
    if revision is not None and revision != result.draft_revision:
        raise MockDeadlineExpired("Черновик изменён в другой вкладке. Обновите страницу.")
    result.draft_answers = {**result.draft_answers, **validate_answers(result, answers)}
    result.draft_saved_at = timezone.now()
    result.draft_revision += 1
    result.save(update_fields=["draft_answers", "draft_saved_at", "draft_revision"])
    caller.refresh_from_db()
    return caller


@transaction.atomic
def submit_mock(result: MockExamResult, answers: dict) -> MockExamResult:
    """Validate the server deadline, record part 1 and close its automatic check."""
    caller = result
    result = MockExamResult.objects.select_for_update().get(pk=result.pk)
    if result.status != MockExamResult.Status.IN_PROGRESS:
        caller.refresh_from_db()
        return caller
    result.time_expired = timezone.now() >= result.deadline
    if not result.time_expired:
        result.draft_answers = {**result.draft_answers, **validate_answers(result, answers)}
    answers = result.draft_answers
    # Older in-progress rows have no start snapshot; capture before processing
    # any answers, never after learning from this submission.
    if not result.forecast_at_start:
        result.forecast_at_start = forecast_snapshot(result.student)
    result.save(update_fields=["time_expired", "draft_answers", "forecast_at_start"])

    from apps.practice.models import Attempt
    from apps.practice.services import submit_attempt

    for assignment in result.exam.assignments.filter(exam_part=Assignment.Part.PART1):
        submit_attempt(
            result.student,
            assignment,
            str(answers.get(str(assignment.id), "")),
            context=Attempt.Context.MOCK,
            mock_result=result,
            # На пробнике условия экзаменационные: нечитаемый ответ не
            # переспрашивают, он просто не приносит балла.
            strict=False,
        )
    complete_mock_part1(result)
    caller.refresh_from_db()
    return caller


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
    snapshot = result.forecast_at_start
    table = snapshot.get("primary_to_scaled") if snapshot else None
    if table and "calibrated_primary" in snapshot:
        from apps.engine.forecast import scaled_score
        predicted = scaled_score(snapshot["calibrated_primary"], table)
    else:
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
