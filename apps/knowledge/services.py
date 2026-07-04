"""Mastery update domain logic."""
from .models import KnowledgeNode, SkillMastery

# Exponential-moving-average learning rate. TODO: replace with BKT/IRT later.
ALPHA = 0.3


def update_mastery(student, node: KnowledgeNode, correct: bool, weight: float = 1.0) -> SkillMastery:
    """Move mastery towards 100 on a correct attempt, towards 0 on a mistake.

    `weight` is the assignment↔skill tag weight (0..1] scaling the step.
    """
    sm, _ = SkillMastery.objects.get_or_create(student=student, node=node)
    target = 100.0 if correct else 0.0
    step = ALPHA * min(max(weight, 0.0), 1.0)
    sm.mastery = round(sm.mastery + step * (target - sm.mastery), 2)
    sm.refresh_status()
    sm.save()
    return sm


def set_mastery(student, node: KnowledgeNode, value: float) -> SkillMastery:
    """Directly set mastery (used when seeding from a diagnostic)."""
    sm, _ = SkillMastery.objects.get_or_create(student=student, node=node)
    sm.mastery = min(max(value, 0.0), 100.0)
    sm.refresh_status()
    sm.save()
    return sm


def mastery_map(student) -> dict[int, float]:
    return dict(
        SkillMastery.objects.filter(student=student).values_list("node_id", "mastery")
    )
