"""Pure preparation-phase calendar calculations."""

from dataclasses import dataclass
from datetime import date, timedelta


LEARNING = "learning"
CONSOLIDATION = "consolidation"
EXAM = "exam"


@dataclass(frozen=True, slots=True)
class PhaseRange:
    code: str
    starts_on: date
    ends_on: date | None
    consolidation_starts_on: date | None
    exam_starts_on: date | None


def phase_for_date(
    plan_start: date,
    exam_date: date | None,
    on_date: date,
    *,
    consolidation_weeks: int,
    exam_phase_weeks: int,
) -> PhaseRange:
    """Return the phase and its inclusive date range for ``on_date``."""
    if exam_date is None:
        return PhaseRange(LEARNING, plan_start, None, None, None)

    weeks_left = max((exam_date - plan_start).days // 7, 0)
    final_weeks = min(max(consolidation_weeks, 0), weeks_left // 4)
    exam_weeks = min(max(exam_phase_weeks, 0), final_weeks)
    consolidation_start = (
        exam_date - timedelta(weeks=final_weeks) if final_weeks else None
    )
    exam_start = exam_date - timedelta(weeks=exam_weeks) if exam_weeks else None

    if exam_start is not None and on_date >= exam_start:
        return PhaseRange(EXAM, exam_start, exam_date, consolidation_start, exam_start)
    if consolidation_start is not None and on_date >= consolidation_start:
        return PhaseRange(
            CONSOLIDATION,
            consolidation_start,
            exam_start - timedelta(days=1),
            consolidation_start,
            exam_start,
        )
    learning_end = (
        consolidation_start - timedelta(days=1)
        if consolidation_start is not None
        else exam_date
    )
    return PhaseRange(
        LEARNING, plan_start, learning_end, consolidation_start, exam_start
    )
