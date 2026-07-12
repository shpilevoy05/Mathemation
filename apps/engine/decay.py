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


def next_intervals(
    error_count: int, success_streak: int, params: EngineParams
) -> list[int]:
    """Adapt the configured review ladder after failures and successes."""
    shrink = 0.5 ** max(int(error_count), 0)
    stretch = params.review_ease ** max(int(success_streak), 0)
    return [
        min(
            max(
                int(round(float(days) * shrink * stretch)),
                params.min_review_interval_days,
            ),
            params.max_review_interval_days,
        )
        for days in params.review_intervals_days
    ]
