"""Study plan building and adaptation."""
from datetime import timedelta
from math import ceil

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.content.models import Assignment
from apps.engine.dto import EdgeDTO, EngineParams, NodeState, TaskWeight
from apps.engine.planner import greedy_plan, topological_order
from apps.knowledge.models import KnowledgeDependency, KnowledgeNode
from apps.knowledge.services import mastery_map

from .models import (
    PlanChangeLog,
    StudyPlan,
    StudyPlanItem,
    Trajectory,
    TrajectoryTransition,
)


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


def _graph_edges(ids: set[int]) -> list[EdgeDTO]:
    """Рёбра для движка — только обязательные.

    Поддерживающая связь объясняет порядок, но не закрывает тему; если отдать
    её движку как зависимость, план начнёт ждать освоения того, без чего тема
    решается.
    """
    return [
        EdgeDTO(
            from_node_id=dependency.prerequisite_id,
            to_node_id=dependency.node_id,
            min_mastery=float(dependency.min_mastery),
        )
        for dependency in KnowledgeDependency.objects.filter(
            node_id__in=ids,
            prerequisite_id__in=ids,
            kind=KnowledgeDependency.Kind.PREREQUISITE,
        )
    ]


def _planned_nodes():
    """Узлы, которые вообще могут попасть в план.

    Папка складывается из детей и своей практики не имеет: занятия по ней не
    существует, и в расписании она была бы пустым пунктом.
    """
    return KnowledgeNode.objects.exclude(node_type=KnowledgeNode.NodeType.GROUP)


def _node_dto(node, mastery: float = 0.0) -> NodeState:
    return NodeState(
        node_id=node.id,
        mastery=float(mastery),
        last_practiced_at=None,
        weight=float(node.weight),
        cluster_weight=float(node.cluster.exam_weight),
        hours=float(node.effective_hours),
    )


def _topological_order(nodes):
    """Order nodes so prerequisites come first; ties broken by exam weight desc."""
    by_id = {n.id: n for n in nodes}
    ids = set(by_id)
    ordered = topological_order([_node_dto(node) for node in nodes], _graph_edges(ids))
    return [by_id[state.node_id] for state in ordered]


def order_pending_nodes(student) -> list[KnowledgeNode]:
    """Неосвоенные узлы в порядке изучения (зависимости + вес в баллах).

    Используется и планировщиком, и симуляцией потолка прогноза.
    """
    masteries = mastery_map(student)
    nodes = list(_planned_nodes().select_related("cluster"))
    ids = {node.id for node in nodes}
    edges = _graph_edges(ids)
    by_id = {node.id: node for node in nodes}
    states = [_node_dto(node, masteries.get(node.id, 0.0)) for node in nodes]
    assignments = list(
        Assignment.objects.filter(skill_tags__node_id__in=ids)
        .prefetch_related("skill_tags")
        .distinct()
    )
    task_weights = []
    for assignment in assignments:
        tags = list(assignment.skill_tags.all())
        task_weights.append(
            TaskWeight(
                assignment_id=assignment.id,
                node_ids=tuple(tag.node_id for tag in tags),
                node_weights=tuple(float(tag.weight) for tag in tags),
                max_score=float(assignment.max_score),
                difficulty=float(assignment.difficulty),
                discrimination=settings.IRT_DEFAULT_DISCRIMINATION,
            )
        )
    if not task_weights:
        task_weights = [
            TaskWeight(
                assignment_id=node.id,
                node_ids=(node.id,),
                max_score=float(node.weight * node.cluster.exam_weight),
                difficulty=3.0,
            )
            for node in nodes
        ]
    ordered = greedy_plan(states, edges, task_weights, _engine_params())
    return [by_id[state.node_id] for state in ordered]


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

    _fill_plan_items(student, plan, trajectory)
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


def _weekly_hours(student, trajectory) -> int:
    return trajectory.weekly_load_hours if trajectory else student.weekly_hours


def _fill_plan_items(student, plan: StudyPlan, trajectory, *, done_pairs=None) -> int:
    """Разложить темы по дням: сначала выгодные, дальше — по бюджету часов.

    Бюджет считается в часах, а не в темах: узел на четыре часа не должен
    занимать столько же места в неделе, сколько узел на два. Если до экзамена
    времени меньше, чем нужно плану, дни сжимаются — лучше показать честно
    плотный график, чем расписание, уходящее за дату экзамена.
    """
    weekly_hours = max(1, _weekly_hours(student, trajectory))
    today = timezone.localdate()
    nodes = order_pending_nodes(student)
    done_pairs = done_pairs or set()
    # Уже закрытые пункты не возвращаем: исключаем пару «тема + тип пункта», а
    # не тему целиком — закрытый урок не отменяет практику по той же теме.
    nodes = [
        node for node in nodes
        if any(
            (node.id, item_type) not in done_pairs
            for item_type in (StudyPlanItem.ItemType.LESSON, StudyPlanItem.ItemType.PRACTICE)
        )
    ]
    if not nodes:
        return 0

    total_hours = sum(_node_hours(node) for node in nodes)
    weeks_needed = max(1, ceil(total_hours / weekly_hours))
    weeks_left = None
    if student.exam_date:
        weeks_left = max(1, ceil((student.exam_date - today).days / 7))
    # Сжатие: если недель до экзамена меньше, чем требует бюджет, кладём тот же
    # объём в оставшиеся недели.
    weeks = min(weeks_needed, weeks_left) if weeks_left else weeks_needed
    hours_per_week = total_hours / weeks if weeks else float(weekly_hours)

    order = 0
    week = 0
    hours_in_week = 0.0
    day_in_week = 0
    for node in nodes:
        node_hours = _node_hours(node)
        if hours_in_week and hours_in_week + node_hours > hours_per_week:
            week += 1
            hours_in_week = 0.0
            day_in_week = 0
        due = today + timedelta(days=7 * week + min(day_in_week, 6))
        if student.exam_date and due > student.exam_date:
            due = student.exam_date
        for item_type in (StudyPlanItem.ItemType.LESSON, StudyPlanItem.ItemType.PRACTICE):
            if (node.id, item_type) in done_pairs:
                continue
            StudyPlanItem.objects.create(
                plan=plan, node=node, item_type=item_type,
                order=order, week_index=week, due_date=due,
            )
            order += 1
        hours_in_week += node_hours
        day_in_week += 1
    return order


def _node_hours(node) -> float:
    """Часы на тему: собственная оценка узла, иначе дефолт по части экзамена."""
    hours = getattr(node, "effective_hours", None)
    if hours:
        return float(hours)
    return float(
        settings.HOURS_PER_NODE_BY_PART.get(node.exam_part, settings.HOURS_PER_NODE)
    )


@transaction.atomic
def reprioritize_plan(student) -> StudyPlan | None:
    """Пересобрать очередь активного плана под текущее освоение.

    План строится один раз по событию, но ученик растёт каждый день: закрытая
    тема меняет и пороги пререквизитов, и выгоду остальных тем. Без переоценки
    остаток плана остаётся в приоритете, посчитанном на старых данных, — это
    прямо противоречит обещанию «быстрее к баллу».

    Сделанное не трогаем: закрытые пункты остаются в плане как история, а
    пересобирается только незакрытая часть.
    """
    plan = get_active_plan(student)
    if plan is None:
        return None

    done_items = list(plan.items.filter(status=StudyPlanItem.Status.DONE))
    done_pairs = {
        (item.node_id, item.item_type) for item in done_items if item.node_id
    }
    before = list(
        plan.items.exclude(status=StudyPlanItem.Status.DONE)
        .order_by("order")
        .values_list("node_id", "item_type")
    )

    plan.items.exclude(status=StudyPlanItem.Status.DONE).delete()
    # Закрытые пункты уходят в начало очереди: они уже история, и новая
    # нумерация не должна их перемешивать с актуальными.
    for index, item in enumerate(sorted(done_items, key=lambda entry: entry.order)):
        if item.order != index:
            item.order = index
            item.save(update_fields=["order"])
    trajectory = plan.trajectory
    created = _fill_plan_items(student, plan, trajectory, done_pairs=done_pairs)
    if created:
        StudyPlanItem.objects.filter(
            plan=plan, status=StudyPlanItem.Status.PENDING
        ).update(order=models.F("order") + len(done_items))

    after = list(
        plan.items.exclude(status=StudyPlanItem.Status.DONE)
        .order_by("order")
        .values_list("node_id", "item_type")
    )
    if before != after:
        from apps.events.models import Event
        from apps.events.services import log_event

        log_event(
            Event.Type.PLAN_REBUILT,
            student=student,
            plan_id=plan.id,
            reason="reprioritized",
            is_major=False,
            items=len(after),
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
        # Возвращённая тема — самое срочное, что есть в плане: её срок «завтра».
        # Раньше она получала последний порядковый номер и уезжала в конец
        # списка, то есть срок и порядок противоречили друг другу.
        first_pending = (
            plan.items.filter(status=StudyPlanItem.Status.PENDING)
            .order_by("order")
            .values_list("order", flat=True)
            .first()
        )
        order = (first_pending if first_pending is not None else 0)
        plan.items.filter(
            status=StudyPlanItem.Status.PENDING, order__gte=order
        ).update(order=models.F("order") + 1)
        item = StudyPlanItem.objects.create(
            plan=plan, node=node, item_type=StudyPlanItem.ItemType.PRACTICE,
            order=order, due_date=timezone.localdate() + timedelta(days=in_days),
        )
    else:
        item = None
    log_plan_change(
        student, reason=reason, description=description, is_major=is_major, node=node
    )
    return item


def log_plan_change(student, reason: str, description: str = "",
                    is_major: bool = False, node=None) -> PlanChangeLog | None:
    """Записать изменение плана без повторного шума.

    `reinsert_node` вызывается на каждой ошибке ученика, поэтому запись с той
    же причиной и тем же узлом переиспользуется в пределах
    `PLAN_CHANGE_LOG_DEDUP_HOURS`. Мажорные изменения не дедуплицируются: их
    подтверждает ученик, и каждое должно дойти до него.
    """
    plan = get_active_plan(student)
    if plan is None:
        return None

    if not is_major:
        cutoff = timezone.now() - timedelta(hours=settings.PLAN_CHANGE_LOG_DEDUP_HOURS)
        existing = (
            PlanChangeLog.objects.filter(
                plan=plan, node=node, reason=reason, is_major=False, created_at__gt=cutoff
            )
            .order_by("-created_at")
            .first()
        )
        if existing is not None:
            return existing

    change = PlanChangeLog.objects.create(
        plan=plan, node=node, reason=reason, description=description, is_major=is_major
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
        from_trajectory=current,
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


@transaction.atomic
def change_target_score(student, target_score: int) -> dict:
    """Change a student's goal and rebuild only when its trajectory changes."""
    old_score = student.target_score
    old_trajectory = _current_trajectory(student)
    student.target_score = target_score
    student.save(update_fields=["target_score"])

    trajectory = assign_trajectory(student, target_score)
    trajectory_changed = (
        old_trajectory is None or old_trajectory.pk != trajectory.pk
    )
    plan = get_active_plan(student)
    if trajectory_changed:
        plan = build_study_plan(student, reason=PlanChangeLog.Reason.MANUAL)
        log_plan_change(
            student,
            reason=PlanChangeLog.Reason.MANUAL,
            description=(
                f"Целевой балл изменён на {target_score} — траектория {trajectory.title}"
            ),
            is_major=True,
        )

    from apps.events.models import Event
    from apps.events.services import log_event

    log_event(
        Event.Type.TARGET_SCORE_CHANGED,
        student=student,
        old=old_score,
        new=target_score,
        trajectory_id=trajectory.id,
    )
    return {
        "target_score": target_score,
        "trajectory": trajectory,
        "trajectory_changed": trajectory_changed,
        "plan": plan,
    }


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


@transaction.atomic
def complete_item(item: StudyPlanItem) -> StudyPlanItem:
    if item.status == StudyPlanItem.Status.DONE:
        return item
    item.status = StudyPlanItem.Status.DONE
    item.completed_at = timezone.now()
    item.save(update_fields=["status", "completed_at"])
    from apps.gamification.services import record_plan_item_activity

    record_plan_item_activity(item.plan.student)
    return item


@transaction.atomic
def carry_over_overdue(student, on_date=None) -> int:
    """Перенести просроченные пункты на сегодня.

    Пропущенный день не должен превращаться в мёртвый груз: пункт с прошедшей
    датой остаётся первым по очереди, но получает сегодняшний срок, иначе
    «просрочено» копится и перестаёт что-либо значить.
    """
    plan = get_active_plan(student)
    if plan is None:
        return 0
    today = on_date or timezone.localdate()
    overdue = plan.items.filter(
        status=StudyPlanItem.Status.PENDING, due_date__lt=today
    )
    return overdue.update(due_date=today)


def items_for_period(student, start, end):
    plan = get_active_plan(student)
    if plan is None:
        return StudyPlanItem.objects.none()
    return plan.items.filter(due_date__gte=start, due_date__lte=end).select_related("node")


def autocomplete_items_for_node(student, node) -> list[StudyPlanItem]:
    """Закрыть пункты плана, которые ученик уже фактически выполнил.

    План — обещание сервиса, а не ручной чек-лист: если ученик решил задачу
    темы, пункт «пройти урок» закрывается сам, а «практика» — когда тема
    освоена до порога. Иначе выполненная работа висит невыполненной, а квесты
    и карточка плана врут.
    """
    plan = get_active_plan(student)
    if plan is None or node is None:
        return []

    from apps.knowledge.models import SkillMastery

    mastery = (
        SkillMastery.objects.filter(student=student, node=node)
        .values_list("mastery", flat=True)
        .first()
        or 0.0
    )
    finished_types = [StudyPlanItem.ItemType.LESSON]
    if mastery >= settings.MASTERY_THRESHOLD:
        finished_types.append(StudyPlanItem.ItemType.PRACTICE)

    pending = plan.items.filter(
        node=node, item_type__in=finished_types
    ).exclude(status=StudyPlanItem.Status.DONE)
    closed = [complete_item(item) for item in pending]
    if closed:
        # Закрытая тема меняет выгоду остальных: пороги пререквизитов открылись,
        # а часть плана могла обесцениться. Переоцениваем очередь сразу, пока
        # ученик ещё в занятии.
        reprioritize_plan(student)
    return closed


def autocomplete_review_items(student, node) -> list[StudyPlanItem]:
    """Закрыть пункты отработки после успешного повтора по теме."""
    plan = get_active_plan(student)
    if plan is None or node is None:
        return []
    pending = plan.items.filter(
        node=node, item_type=StudyPlanItem.ItemType.REVIEW
    ).exclude(status=StudyPlanItem.Status.DONE)
    return [complete_item(item) for item in pending]
