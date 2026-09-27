"""Human-readable labels shared by cabinet read models."""

ERROR_TYPE_LABELS = {
    "algebraic_slip": "алгебраическая ошибка",
    "arithmetic_slip": "арифметическая ошибка",
    "wrong_method": "неверный метод",
    "incomplete_argument": "неполное обоснование",
    "rubric_miss": "потеря критерия ФИПИ",
    "graph_misread": "неверно прочитан график",
    "misread_condition": "неверно прочитано условие",
    "unknown": "тип уточняется",
}


TRAJECTORY_REASON_LABELS = {
    "target_score": "изменена цель",
    "poor_mock": "результат пробника",
    "frequent_mistakes": "частые ошибки",
    "inactivity": "перерыв в занятиях",
    "decay": "тема вернулась на повторение",
    "manual": "ручная корректировка",
}
