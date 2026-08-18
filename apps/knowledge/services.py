"""ORM adapters for mastery and forgetting-curve engine algorithms."""

from django.conf import settings
from django.utils import timezone

from apps.engine.decay import decayed_mastery
from apps.engine.dto import EngineParams
from apps.engine.mastery import bkt_update

from .models import KnowledgeDependency, KnowledgeNode, SkillMastery


def would_create_cycle(
    node: KnowledgeNode,
    prerequisite: KnowledgeNode,
    *,
    exclude_dependency_id: int | None = None,
) -> bool:
    """Замкнёт ли новая зависимость граф.

    Идём вверх по рёбрам от предполагаемого пререквизита: если оттуда
    достижим сам узел, связь создаёт цикл. Обход итеративный — граф ведут
    методисты, и рекурсия на большой цепочке была бы лишним риском.
    """
    if node.pk is None or prerequisite.pk is None:
        return node is prerequisite

    target_id = node.pk
    frontier = {prerequisite.pk}
    visited: set[int] = set()
    while frontier:
        if target_id in frontier:
            return True
        visited.update(frontier)
        prerequisite_ids = set(
            KnowledgeDependency.objects.filter(
                node_id__in=frontier, kind=KnowledgeDependency.Kind.PREREQUISITE
            )
            .exclude(pk=exclude_dependency_id)
            .values_list("prerequisite_id", flat=True)
        )
        frontier = prerequisite_ids - visited
    return False


def gates():
    """Связи, которые действительно закрывают темы."""
    return KnowledgeDependency.objects.filter(kind=KnowledgeDependency.Kind.PREREQUISITE)


def learnable_nodes():
    """Узлы, которые можно изучать: папки практикой не закрываются."""
    return KnowledgeNode.objects.exclude(node_type=KnowledgeNode.NodeType.GROUP)


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


def update_mastery(student, node: KnowledgeNode, correct: bool, weight: float = 1.0) -> SkillMastery:
    """Move mastery towards 100 on a correct attempt, towards 0 on a mistake.

    `weight` is the assignment↔skill tag weight (0..1] scaling the step.
    Every practice resets the forgetting curve: peak = new value, peak_at = now.
    """
    sm, _ = SkillMastery.objects.get_or_create(student=student, node=node)
    sm.mastery = bkt_update(sm.mastery, correct, weight, _engine_params())
    sm.peak_mastery = sm.mastery
    sm.peak_at = timezone.now()
    sm.last_practiced_at = sm.peak_at
    sm.refresh_status()
    sm.save()
    return sm


def set_mastery(student, node: KnowledgeNode, value: float) -> SkillMastery:
    """Directly set mastery (used when seeding from a diagnostic)."""
    sm, _ = SkillMastery.objects.get_or_create(student=student, node=node)
    sm.mastery = min(max(value, 0.0), 100.0)
    sm.peak_mastery = sm.mastery
    sm.peak_at = timezone.now()
    sm.last_practiced_at = sm.peak_at
    sm.refresh_status()
    sm.save()
    return sm


def decayed_value(peak: float, peak_at, now=None) -> float:
    """Forgetting curve: exponential decay after a grace period.

    TODO: replace with FSRS-style per-node half-life once attempt logs allow it.
    """
    now = now or timezone.now()
    days = (now - peak_at).total_seconds() / 86400
    return decayed_mastery(peak, days, _engine_params())


def apply_decay(student) -> list[SkillMastery]:
    """Re-apply the forgetting curve to all student skills (idempotent).

    Called after every session/mock and daily by Celery; freshly decayed
    mastered nodes flip to «подзабылось» and return to the study plan.
    """
    newly_decayed = []
    for sm in SkillMastery.objects.filter(student=student, peak_mastery__gt=0).select_related("node"):
        value = decayed_value(sm.peak_mastery, sm.peak_at)
        if abs(value - sm.mastery) < 0.01:
            continue
        was_decayed = sm.status == SkillMastery.Status.DECAYED
        sm.mastery = value
        sm.refresh_status()
        sm.save(update_fields=["mastery", "status", "updated_at"])
        if sm.status == SkillMastery.Status.DECAYED and not was_decayed:
            newly_decayed.append(sm)

    if newly_decayed:
        from apps.planning.models import PlanChangeLog
        from apps.planning.services import reinsert_node

        for sm in newly_decayed:
            reinsert_node(
                student, sm.node,
                reason=PlanChangeLog.Reason.DECAY,
                description=(
                    f"Тема «{sm.node.title}» подзабылась (осталось {sm.mastery:.0f}% "
                    "от освоенного) — вернул её в план на повторение."
                ),
            )
    return newly_decayed


def mastery_map(student) -> dict[int, float]:
    return dict(
        SkillMastery.objects.filter(student=student).values_list("node_id", "mastery")
    )


def group_mastery(node: KnowledgeNode, child_masteries: list[float]) -> float:
    """Освоение папки из освоения детей.

    Способ выбирает методист: по минимуму папка закрывается по самому слабому
    ребёнку, по среднему — раньше. Папка без детей — ноль, а не сто: пустая
    папка ничего не доказывает.
    """
    if not child_masteries:
        return 0.0
    if node.group_aggregation == KnowledgeNode.GroupAggregation.MINIMUM:
        return min(child_masteries)
    return sum(child_masteries) / len(child_masteries)


def node_states(student) -> dict[int, dict]:
    """Состояния узлов карты: закрыто / можно начинать / в процессе / освоено / подзабылось.

    «Закрыто» и «можно начинать» выводятся из обязательных связей: узел
    доступен, когда каждый его предшественник освоен до порога конкретного
    ребра. Поддерживающие связи в расчёт не идут — они объясняют порядок, но
    ничего не закрывают, и попадают в ответ отдельным списком.

    Папка своего освоения не имеет: её состояние собирается по детям.
    """
    masteries = {
        m.node_id: m for m in SkillMastery.objects.filter(student=student)
    }
    nodes = list(KnowledgeNode.objects.prefetch_related("dependencies__prerequisite"))
    states = {}
    for node in nodes:
        if node.is_group:
            continue
        m = masteries.get(node.id)
        dependencies = list(node.dependencies.all())
        gate_dependencies = [dependency for dependency in dependencies if dependency.is_gate]
        prereq_ids = [dependency.prerequisite_id for dependency in gate_dependencies]
        supporting = [
            {
                "node_id": dependency.prerequisite_id,
                "title": dependency.prerequisite.title,
            }
            for dependency in dependencies
            if not dependency.is_gate
        ]
        unmet_conditions = []
        for dependency in gate_dependencies:
            current = masteries.get(dependency.prerequisite_id)
            current_mastery = current.mastery if current else 0.0
            if current_mastery < dependency.min_mastery:
                unmet_conditions.append(
                    {
                        "node_id": dependency.prerequisite_id,
                        "title": dependency.prerequisite.title,
                        "required_mastery": dependency.min_mastery,
                        "current_mastery": current_mastery,
                    }
                )
        unlocked = not unmet_conditions
        if m and m.status == SkillMastery.Status.MASTERED:
            state = "mastered"
        elif m and m.status == SkillMastery.Status.DECAYED:
            state = "decayed"
        elif m and m.mastery > 0:
            state = "in_progress"
        elif unlocked:
            state = "available"
        else:
            state = "locked"
        states[node.id] = {
            "state": state,
            "mastery": m.mastery if m else 0.0,
            "decay_percent": m.decay_percent if m else 0.0,
            "last_practiced_at": m.last_practiced_at if m else None,
            "prerequisites": prereq_ids,
            "unmet_conditions": unmet_conditions,
            "supporting": supporting,
        }

    # Папки считаем после навыков: их состояние — производное от детей.
    for group in nodes:
        if not group.is_group:
            continue
        children = [states[child.id] for child in nodes if child.parent_id == group.id and child.id in states]
        values = [child["mastery"] for child in children]
        value = group_mastery(group, values)
        states[group.id] = {
            "state": _group_state(children, value),
            "mastery": value,
            "decay_percent": 0.0,
            "last_practiced_at": None,
            "prerequisites": [],
            "unmet_conditions": [],
            "supporting": [],
            "is_group": True,
            "child_count": len(children),
        }
    return states


def _group_state(children: list[dict], value: float) -> str:
    """Состояние папки: по детям, а не по собственному освоению."""
    if not children:
        return "locked"
    if value >= settings.MASTERY_THRESHOLD:
        return "mastered"
    if any(child["state"] == "decayed" for child in children):
        return "decayed"
    if value > 0:
        return "in_progress"
    if any(child["state"] == "available" for child in children):
        return "available"
    return "locked"
