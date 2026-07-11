"""Study plan building and adaptation."""
from collections import deque
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.knowledge.models import KnowledgeDependency, KnowledgeNode
from apps.knowledge.services import mastery_map

from .models import (
    PlanChangeLog,
    StudyPlan,
    StudyPlanItem,
    Trajectory,
    TrajectoryTransition,
)


def _topological_order(nodes):
    """Order nodes so prerequisites come first; ties broken by exam weight desc."""
    ids = {n.id for n in nodes}
    deps = KnowledgeDependency.objects.filter(node_id__in=ids, prerequisite_id__in=ids)
    incoming = {n.id: set() for n in nodes}
    outgoing = {n.id: set() for n in nodes}
    for d in deps:
        incoming[d.node_id].add(d.prerequisite_id)
        outgoing[d.prerequisite_id].add(d.node_id)

    by_id = {n.id: n for n in nodes}
    ready = sorted(
        (nid for nid, pre in incoming.items() if not pre),
        key=lambda nid: -(by_id[nid].weight * by_id[nid].cluster.exam_weight),
    )
    queue, result = deque(ready), []
    while queue:
        nid = queue.popleft()
        result.append(by_id[nid])
        for nxt in sorted(
            outgoing[nid],
            key=lambda x: -(by_id[x].weight * by_id[x].cluster.exam_weight),
        ):
            incoming[nxt].discard(nid)
            if not incoming[nxt]:
                queue.append(nxt)
    # Cycles shouldn't exist; append leftovers defensively.
    leftover = [n for n in nodes if n not in result]
    return result + leftover


def order_pending_nodes(student) -> list[KnowledgeNode]:
    """Неосвоенные узлы в порядке изучения (зависимости + вес в баллах).

    Используется и планировщиком, и симуляцией потолка прогноза.
    """
    masteries = mastery_map(student)
    nodes = list(KnowledgeNode.objects.select_related("cluster").all())
    pending = [n for n in nodes if masteries.get(n.id, 0) < settings.MASTERY_THRESHOLD]
    return _topological_order(pending)


def build_study_plan(student, reason: str = "initial") -> StudyPlan:
    """Build a plan from current mastery, dependencies and topic weights.

    Nodes already at/above MASTERY_THRESHOLD are skipped. Each node gets a
    lesson item and a practice item; items are spread over weeks by
    student.weekly_hours (assumption: 1 node ≈ HOURS_PER_NODE hours).
    """
    current = get_active_plan(student)
    trajectory = current.trajectory if current else None
    if trajectory is None:
        latest_transition = (
            TrajectoryTransition.objects.filter(student=student)
            .select_related("to_trajectory")
            .first()
        )
        trajectory = latest_transition.to_trajectory if latest_transition else None

    StudyPlan.objects.filter(student=student, status=StudyPlan.Status.ACTIVE).update(
        status=StudyPlan.Status.ARCHIVED
    )
    plan = StudyPlan.objects.create(
        student=student,
        target_score=student.target_score,
        trajectory=trajectory,
    )

    weekly_hours = trajectory.weekly_load_hours if trajectory else student.weekly_hours
    nodes_per_week = max(1, weekly_hours // settings.HOURS_PER_NODE)
    today = timezone.localdate()
    order = 0
    for i, node in enumerate(order_pending_nodes(student)):
        week = i // nodes_per_week
        due = today + timedelta(days=7 * week + (i % nodes_per_week))
        for item_type in (StudyPlanItem.ItemType.LESSON, StudyPlanItem.ItemType.PRACTICE):
            StudyPlanItem.objects.create(
                plan=plan, node=node, item_type=item_type,
                order=order, week_index=week, due_date=due,
            )
            order += 1
    from apps.events.models import Event
    from apps.events.services import log_event

    log_event(
        Event.Type.PLAN_REBUILT,
        student=student,
        plan_id=plan.id,
        trajectory_id=trajectory.id if trajectory else None,
        reason=reason,
        is_major=reason != "initial",
    )
    return plan


def get_active_plan(student) -> StudyPlan | None:
    return (
        StudyPlan.objects.filter(student=student, status=StudyPlan.Status.ACTIVE)
        .order_by("-created_at")
        .first()
    )


def reinsert_node(student, node, reason: str, description: str = "",
                  is_major: bool = False, in_days: int = 1) -> StudyPlanItem | None:
    """Return a topic to the active plan (frequent mistakes, poor mock, decay)."""
    plan = get_active_plan(student)
    if plan is None:
        return None
    has_pending = plan.items.filter(
        node=node, status=StudyPlanItem.Status.PENDING
    ).exists()
    if not has_pending:
        last_order = plan.items.order_by("-order").values_list("order", flat=True).first() or 0
        item = StudyPlanItem.objects.create(
            plan=plan, node=node, item_type=StudyPlanItem.ItemType.PRACTICE,
            order=last_order + 1, due_date=timezone.localdate() + timedelta(days=in_days),
        )
    else:
        item = None
    log_plan_change(
        student, reason=reason, description=description, is_major=is_major
    )
    return item


def log_plan_change(student, reason: str, description: str = "",
                    is_major: bool = False) -> PlanChangeLog | None:
    plan = get_active_plan(student)
    if plan is None:
        return None
    change = PlanChangeLog.objects.create(
        plan=plan, reason=reason, description=description, is_major=is_major
    )
    from apps.events.models import Event
    from apps.events.services import log_event

    log_event(
        Event.Type.PLAN_CHANGE_LOGGED,
        student=student,
        change_id=change.id,
        reason=reason,
        is_major=is_major,
    )
    return change


def rebuild_after_inactivity(student, idle_days: int) -> StudyPlan | None:
    """«Тебя не было N недель. Перестроил план под сжатое время.»

    Снижение прогноза показываем фактом, без упрёка. Пропускаем учеников
    без активного плана (диагностика ещё не пройдена).
    """
    from apps.progress.services import predict_score

    if get_active_plan(student) is None:
        return None
    transition = maybe_transition(
        student,
        PlanChangeLog.Reason.INACTIVITY,
        {"idle_days": idle_days},
    )
    if transition:
        return get_active_plan(student)

    plan = build_study_plan(student, reason=PlanChangeLog.Reason.INACTIVITY)
    predicted, _ = predict_score(student)
    weeks = max(1, round(idle_days / 7))
    log_plan_change(
        student,
        reason=PlanChangeLog.Reason.INACTIVITY,
        description=(
            f"Тебя не было {weeks} нед. Перестроил план под сжатое время. "
            f"При текущем темпе прогноз: {predicted}."
        ),
        is_major=True,
    )
    return plan


def _current_trajectory(student) -> Trajectory | None:
    plan = get_active_plan(student)
    if plan and plan.trajectory_id:
        return plan.trajectory
    latest = (
        TrajectoryTransition.objects.filter(student=student)
        .select_related("to_trajectory")
        .first()
    )
    return latest.to_trajectory if latest else None


def _select_trajectory(target_score: int) -> Trajectory:
    trajectories = list(Trajectory.objects.order_by("target_min"))
    if not trajectories:
        raise Trajectory.DoesNotExist("Именованные траектории ещё не настроены.")
    for trajectory in trajectories:
        if trajectory.target_min <= target_score <= trajectory.target_max:
            return trajectory
    if target_score > trajectories[-1].target_max:
        return trajectories[-1]
    return trajectories[0]


@transaction.atomic
def assign_trajectory(student, target_score: int) -> Trajectory:
    trajectory = _select_trajectory(target_score)
    current = _current_trajectory(student)
    if current and current.pk == trajectory.pk:
        plan = get_active_plan(student)
        if plan and plan.trajectory_id != trajectory.id:
            plan.trajectory = trajectory
            plan.save(update_fields=["trajectory"])
        return trajectory

    transition = TrajectoryTransition.objects.create(
        student=student,
        from_trajectory=None,
        to_trajectory=trajectory,
        reasons=["target_score"],
        recovery_actions=[],
    )
    plan = get_active_plan(student)
    if plan:
        plan.trajectory = trajectory
        plan.save(update_fields=["trajectory"])

    from apps.events.models import Event
    from apps.events.services import log_event

    log_event(
        Event.Type.TRAJECTORY_ASSIGNED,
        student=student,
        transition_id=transition.id,
        trajectory_id=trajectory.id,
        target_score=target_score,
    )
    return trajectory


def _recovery_actions(student, details: dict, trajectory: Trajectory) -> list[str]:
    node_ids = []
    for node_id in details.get("node_ids", []):
        try:
            node_ids.append(int(node_id))
        except (TypeError, ValueError):
            continue
    plan = get_active_plan(student)
    if not node_ids and plan:
        node_ids = list(
            plan.items.filter(
                status__in=[StudyPlanItem.Status.PENDING, StudyPlanItem.Status.IN_PROGRESS],
                node_id__isnull=False,
            )
            .order_by()
            .values_list("node_id", flat=True)
            .distinct()[:3]
        )
    node_ids = list(dict.fromkeys(node_ids))
    nodes_by_id = KnowledgeNode.objects.in_bulk(node_ids)
    node_titles = [
        nodes_by_id[node_id].title
        for node_id in node_ids
        if node_id in nodes_by_id
    ]
    actions = []
    if node_titles:
        quoted_titles = ", ".join(f'"{title}"' for title in node_titles)
        actions.append(f"Вернуть в план: {quoted_titles}.")
    actions.append(
        f"Пересобрать недельный план под нагрузку {trajectory.weekly_load_hours} ч."
    )
    return actions


def _transition_target(student, current: Trajectory, reason: str, details: dict):
    trajectories = list(Trajectory.objects.order_by("target_min"))
    index = next((i for i, item in enumerate(trajectories) if item.pk == current.pk), None)
    if index is None:
        return None

    should_move_down = False
    if reason == PlanChangeLog.Reason.POOR_MOCK:
        primary_score = details.get("primary_score")
        if primary_score is not None:
            target_primary = next(
                (
                    index
                    for index, scaled in enumerate(settings.PRIMARY_TO_SCALED)
                    if scaled >= current.target_min
                ),
                settings.MAX_PRIMARY_SCORE,
            )
            should_move_down = primary_score < target_primary - 5
        else:
            score = details.get(
                "scaled_score",
                details.get("score", details.get("mock_score", details.get("actual_score"))),
            )
            should_move_down = score is not None and score < current.target_min - 5
    elif reason == PlanChangeLog.Reason.FREQUENT_MISTAKES:
        error_count = details.get(
            "error_count",
            details.get("mistake_count", details.get("errors_count", 0)),
        )
        should_move_down = error_count >= settings.FREQUENT_MISTAKE_THRESHOLD
    elif reason == PlanChangeLog.Reason.INACTIVITY:
        idle_days = details.get("idle_days", details.get("days", 0))
        should_move_down = idle_days >= settings.INACTIVITY_REBUILD_DAYS

    if should_move_down and index > 0:
        return trajectories[index - 1]

    if reason == PlanChangeLog.Reason.POOR_MOCK and index < len(trajectories) - 1:
        from apps.mocks.models import MockExamResult

        recent_scores = list(
            MockExamResult.objects.filter(
                student=student,
                status=MockExamResult.Status.COMPLETED,
                scaled_score__isnull=False,
            )
            .order_by("-completed_at")
            .values_list("scaled_score", flat=True)[:2]
        )
        if len(recent_scores) == 2 and all(score > current.target_max for score in recent_scores):
            return trajectories[index + 1]
    return None


@transaction.atomic
def maybe_transition(student, reason: str, details: dict | None = None):
    details = details or {}
    current = _current_trajectory(student)
    if current is None:
        return None
    target = _transition_target(student, current, reason, details)
    if target is None or target.pk == current.pk:
        return None

    moving_down = target.target_min < current.target_min
    recovery_actions = _recovery_actions(student, details, target) if moving_down else []
    transition = TrajectoryTransition.objects.create(
        student=student,
        from_trajectory=current,
        to_trajectory=target,
        reasons=[reason],
        recovery_actions=recovery_actions,
    )
    old_plan = get_active_plan(student)
    if old_plan:
        old_plan.trajectory = target
        old_plan.save(update_fields=["trajectory"])
    build_study_plan(student, reason=reason)
    log_plan_change(
        student,
        reason=reason,
        description=(
            f"При текущем темпе траектория изменена с {current.title} на {target.title}."
        ),
        is_major=True,
    )

    from apps.events.models import Event
    from apps.events.services import log_event

    log_event(
        Event.Type.TRAJECTORY_TRANSITION,
        student=student,
        transition_id=transition.id,
        from_trajectory_id=current.id,
        to_trajectory_id=target.id,
        reason=reason,
        details=details,
        recovery_actions=recovery_actions,
    )
    return transition


def acknowledge_trajectory_transition(student, transition_id: int):
    transition = TrajectoryTransition.objects.get(pk=transition_id, student=student)
    transition.acknowledged = True
    transition.save(update_fields=["acknowledged"])
    return transition


def complete_item(item: StudyPlanItem) -> StudyPlanItem:
    item.status = StudyPlanItem.Status.DONE
    item.save(update_fields=["status"])
    return item


def items_for_period(student, start, end):
    plan = get_active_plan(student)
    if plan is None:
        return StudyPlanItem.objects.none()
    return plan.items.filter(due_date__gte=start, due_date__lte=end).select_related("node")
