"""Study plan building and adaptation."""
from collections import deque
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.knowledge.models import KnowledgeDependency, KnowledgeNode
from apps.knowledge.services import mastery_map

from .models import PlanChangeLog, StudyPlan, StudyPlanItem


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


def build_study_plan(student) -> StudyPlan:
    """Build a plan from current mastery, dependencies and topic weights.

    Nodes already at/above MASTERY_THRESHOLD are skipped. Each node gets a
    lesson item and a practice item; items are spread over weeks by
    student.weekly_hours (assumption: 1 node ≈ HOURS_PER_NODE hours).
    """
    StudyPlan.objects.filter(student=student, status=StudyPlan.Status.ACTIVE).update(
        status=StudyPlan.Status.ARCHIVED
    )
    plan = StudyPlan.objects.create(student=student, target_score=student.target_score)

    nodes_per_week = max(1, student.weekly_hours // settings.HOURS_PER_NODE)
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
    PlanChangeLog.objects.create(
        plan=plan, reason=reason, description=description, is_major=is_major
    )
    return item


def log_plan_change(student, reason: str, description: str = "",
                    is_major: bool = False) -> PlanChangeLog | None:
    plan = get_active_plan(student)
    if plan is None:
        return None
    return PlanChangeLog.objects.create(
        plan=plan, reason=reason, description=description, is_major=is_major
    )


def rebuild_after_inactivity(student, idle_days: int) -> StudyPlan | None:
    """«Тебя не было N недель. Перестроил план под сжатое время.»

    Снижение прогноза показываем фактом, без упрёка. Пропускаем учеников
    без активного плана (диагностика ещё не пройдена).
    """
    from apps.progress.services import predict_score

    if get_active_plan(student) is None:
        return None
    plan = build_study_plan(student)
    predicted, _ = predict_score(student)
    weeks = max(1, round(idle_days / 7))
    log_plan_change(
        student,
        reason=PlanChangeLog.Reason.INACTIVITY,
        description=(
            f"Тебя не было {weeks} нед. Перестроил план под сжатое время. "
            f"Текущий прогноз: {predicted}."
        ),
        is_major=True,
    )
    return plan


def complete_item(item: StudyPlanItem) -> StudyPlanItem:
    item.status = StudyPlanItem.Status.DONE
    item.save(update_fields=["status"])
    return item


def items_for_period(student, start, end):
    plan = get_active_plan(student)
    if plan is None:
        return StudyPlanItem.objects.none()
    return plan.items.filter(due_date__gte=start, due_date__lte=end).select_related("node")
