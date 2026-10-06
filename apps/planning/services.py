"""Study plan building and adaptation."""
from datetime import date, timedelta
from math import ceil

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.engine.dto import EdgeDTO, EngineParams, NodeState
from apps.engine.planner import greedy_plan, study_cost_hours, topological_order
from apps.exams.services import max_primary_score, task_weights_for_nodes
from apps.knowledge.models import KnowledgeDependency, KnowledgeNode
from apps.knowledge.services import mastery_map

from .models import (
    PlanChangeLog,
    StudyPlan,
    StudyPlanItem,
    Trajectory,
    TrajectoryTransition,
)

def _engine_params(profile=None) -> EngineParams:
    return EngineParams(
        mastery_threshold=settings.MASTERY_THRESHOLD,
        decay_grace_days=settings.DECAY_GRACE_DAYS,
        decay_rate_per_day=settings.DECAY_RATE_PER_DAY,
        max_primary_score=max_primary_score(profile),
        hours_per_node=settings.HOURS_PER_NODE,
        attainable_mastery=settings.ATTAINABLE_MASTERY,
        plan_min_cost_share=settings.PLAN_MIN_COST_SHARE,
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
        normalize_by_task_weights=profile is None,
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


def _ordered_pending_nodes_and_params(student) -> tuple[list[KnowledgeNode], EngineParams]:
    """Неосвоенные узлы в порядке изучения (зависимости + вес в баллах).

    Используется и планировщиком, и симуляцией потолка прогноза.
    """
    masteries = mastery_map(student)
    nodes = list(_planned_nodes().select_related("cluster"))
    ids = {node.id for node in nodes}
    edges = _graph_edges(ids)
    by_id = {node.id: node for node in nodes}
    states = [_node_dto(node, masteries.get(node.id, 0.0)) for node in nodes]
    weight_set = task_weights_for_nodes(nodes)
    params = _engine_params(weight_set.profile)
    ordered = greedy_plan(states, edges, weight_set.weights, params)
    return [by_id[state.node_id] for state in ordered], params


def order_pending_nodes(student) -> list[KnowledgeNode]:
    """Несвоенные узлы в порядке изучения (зависимости + вес в баллах).

    Используется публичными тестами и симуляцией: детали параметров движка остаются внутри сервиса.
    """
    nodes, _params = _ordered_pending_nodes_and_params(student)
    return nodes


def build_study_plan(student, reason: str = "initial") -> StudyPlan:
    """Build a plan from current mastery, dependencies and topic weights.

    Nodes already at/above MASTERY_THRESHOLD are skipped. Each node gets a
    lesson item and a practice item; items are spread over weeks by
    student.weekly_hours (assumption: 1 node ≈ HOURS_PER_NODE hours).
    """
    current = get_active_plan(student)
    trajectory = current.trajectory if current else None
    carried_items = _items_to_carry_into_new_plan(current, student.exam_date)
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

    carried_pairs = _copy_carried_items(carried_items, plan)
    _fill_plan_items(student, plan, trajectory, done_pairs=carried_pairs)
    _renumber_plan_items(plan)
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


def _items_to_carry_into_new_plan(plan: StudyPlan | None, exam_date) -> list[StudyPlanItem]:
    if plan is None:
        return []
    today = timezone.localdate()
    carried = plan.items.exclude(status=StudyPlanItem.Status.DONE).filter(
        models.Q(origin=StudyPlanItem.Origin.URGENT)
        | models.Q(origin=StudyPlanItem.Origin.MANUAL, due_date__gte=today)
    )
    if exam_date:
        carried = carried.filter(
            models.Q(due_date__isnull=True) | models.Q(due_date__lte=exam_date)
        )
    return list(carried.order_by("order"))


def _copy_carried_items(items: list[StudyPlanItem], plan: StudyPlan) -> set[tuple[int, str]]:
    carried_pairs = set()
    for item in items:
        StudyPlanItem.objects.create(
            plan=plan,
            node_id=item.node_id,
            item_type=item.item_type,
            order=item.order,
            week_index=item.week_index,
            due_date=item.due_date,
            status=item.status,
            origin=item.origin,
            completed_at=item.completed_at,
        )
        if item.node_id:
            carried_pairs.add((item.node_id, item.item_type))
    return carried_pairs


def _weekly_hours(student, trajectory) -> int:
    return student.weekly_hours


def _node_cost_hours(node, mastery: float, params: EngineParams) -> float:
    return study_cost_hours(_node_dto(node, mastery), params)


def _fill_plan_items(student, plan: StudyPlan, trajectory, *, done_pairs=None) -> int:
    """Разложить темы по неделям по выбранной нагрузке.

    Бюджет считается в часах, а не в темах: тема на четыре часа не должна
    занимать столько же места в неделе, сколько тема на два. В неделю кладётся
    ровно столько занятий, сколько человек успевает при своей загрузке.

    Уплотнять неделю, если до экзамена времени не хватает, нельзя: получится
    расписание, которое обещает выполнимость и её не даёт. То, что не влезает,
    в план не попадает и считается отдельно — это ровно та часть материала,
    которую не обещает и прогноз.
    """
    weekly_hours = max(1, _weekly_hours(student, trajectory))
    today = timezone.localdate()
    masteries = mastery_map(student)
    nodes, params = _ordered_pending_nodes_and_params(student)
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

    hours_per_week = float(weekly_hours)
    # Сколько недель осталось до экзамена. Без даты горизонта нет: план
    # раскладывается целиком.
    weeks_left = None
    if student.exam_date:
        weeks_left = max(1, ceil((student.exam_date - today).days / 7))

    order = 0
    week = 0
    hours_in_week = 0.0
    day_in_week = 0
    unplanned = 0
    for node in nodes:
        node_hours = _node_cost_hours(node, masteries.get(node.id, 0.0), params)
        if hours_in_week and hours_in_week + node_hours > hours_per_week:
            week += 1
            hours_in_week = 0.0
            day_in_week = 0
        if weeks_left is not None and week >= weeks_left:
            # Дальше экзамена планировать нечего: остаток честно не помещается.
            unplanned += 1
            continue
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
    if plan.unplanned_nodes != unplanned:
        plan.unplanned_nodes = unplanned
        plan.save(update_fields=["unplanned_nodes"])
    return order


def recommended_weekly_hours(student, exam_date=None) -> int | None:
    """Сколько часов в неделю нужно, чтобы пройти всё до экзамена.

    Считается по той же трудоёмкости тем, по которой раскладывается план:
    иначе совет разошёлся бы с расписанием. Без даты экзамена совета нет —
    успевать не к чему.
    """
    exam_date = exam_date or student.exam_date
    if exam_date is None:
        return None
    nodes, params = _ordered_pending_nodes_and_params(student)
    if not nodes:
        return 0
    masteries = mastery_map(student)
    total_hours = sum(
        _node_cost_hours(node, masteries.get(node.id, 0.0), params)
        for node in nodes
    )
    weeks_left = max(1, ceil((exam_date - timezone.localdate()).days / 7))
    return max(1, ceil(total_hours / weeks_left))


def _node_hours(node) -> float:
    """Часы на тему: собственная оценка узла, иначе дефолт по части экзамена."""
    hours = getattr(node, "effective_hours", None)
    if hours:
        return float(hours)
    return float(
        settings.HOURS_PER_NODE_BY_PART.get(node.exam_part, settings.HOURS_PER_NODE)
    )


def _item_pair_set(items) -> set[tuple[int, str]]:
    return {
        (item.node_id, item.item_type)
        for item in items
        if item.node_id
    }


def _active_priority(item: StudyPlanItem) -> int:
    if item.origin == StudyPlanItem.Origin.URGENT:
        return 0
    if item.origin == StudyPlanItem.Origin.MANUAL or item.status == StudyPlanItem.Status.IN_PROGRESS:
        return 1
    return 2


def _renumber_plan_items(plan: StudyPlan) -> None:
    done_items = list(plan.items.filter(status=StudyPlanItem.Status.DONE).order_by("order"))
    active_items = list(plan.items.exclude(status=StudyPlanItem.Status.DONE))
    ordered_active = sorted(
        active_items,
        key=lambda item: (
            item.due_date is None,
            item.due_date or date.max,
            _active_priority(item),
            item.order,
        ),
    )
    changed = []
    for index, item in enumerate([*done_items, *ordered_active]):
        if item.order != index:
            item.order = index
            changed.append(item)
    if changed:
        StudyPlanItem.objects.bulk_update(changed, ["order"])


@transaction.atomic
def reprioritize_plan(
    student, *, event_reason: str = "reprioritized", force_event: bool = False
) -> StudyPlan | None:
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

    before = list(
        plan.items.exclude(status=StudyPlanItem.Status.DONE)
        .order_by("order")
        .values_list("node_id", "item_type")
    )

    plan.items.filter(
        status=StudyPlanItem.Status.PENDING,
        origin=StudyPlanItem.Origin.PLAN,
    ).delete()
    # Закрытые пункты уходят в начало очереди: они уже история, и новая
    # нумерация не должна их перемешивать с актуальными.
    kept_pairs = _item_pair_set(plan.items.all())
    trajectory = plan.trajectory
    _fill_plan_items(student, plan, trajectory, done_pairs=kept_pairs)
    _renumber_plan_items(plan)

    after = list(
        plan.items.exclude(status=StudyPlanItem.Status.DONE)
        .order_by("order")
        .values_list("node_id", "item_type")
    )
    if force_event or before != after:
        from apps.events.models import Event
        from apps.events.services import log_event

        log_event(
            Event.Type.PLAN_REBUILT,
            student=student,
            plan_id=plan.id,
            reason=event_reason,
            is_major=False,
            items=len(after),
        )
    return plan


@transaction.atomic
def rebuild_unfinished_plan(
    student, *, reason: str, description: str, is_major: bool = False
) -> StudyPlan | None:
    """Пересобрать только незавершённую очередь и записать причину изменения."""
    if get_active_plan(student) is None:
        return None
    plan = reprioritize_plan(
        student, event_reason=reason, force_event=True
    )
    log_plan_change(
        student,
        reason=reason,
        description=description,
        is_major=is_major,
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
    urgent_due = timezone.localdate() + timedelta(days=in_days)
    item = (
        plan.items.filter(
            node=node,
            status=StudyPlanItem.Status.PENDING,
            item_type=StudyPlanItem.ItemType.PRACTICE,
        )
        .order_by("order")
        .first()
    )
    if item is not None:
        item.origin = StudyPlanItem.Origin.URGENT
        if item.due_date is None or urgent_due < item.due_date:
            item.due_date = urgent_due
        item.save(update_fields=["origin", "due_date"])
    else:
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
            order=order, due_date=urgent_due, origin=StudyPlanItem.Origin.URGENT,
        )
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


class PlanItemMoveRefused(ValueError):
    """Перенос невозможен: дата в прошлом или за датой экзамена."""


@transaction.atomic
def move_item(item, new_date) -> StudyPlanItem:
    """Перенести пункт плана на другой день.

    Правила простые и объяснимые: назад в прошлое не переносим — это не
    планирование, а подделка истории; за дату экзамена тоже, иначе план
    обещает время, которого нет. Готовый пункт не двигаем: он уже сделан.
    """
    today = timezone.localdate()
    if item.status == StudyPlanItem.Status.DONE:
        raise PlanItemMoveRefused("Выполненный пункт не переносится.")
    if new_date < today:
        raise PlanItemMoveRefused("Нельзя перенести на прошедший день.")
    exam_date = item.plan.student.exam_date
    if exam_date and new_date > exam_date:
        raise PlanItemMoveRefused("Дата позже экзамена — план так не строят.")
    item.due_date = new_date
    item.week_index = max(0, (new_date - today).days // 7)
    item.origin = StudyPlanItem.Origin.MANUAL
    item.save(update_fields=["due_date", "week_index", "origin"])
    log_plan_change(
        item.plan.student,
        PlanChangeLog.Reason.MANUAL,
        f"«{item.node.title}» перенесено на {new_date.strftime('%d.%m')}.",
        node=item.node,
    )
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
