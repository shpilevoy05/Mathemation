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
    # Часы на освоение узла. 0 — взять hours_per_node из параметров: тема
    # второй части дороже короткой задачи первой, и планировщик обязан это
    # видеть, иначе «баллы за час» вырождаются в «баллы».
    hours: float = 0.0

    def study_hours(self, default_hours: float) -> float:
        return float(self.hours) if self.hours and self.hours > 0 else float(default_hours)


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
    discrimination: float = 1.0
    node_weights: tuple[float, ...] = ()


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
    theta_scale: float
    b_step: float
    default_discrimination: float
    guess: float
    review_intervals_days: tuple[int, ...]
    review_ease: float
    min_review_interval_days: int
    max_review_interval_days: int
    # Нормировать ли сумму ожидаемых баллов на суммарный балл переданных
    # заданий. Так считается прогноз по банку задач, где набор произвольный.
    # Для профиля экзамена нормировка выключается: сумма баллов заданий и есть
    # максимальный первичный балл, а деление сделало бы прогноз зависимым от
    # того, сколько задач методист загрузил в банк.
    normalize_by_task_weights: bool = True


@dataclass(frozen=True, slots=True)
class CeilingResult:
    mastery_profile: dict[int, float]
    reachable_node_ids: tuple[int, ...]
    unreachable_node_ids: tuple[int, ...]
