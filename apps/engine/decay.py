"""Pure forgetting-curve calculations."""
import math

from .dto import EngineParams


def decayed_mastery(
    p_mastery: float,
    days_since_practice: float,
    params: EngineParams,
) -> float:
    """Apply exponential decay after the configured grace period."""
    over_grace = max(0.0, float(days_since_practice) - params.decay_grace_days)
    value = float(p_mastery) * math.exp(-params.decay_rate_per_day * over_grace)
    return round(min(max(value, 0.0), 100.0), 2)

