"""Mastery updates with no persistence concerns."""
from .dto import EngineParams


def bkt_update(
    p_mastery: float,
    is_correct: bool,
    weight: float,
    params: EngineParams,
) -> float:
    """Apply the existing weighted EMA/BKT-style micro-update."""
    mastery = min(max(float(p_mastery), 0.0), 100.0)
    target = 100.0 if is_correct else 0.0
    step = params.bkt_alpha * min(max(float(weight), 0.0), 1.0)
    return round(mastery + step * (target - mastery), 2)

