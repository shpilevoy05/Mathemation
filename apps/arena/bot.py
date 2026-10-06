"""Детерминированный соперник-бот.

Нарешивание и квиз используют настроенные по уровням таблицы ошибок и
среднего времени. «Своя игра» сохраняет IRT-модель освоения и сложности.
Прогон фиксируется seed при создании партии и не зависит от игры человека.
"""

from __future__ import annotations

import random

from apps.engine.dto import EngineParams
from apps.engine.forecast import probability_correct

# Уровень бота 1..5 → условное освоение в процентах. Пятый уровень — сильный
# ученик, а не безошибочная машина: непобедимый соперник не мотивирует.
BOT_MASTERY = {1: 25.0, 2: 45.0, 3: 62.0, 4: 78.0, 5: 90.0}
BOT_ERROR_PROBABILITY = {1: 0.25, 2: 0.15, 3: 0.15, 4: 0.10, 5: 0.02}
BOT_SECONDS = {1: 60.0, 2: 40.0, 3: 30.0, 4: 25.0, 5: 15.0}
BOT_QUIZ_SECONDS = {1: 30.0, 2: 25.0, 3: 20.0, 4: 15.0, 5: 12.5}
MIN_LEVEL, MAX_LEVEL = 1, 5


def clamp_level(level: int) -> int:
    return max(MIN_LEVEL, min(MAX_LEVEL, int(level)))


def _params() -> EngineParams:
    from apps.progress.services import _engine_params

    return _engine_params()


def bot_run(questions, level: int, seed: int) -> list[dict]:
    """Разыграть ответы бота: попал или нет и за сколько.

    `seed` привязан к партии, поэтому прогон воспроизводим: один и тот же бот
    в одной и той же партии всегда играет одинаково — это важно и для тестов,
    и для разбора спорных результатов.
    """
    level = clamp_level(level)
    average = BOT_SECONDS[level]
    rng = random.Random(seed)

    run = []
    for question in questions:
        correct = rng.random() >= BOT_ERROR_PROBABILITY[level]
        seconds = max(average * 0.6, rng.gauss(average, average * 0.15))
        run.append({
            "question": question,
            "is_correct": correct,
            "time_ms": int(round(min(seconds, 600) * 1000)),
        })
    return run


# «Своя игра»: время до ответа на открытую клетку — надо вспомнить и написать.
BOT_THEORY_SECONDS = {1: 22.0, 2: 18.0, 3: 14.0, 4: 10.0, 5: 7.0}


def theory_run(questions, level: int, seed: int, *, mode: str) -> list[dict]:
    """Разыграть знание бота по теории: знает ли он вопрос и как скоро ответит.

    Тот же принцип, что и в нарешивании: всё решается заранее, при создании
    партии. В квизе и «своей игре» ходы идут по очереди, поэтому важен не
    итог целиком, а расписание — «на этот вопрос бот ответит через N мс».
    Расписание фиксировано, значит бот не может ускориться, увидев, что
    человек медлит.
    """
    level = clamp_level(level)
    mastery = BOT_MASTERY[level]
    average = (BOT_QUIZ_SECONDS if mode == "quiz" else BOT_THEORY_SECONDS)[level]
    rng = random.Random(seed)
    params = _params()

    run = []
    for question in questions:
        difficulty = question.theory.difficulty if question.theory_id else 3
        if mode == "quiz":
            correct = rng.random() >= BOT_ERROR_PROBABILITY[level]
            seconds = min(29.5, max(average * 0.6, rng.gauss(average, average * 0.15)))
        else:
            chance = probability_correct(mastery, difficulty, params)
            correct = rng.random() < chance
            seconds = max(1.5, rng.gauss(average, average * 0.3))
            if not correct:
                seconds *= 1.2
        run.append({
            "question": question,
            "is_correct": correct,
            "time_ms": int(round(min(seconds, 120) * 1000)),
        })
    return run


def choose_cell(cells, level: int, seed: int):
    """Какую клетку доски выберет бот на своём ходу.

    Стратегия по уровню, а не случайность ради случайности: слабый бот идёт от
    дешёвых клеток (осторожная игра новичка), сильный сразу забирает дорогие,
    средний выбирает наугад. Выбор зависит только от того, что осталось на
    доске, поэтому он воспроизводим при разборе партии.
    """
    if not cells:
        return None
    level = clamp_level(level)
    if level <= 2:
        return min(cells, key=lambda cell: (cell.points, cell.order))
    if level >= 4:
        return max(cells, key=lambda cell: (cell.points, -cell.order))
    return random.Random(seed).choice(list(cells))
