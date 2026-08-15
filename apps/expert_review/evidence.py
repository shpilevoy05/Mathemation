"""Из отметок эксперта — в освоение навыков.

Раньше вердикт двигал все темы задачи одинаково: одна ошибка в отборе корней
роняла и «значения синуса», и «нулевое произведение», и ещё десяток навыков,
которые ученик выполнил верно. Отметки по шагам убирают это враньё — каждый
навык получает ровно то свидетельство, которое эксперт наблюдал.

Три правила разметки, ради которых модуль и существует:

* **нет действия — нет обновления.** Шаг, которого ученик не делал, не
  понижает навык: незнание и неиспользование это разные вещи;
* **роль и сила независимы.** Вспомогательный шаг может дать сильный сигнал,
  поэтому вес берётся из силы, а не из роли;
* **свидетельство идёт самому конкретному узлу.** Ни предкам, ни
  предшественникам оно не переносится: правильный отбор корней не доказывает
  владение числовой окружностью.
"""

from __future__ import annotations

from django.conf import settings

from apps.content.models import SolutionStep
from apps.knowledge.services import update_mastery
from apps.practice.models import MistakeBacklogItem
from apps.practice.services import register_mistake

from .models import SolutionStepMark

# Во что превращается сила сигнала при обновлении освоения. Сильный сигнал
# двигает навык заметно, слабый копится по многим задачам.
DEFAULT_SIGNAL_WEIGHTS = {
    SolutionStep.Signal.STRONG: 1.0,
    SolutionStep.Signal.WEAK: 0.35,
}

# Какой тип ошибки заводить по этапу, на котором ученик споткнулся. Полка
# ошибок читается человеком, и «ошибка в отборе корней» полезнее, чем «ошибка».
STAGE_ERROR_TYPES = {
    SolutionStep.Stage.TRANSFORM: MistakeBacklogItem.ErrorType.ALGEBRAIC_SLIP,
    SolutionStep.Stage.ALGEBRA: MistakeBacklogItem.ErrorType.ALGEBRAIC_SLIP,
    SolutionStep.Stage.EQUATION: MistakeBacklogItem.ErrorType.WRONG_METHOD,
    SolutionStep.Stage.CONSTRAINTS: MistakeBacklogItem.ErrorType.INCOMPLETE_ARGUMENT,
    SolutionStep.Stage.SELECTION: MistakeBacklogItem.ErrorType.WRONG_METHOD,
    SolutionStep.Stage.CHECK: MistakeBacklogItem.ErrorType.INCOMPLETE_ARGUMENT,
    SolutionStep.Stage.FORMAT: MistakeBacklogItem.ErrorType.RUBRIC_MISS,
}


def signal_weight(signal: str) -> float:
    weights = getattr(settings, "EVIDENCE_SIGNAL_WEIGHTS", None) or DEFAULT_SIGNAL_WEIGHTS
    return float(weights.get(signal, DEFAULT_SIGNAL_WEIGHTS[SolutionStep.Signal.WEAK]))


def apply_step_marks(review) -> dict:
    """Разнести отметки по навыкам. Возвращает сводку для отчёта и логов."""
    marks = list(
        SolutionStepMark.objects.filter(review=review).select_related("step", "step__node")
    )
    summary = {"done": [], "wrong": [], "missing": []}
    for mark in marks:
        step = mark.step
        node = step.node
        summary[mark.outcome].append(node.id)
        if mark.outcome == SolutionStepMark.Outcome.MISSING:
            # Действия не было — свидетельства тоже нет.
            continue
        correct = mark.outcome == SolutionStepMark.Outcome.DONE
        update_mastery(review.student, node, correct, signal_weight(step.signal))
        if correct:
            continue
        register_mistake(
            review.student, review.assignment, node,
            error_type=STAGE_ERROR_TYPES.get(
                step.stage, MistakeBacklogItem.ErrorType.UNKNOWN
            ),
        )
    return summary


def missing_required_steps(review) -> list[SolutionStep]:
    """Обязательные шаги, которых в решении не оказалось.

    Ученику это и есть ответ на вопрос «что именно не сошлось»: не «минус балл
    за задачу», а «не выписал ограничения и не проверил корни».
    """
    marks = {
        mark.step_id: mark.outcome
        for mark in SolutionStepMark.objects.filter(review=review)
    }
    return [
        step
        for step in SolutionStep.objects.filter(pk__in=marks, is_required=True).select_related("node")
        if marks[step.pk] != SolutionStepMark.Outcome.DONE
    ]


def canonical_path(assignment):
    """Путь, по которому ведётся проверка. Канонический, если он есть."""
    paths = list(assignment.solution_paths.filter(is_active=True).prefetch_related("steps__node"))
    if not paths:
        return None
    return next((path for path in paths if path.is_canonical), paths[0])
