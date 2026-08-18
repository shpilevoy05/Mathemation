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
