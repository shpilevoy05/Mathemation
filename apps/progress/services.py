"""Forecast (текущий балл + потолок с рычагами), snapshots, weekly reports."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from apps.engine.ceiling import simulate_ceiling
from apps.engine.dto import EdgeDTO, EngineParams, NodeState, TaskWeight
from apps.engine.forecast import expected_primary as engine_expected_primary
from apps.engine.forecast import scaled_score
from apps.content.models import Assignment
from apps.knowledge.models import KnowledgeNode, SkillMastery
from apps.knowledge.models import KnowledgeDependency
from apps.planning.models import StudyPlanItem
from apps.planning.services import get_active_plan
from apps.practice.models import Attempt, MistakeBacklogItem

from .models import ParentReport, ProgressSnapshot

WEAK_TOPIC_LIMIT = 5


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


def _forecast_dtos(
    student, mastery_override: dict[int, float] | None = None
) -> tuple[list[NodeState], list[TaskWeight]]:
    nodes = list(KnowledgeNode.objects.select_related("cluster").all())
    masteries = mastery_override if mastery_override is not None else dict(
        SkillMastery.objects.filter(student=student).values_list("node_id", "mastery")
    )
    practiced_at = dict(
        SkillMastery.objects.filter(student=student).values_list(
            "node_id", "last_practiced_at"
        )
    )
    states = [
        NodeState(
            node_id=node.id,
            mastery=float(masteries.get(node.id, 0.0)),
            last_practiced_at=practiced_at.get(node.id),
            weight=float(node.weight),
            cluster_weight=float(node.cluster.exam_weight),
        )
        for node in nodes
    ]
    assignments = list(
        Assignment.objects.filter(skill_tags__node_id__in=[node.id for node in nodes])
        .prefetch_related("skill_tags")
        .distinct()
    )
    weights = []
    for assignment in assignments:
        tags = list(assignment.skill_tags.all())
        weights.append(
            TaskWeight(
                assignment_id=assignment.id,
                node_ids=tuple(tag.node_id for tag in tags),
                node_weights=tuple(float(tag.weight) for tag in tags),
                max_score=float(assignment.max_score),
                difficulty=float(assignment.difficulty),
                discrimination=settings.IRT_DEFAULT_DISCRIMINATION,
            )
        )
    # Empty content databases still get a deterministic node-based bootstrap.
    if not weights:
        weights = [
            TaskWeight(
                assignment_id=node.id,
                node_ids=(node.id,),
                max_score=float(node.weight * node.cluster.exam_weight),
                difficulty=3.0,
            )
            for node in nodes
        ]
    return states, weights


def primary_to_scaled(primary: float) -> int:
    """Перевод первичных баллов в тестовые по таблице (конфиг на каждый год)."""
    return scaled_score(primary, settings.PRIMARY_TO_SCALED)


def expected_primary(student, mastery_override: dict[int, float] | None = None) -> float:
    """Ожидаемый первичный балл: взвешенное среднее mastery → доля от максимума.

    TODO: заменить на Σ P(верно | mastery, IRT-сложность) по профилю экзамена,
    когда накопятся реальные логи попыток.
    """
    states, weights = _forecast_dtos(student, mastery_override)
    return engine_expected_primary(states, weights, _engine_params())


def predict_score(student, mastery_override: dict[int, float] | None = None) -> tuple[int, float]:
    """(прогнозный тестовый балл с калибровкой, средний взвешенный mastery)."""
    primary = expected_primary(student, mastery_override)
    scaled = primary_to_scaled(primary) + student.forecast_calibration
    avg = primary / settings.MAX_PRIMARY_SCORE * 100
    return int(min(max(round(scaled), 0), 100)), round(avg, 2)


def calibrate_forecast(student, actual_scaled: int) -> None:
    """После пробника сверяем предсказание с фактом и подтягиваем модель."""
    raw_predicted = primary_to_scaled(expected_primary(student))
    error = actual_scaled - raw_predicted
    student.forecast_calibration = round(
        (1 - settings.FORECAST_CALIBRATION_ALPHA) * student.forecast_calibration
        + settings.FORECAST_CALIBRATION_ALPHA * error,
        2,
    )
    student.save(update_fields=["forecast_calibration"])


def ceiling_forecast(student, weekly_hours: int | None = None, exam_date=None) -> dict:
    """Потолок: чего реально достичь к экзамену при заданном темпе.

    Рычаги «поиграть ползунком» = вызов с другими weekly_hours / exam_date.
    Возвращает потолочный балл и списки достижимых/недостижимых узлов —
    последние подсвечиваются на карте оверлеем «что реально успеешь».
    """
    weekly_hours = weekly_hours or student.weekly_hours
    exam_date = exam_date or student.exam_date
    current_score, _ = predict_score(student)

    states, _ = _forecast_dtos(student)
    edges = [
        EdgeDTO(
            from_node_id=dependency.prerequisite_id,
            to_node_id=dependency.node_id,
            min_mastery=float(dependency.min_mastery),
        )
        for dependency in KnowledgeDependency.objects.all()
    ]
    days_left = (
        None
        if exam_date is None
        else max((exam_date - timezone.localdate()).days, 0)
    )
    result = simulate_ceiling(states, edges, days_left, weekly_hours, _engine_params())
    ceiling_score, _ = predict_score(student, mastery_override=result.mastery_profile)

    return {
        "current_score": current_score,
        "ceiling_score": max(ceiling_score, current_score),
        "weekly_hours": weekly_hours,
        "exam_date": exam_date,
        "reachable_node_ids": list(result.reachable_node_ids),
        "unreachable_node_ids": list(result.unreachable_node_ids),
    }


def weak_topics(student, limit=WEAK_TOPIC_LIMIT) -> list[dict]:
    masteries = dict(
        SkillMastery.objects.filter(student=student).values_list("node_id", "mastery")
    )
    nodes = KnowledgeNode.objects.select_related("cluster").all()
    ranked = sorted(nodes, key=lambda n: masteries.get(n.id, 0))[:limit]
    return [
        {
            "node_id": n.id,
            "code": n.code,
            "title": n.title,
            "cluster": n.cluster.title,
            "mastery": masteries.get(n.id, 0),
        }
        for n in ranked
    ]


def create_snapshot(student) -> ProgressSnapshot:
    """Recalculated after each mock exam / diagnostic."""
    predicted, avg = predict_score(student)
    return ProgressSnapshot.objects.create(
        student=student,
        start_score=student.start_score,
        predicted_score=predicted,
        target_score=student.target_score,
        average_mastery=avg,
        weak_topics=weak_topics(student),
    )


def build_parent_report(student, week_start=None) -> ParentReport:
    """Weekly pulse: факт недели, динамика, риски, слабые темы, следующий шаг."""
    today = timezone.localdate()
    week_start = week_start or today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)

    attempts = Attempt.objects.filter(
        student=student, created_at__date__gte=week_start, created_at__date__lt=week_end
    )
    solved = attempts.filter(is_correct=True).count()
    total = attempts.count()

    from apps.ai_mentor.models import AiHintMessage

    hints_used = AiHintMessage.objects.filter(
        session__student=student,
        role=AiHintMessage.Role.MENTOR,
        is_blocked=False,
        created_at__date__gte=week_start, created_at__date__lt=week_end,
    ).count()

    from apps.mocks.models import MockExamResult

    mocks_completed = MockExamResult.objects.filter(
        student=student,
        completed_at__date__gte=week_start,
        completed_at__date__lt=week_end,
    ).count()

    snapshots = list(
        ProgressSnapshot.objects.filter(student=student).order_by("-created_at")[:8]
    )
    scores = [snapshot.predicted_score for snapshot in reversed(snapshots)]
    current = scores[-1] if scores else None
    previous = scores[-2] if len(scores) > 1 else None
    delta = (scores[-1] - scores[0]) if len(scores) > 1 else None
    if len(scores) == 1:
        sparkline_points = "50,20"
        sparkline_last_x, sparkline_last_y = 50, 20
    elif scores:
        low, high = min(scores), max(scores)
        score_range = high - low
        points = [
            (
                round(index * 100 / (len(scores) - 1), 1),
                round(20 if not score_range else 40 - (score - low) * 40 / score_range, 1),
            )
            for index, score in enumerate(scores)
        ]
        sparkline_points = " ".join(f"{x},{y}" for x, y in points)
        sparkline_last_x, sparkline_last_y = points[-1]
    else:
        sparkline_points = ""
        sparkline_last_x, sparkline_last_y = None, None

    open_mistakes = (
        MistakeBacklogItem.objects.filter(student=student)
        .exclude(status=MistakeBacklogItem.Status.RESOLVED)
        .count()
    )
    error_type_distribution = {
        row["error_type"]: row["total"]
        for row in (
            MistakeBacklogItem.objects.filter(student=student)
            .exclude(status=MistakeBacklogItem.Status.RESOLVED)
            .values("error_type")
            .annotate(total=Sum("error_count"))
        )
    }
    plan = get_active_plan(student)
    overdue = (
        plan.items.filter(
            status=StudyPlanItem.Status.PENDING, due_date__lt=today
        ).count()
        if plan
        else 0
    )

    risks = []
    if total == 0:
        risks.append("На этой неделе не было активности.")
    if overdue:
        risks.append(f"Просрочено пунктов плана: {overdue}.")
    if open_mistakes >= 5:
        risks.append(f"Накопилось ошибок на отработку: {open_mistakes}.")

    next_item = (
        plan.items.filter(status=StudyPlanItem.Status.PENDING)
        .select_related("node")
        .first()
        if plan
        else None
    )
    next_step = (
        f"{next_item.get_item_type_display()}: {next_item.node.title}"
        if next_item and next_item.node
        else "Пройти входную диагностику."
    )

    payload = {
        "week_fact": {
            "attempts": total,
            "solved": solved,
            "hints_used": hints_used,
            "mocks_completed": mocks_completed,
            "plan_items_done": (
                plan.items.filter(
                    status=StudyPlanItem.Status.DONE,
                    due_date__gte=week_start, due_date__lt=week_end,
                ).count()
                if plan
                else 0
            ),
        },
        "dynamics": {
            "current_predicted_score": current,
            "previous_predicted_score": previous,
            "delta": delta,
            "sparkline_points": sparkline_points,
            "sparkline_last_x": sparkline_last_x,
            "sparkline_last_y": sparkline_last_y,
            "start_score": student.start_score,
            "target_score": student.target_score,
        },
        "risks": risks,
        "weak_topics": weak_topics(student),
        "error_type_distribution": error_type_distribution,
        "next_step": next_step,
    }
    report, _ = ParentReport.objects.update_or_create(
        student=student, week_start=week_start, defaults={"payload": payload}
    )
    return report
