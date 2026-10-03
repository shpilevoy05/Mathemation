"""Соперник-бот: честный и предсказуемый.

Бот не «подыгрывает». Его прогон разыгрывается один раз, в момент создания
партии, по тем же вероятностям, которыми платформа оценивает шансы ученика
(IRT-модель из движка): уровень бота — это его условное освоение, сложность
задачи — её difficulty. Дальше бот не меняется, как бы ни играл человек.

Почему так, а не «бот отвечает чуть хуже игрока»: подстраивающийся соперник
даёт ощущение подкрутки — а мы обещаем честную оценку и не можем позволить
себе игру, в которой результат подогнан.
"""

from __future__ import annotations

import random

from django.conf import settings

from apps.engine.dto import EngineParams
from apps.engine.forecast import probability_correct

# Уровень бота 1..5 → условное освоение в процентах. Пятый уровень — сильный
# ученик, а не безошибочная машина: непобедимый соперник не мотивирует.
BOT_MASTERY = {1: 25.0, 2: 45.0, 3: 62.0, 4: 78.0, 5: 90.0}
# Среднее время ответа, секунды: чем выше уровень, тем увереннее и быстрее.
BOT_SECONDS = {1: 55.0, 2: 42.0, 3: 32.0, 4: 24.0, 5: 17.0}
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
    mastery = BOT_MASTERY[level]
    average = BOT_SECONDS[level]
    rng = random.Random(seed)
    params = _params()

    run = []
    for question in questions:
        chance = probability_correct(mastery, question.assignment.difficulty, params)
        correct = rng.random() < chance
        # Разброс времени, но без мгновенных ответов: бот «думает».
        seconds = max(4.0, rng.gauss(average, average * 0.28))
        # Ошибка обычно стоит времени: неверный ответ приходит позже.
        if not correct:
            seconds *= 1.15
        run.append({
            "question": question,
            "is_correct": correct,
            "time_ms": int(round(min(seconds, 600) * 1000)),
        })
    return run


# Теория спрашивается короче задачи, поэтому у неё свои времена.
# Квиз: время до нажатия на вариант — здесь решает реакция, а не вычисление.
BOT_BUZZ_SECONDS = {1: 8.5, 2: 7.0, 3: 5.5, 4: 4.0, 5: 2.8}
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
    average = (BOT_BUZZ_SECONDS if mode == "quiz" else BOT_THEORY_SECONDS)[level]
    rng = random.Random(seed)
    params = _params()

    run = []
    for question in questions:
        difficulty = question.theory.difficulty if question.theory_id else 3
        chance = probability_correct(mastery, difficulty, params)
        correct = rng.random() < chance
        seconds = max(1.5, rng.gauss(average, average * 0.3))
        # Неуверенный ответ приходит позже: бот «сомневается» ровно так же,
        # как ошибается, — по заранее разыгранному сценарию.
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
