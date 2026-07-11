"""Mastery update and forgetting-curve domain logic."""
import math

from django.conf import settings
from django.utils import timezone

from .models import KnowledgeNode, SkillMastery

# Exponential-moving-average learning rate. TODO: replace with BKT/IRT later.
ALPHA = 0.3


def update_mastery(student, node: KnowledgeNode, correct: bool, weight: float = 1.0) -> SkillMastery:
    """Move mastery towards 100 on a correct attempt, towards 0 on a mistake.

    `weight` is the assignment↔skill tag weight (0..1] scaling the step.
    Every practice resets the forgetting curve: peak = new value, peak_at = now.
    """
    sm, _ = SkillMastery.objects.get_or_create(student=student, node=node)
    target = 100.0 if correct else 0.0
    step = ALPHA * min(max(weight, 0.0), 1.0)
    sm.mastery = round(sm.mastery + step * (target - sm.mastery), 2)
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
    over_grace = max(0.0, days - settings.DECAY_GRACE_DAYS)
    return round(peak * math.exp(-settings.DECAY_RATE_PER_DAY * over_grace), 2)


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


def node_states(student) -> dict[int, dict]:
    """Состояния узлов карты: закрыто / можно начинать / в процессе / освоено / подзабылось.

    «Закрыто» и «можно начинать» выводятся из зависимостей: узел доступен,
    когда все его пререквизиты освоены (mastery >= MASTERY_THRESHOLD).
    """
    masteries = {
        m.node_id: m for m in SkillMastery.objects.filter(student=student)
    }
    nodes = list(KnowledgeNode.objects.prefetch_related("dependencies"))
    states = {}
    for node in nodes:
        m = masteries.get(node.id)
        prereq_ids = [d.prerequisite_id for d in node.dependencies.all()]
        unlocked = all(
            (masteries.get(pid) and masteries[pid].mastery >= settings.MASTERY_THRESHOLD)
            for pid in prereq_ids
        )
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
        }
    return states
