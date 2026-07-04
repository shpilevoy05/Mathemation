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


def build_study_plan(student) -> StudyPlan:
    """Build a plan from current mastery, dependencies and topic weights.

    Nodes already at/above MASTERY_THRESHOLD are skipped. Each node gets a
    lesson item and a practice item; items are spread over weeks by
    student.weekly_hours (assumption: 1 node ≈ 2 hours).
    """
    StudyPlan.objects.filter(student=student, status=StudyPlan.Status.ACTIVE).update(
        status=StudyPlan.Status.ARCHIVED
    )
    plan = StudyPlan.objects.create(student=student, target_score=student.target_score)

    masteries = mastery_map(student)
    nodes = list(KnowledgeNode.objects.select_related("cluster").all())
    pending = [n for n in nodes if masteries.get(n.id, 0) < settings.MASTERY_THRESHOLD]

    nodes_per_week = max(1, student.weekly_hours // 2)
    today = timezone.localdate()
    order = 0
    for i, node in enumerate(_topological_order(pending)):
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


def reinsert_node(student, node, reason: str, description: str = "") -> StudyPlanItem | None:
    """Return a topic to the active plan (frequent mistakes, poor mock, inactivity)."""
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
            order=last_order + 1, due_date=timezone.localdate() + timedelta(days=1),
        )
    else:
        item = None
    PlanChangeLog.objects.create(plan=plan, reason=reason, description=description)
    return item


def log_plan_change(student, reason: str, description: str = "") -> PlanChangeLog | None:
    plan = get_active_plan(student)
    if plan is None:
        return None
    return PlanChangeLog.objects.create(plan=plan, reason=reason, description=description)


def items_for_period(student, start, end):
    plan = get_active_plan(student)
    if plan is None:
        return StudyPlanItem.objects.none()
    return plan.items.filter(due_date__gte=start, due_date__lte=end).select_related("node")
