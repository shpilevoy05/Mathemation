"""Immutable values crossing the boundary of the pure engine."""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NodeState:
    node_id: int
    mastery: float
    last_practiced_at: datetime | None
    weight: float
    cluster_weight: float


@dataclass(frozen=True, slots=True)
class EdgeDTO:
    from_node_id: int
    to_node_id: int
    min_mastery: float = 70.0


@dataclass(frozen=True, slots=True)
class TaskWeight:
    assignment_id: int
    node_ids: tuple[int, ...]
    max_score: float
    difficulty: float


@dataclass(frozen=True, slots=True)
class EngineParams:
    """Algorithm configuration supplied by an adapter.

    Fields intentionally have no numeric defaults. Application settings remain
    the single source of configuration values.
    """

    mastery_threshold: float
    decay_grace_days: float
    decay_rate_per_day: float
    max_primary_score: float
    hours_per_node: float
    attainable_mastery: float
    bkt_alpha: float
    forecast_calibration_alpha: float


@dataclass(frozen=True, slots=True)
class CeilingResult:
    mastery_profile: dict[int, float]
    reachable_node_ids: tuple[int, ...]
    unreachable_node_ids: tuple[int, ...]
