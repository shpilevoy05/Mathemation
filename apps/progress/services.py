"""Forecast, progress snapshots and weekly parent reports."""
from datetime import timedelta

from django.utils import timezone

from apps.knowledge.models import KnowledgeNode, SkillMastery
from apps.planning.models import StudyPlanItem
from apps.planning.services import get_active_plan
from apps.practice.models import Attempt, MistakeBacklogItem

from .models import ParentReport, ProgressSnapshot

WEAK_TOPIC_LIMIT = 5


def predict_score(student) -> tuple[int, float]:
    """Naive forecast: exam-weighted average mastery mapped onto 0-100.

    TODO: replace with a calibrated primary→scaled score model once real
    mock-exam data is available.
    """
    nodes = list(KnowledgeNode.objects.select_related("cluster").all())
    if not nodes:
        return 0, 0.0
    masteries = dict(
        SkillMastery.objects.filter(student=student).values_list("node_id", "mastery")
    )
    total_w = sum(n.weight * n.cluster.exam_weight for n in nodes)
    weighted = sum(
        masteries.get(n.id, 0) * n.weight * n.cluster.exam_weight for n in nodes
    )
    avg = weighted / total_w if total_w else 0.0
    return round(avg), round(avg, 2)


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
        "next_step": next_step,
    }
    report, _ = ParentReport.objects.update_or_create(
        student=student, week_start=week_start, defaults={"payload": payload}
    )
    return report
