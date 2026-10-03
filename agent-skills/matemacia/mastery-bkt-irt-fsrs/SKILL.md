---
name: mastery-bkt-irt-fsrs
description: Use when changing mastery updates, forgetting curves, review intervals, IRT score probabilities, engine parameters, or algorithm tests.
---

# BKT, IRT и FSRS-подобный движок

Считай формулы в `apps/engine/` продуктовым контрактом прогнозов и планов.
Держи вычисления чистыми и детерминированными.

## Mastery

- Используй `bkt_update` из `apps/engine/mastery.py` для микрообновления после попытки.
- Ограничивай mastery диапазоном 0..100.
- Масштабируй шаг весом `AssignmentSkillTag.weight`.
- Передавай `bkt_alpha` только через `EngineParams`.
- Выполняй обновление синхронно в `apps/knowledge/services.py`.
- Не дублируй формулу в API, task или модели.

## Забывание и повторы

- Используй `decayed_mastery` из `apps/engine/decay.py`.
- Применяй grace period, затем экспоненциальный decay.
- Используй `next_intervals` для FSRS-подобной лестницы повторов.
- Передавай интервалы, ease и границы через `EngineParams`.
- Сохраняй idempotent-применение decay от `peak_mastery` и `peak_at`.
- Возвращай decayed-узел в план через `apps/knowledge/services.py`.

## IRT-прогноз

- Используй 2PL-логику `probability_correct` из `apps/engine/forecast.py`.
- Отображай mastery и difficulty 1..5 на общую логит-шкалу.
- Учитывай discrimination и guess из `EngineParams`.
- Суммируй ожидаемые баллы через `expected_primary`.
- Ограничивай первичный балл диапазоном 0..`max_primary_score`.
- Передавай годовую таблицу в `scaled_score` явным аргументом.

## Изменение формул

- Считай любое изменение формулы осознанным изменением прогнозов.
- Опиши ожидаемый эффект на контрольных профилях mastery.
- Обнови тесты `apps/engine/tests/test_algorithms.py` с объяснением причины.
- Не меняй числовые параметры внутри функции; используй `EngineParams` из settings-адаптеров.
- Сохраняй purity-тест `apps/engine/tests/test_purity.py`.

## Обязательные тестовые свойства движка

- mastery↑ у всех навыков → прогноз не ниже без явной причины;
- планировщик не назначает заблокированный навык;
- повторное событие с тем же idempotency key не меняет mastery дважды;
- больше времени → потолок не ниже;
- прогноз воспроизводим по версиям.

## Проверка

- Прогони database-free тесты движка.
- Проверь границы, монотонность и детерминизм.
- Проверь адаптеры `apps/knowledge/services.py`, `apps/practice/services.py`, `apps/progress/services.py`.
