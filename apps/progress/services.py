"""Forecast (текущий балл + потолок с рычагами), snapshots, weekly reports."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from apps.knowledge.models import KnowledgeNode, SkillMastery
from apps.planning.models import StudyPlanItem
from apps.planning.services import get_active_plan
from apps.practice.models import Attempt, MistakeBacklogItem

from .models import ParentReport, ProgressSnapshot

WEAK_TOPIC_LIMIT = 5
# EMA-вес свежего пробника при калибровке прогноза.
CALIBRATION_ALPHA = 0.3


def primary_to_scaled(primary: float) -> int:
    """Перевод первичных баллов в тестовые по таблице (конфиг на каждый год)."""
    table = settings.PRIMARY_TO_SCALED
    idx = min(max(int(round(primary)), 0), len(table) - 1)
    return table[idx]


def expected_primary(student, mastery_override: dict[int, float] | None = None) -> float:
    """Ожидаемый первичный балл: взвешенное среднее mastery → доля от максимума.

    TODO: заменить на Σ P(верно | mastery, IRT-сложность) по профилю экзамена,
    когда накопятся реальные логи попыток.
    """
    nodes = list(KnowledgeNode.objects.select_related("cluster").all())
    if not nodes:
        return 0.0
    masteries = mastery_override if mastery_override is not None else dict(
        SkillMastery.objects.filter(student=student).values_list("node_id", "mastery")
    )
    total_w = sum(n.weight * n.cluster.exam_weight for n in nodes)
    if not total_w:
        return 0.0
    weighted = sum(
        masteries.get(n.id, 0) * n.weight * n.cluster.exam_weight for n in nodes
    )
    return (weighted / total_w) / 100 * settings.MAX_PRIMARY_SCORE


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
        (1 - CALIBRATION_ALPHA) * student.forecast_calibration + CALIBRATION_ALPHA * error, 2
    )
    student.save(update_fields=["forecast_calibration"])


def ceiling_forecast(student, weekly_hours: int | None = None, exam_date=None) -> dict:
    """Потолок: чего реально достичь к экзамену при заданном темпе.

    Рычаги «поиграть ползунком» = вызов с другими weekly_hours / exam_date.
    Возвращает потолочный балл и списки достижимых/недостижимых узлов —
    последние подсвечиваются на карте оверлеем «что реально успеешь».
    """
    from apps.planning.services import order_pending_nodes

    weekly_hours = weekly_hours or student.weekly_hours
    exam_date = exam_date or student.exam_date
    current_score, _ = predict_score(student)

    masteries = dict(
        SkillMastery.objects.filter(student=student).values_list("node_id", "mastery")
    )
    pending = order_pending_nodes(student)

    if exam_date is None:
        reachable = [n.id for n in pending]
        unreachable: list[int] = []
    else:
        days_left = max((exam_date - timezone.localdate()).days, 0)
        budget_hours = days_left / 7 * weekly_hours
        can_take = int(budget_hours // settings.HOURS_PER_NODE)
        reachable = [n.id for n in pending[:can_take]]
        unreachable = [n.id for n in pending[can_take:]]

    simulated = dict(masteries)
    for node_id in reachable:
        simulated[node_id] = max(
            simulated.get(node_id, 0), float(settings.ATTAINABLE_MASTERY)
        )
    ceiling_score, _ = predict_score(student, mastery_override=simulated)

    return {
        "current_score": current_score,
        "ceiling_score": max(ceiling_score, current_score),
        "weekly_hours": weekly_hours,
        "exam_date": exam_date,
        "reachable_node_ids": reachable,
        "unreachable_node_ids": unreachable,
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
        session__student=student, role=AiHintMessage.Role.MENTOR,
        created_at__date__gte=week_start, created_at__date__lt=week_end,
    ).count()

    from apps.mocks.models import MockExamResult

    mocks_completed = MockExamResult.objects.filter(
        student=student,
        completed_at__date__gte=week_start,
        completed_at__date__lt=week_end,
    ).count()

    snapshots = list(
        ProgressSnapshot.objects.filter(student=student).order_by("-created_at")[:2]
    )
    current = snapshots[0].predicted_score if snapshots else None
    previous = snapshots[1].predicted_score if len(snapshots) > 1 else None
    delta = (current - previous) if current is not None and previous is not None else None

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
