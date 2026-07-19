---
name: release-readiness
description: Use when preparing, reviewing, or approving a Mathemation release, deployment, migration rollout, static build, or production configuration.
---

# Готовность к релизу

Не объявляй релиз готовым без прохождения всех обязательных пунктов.
Используй нативный PowerShell и виртуальное окружение `.venv`.

## Код и тесты

- Запусти `.\scripts\test.ps1` из корня репозитория.
- Требуй полностью зелёный результат, не скрывай skipped/failed проверки.
- Запусти `makemigrations --check` через `.venv\Scripts\python.exe`.
- Проверь критические сценарии `apps/web/tests.py` и доменные тесты приложений.
- Проверь purity `apps/engine/tests/test_purity.py`.
- Не добавляй новую зависимость без явного одобрения.

## Миграции и данные

- Проверь миграции с нуля на чистой БД.
- Проверь безопасное применение поверх предыдущего релиза.
- Подтверди обратимость schema migration или документируй подтверждённое исключение.
- Проверь идемпотентность data migrations.
- Не запускай деструктивную миграцию без подтверждения человека.
- Проверь `seed_demo` из `apps/content/management/commands/seed_demo.py` повторным запуском.

## Production config

- Установи `DEBUG=False`.
- Выполни `collectstatic` и проверь `STATIC_ROOT` из `config/settings.py`.
- Проверь allowed hosts, CSRF, secure cookies и HTTPS на production-конфигурации.
- Храни секреты только в env/secret manager.
- Не читай, не печатай и не включай `.env` в артефакты.
- Проверь выбор PostgreSQL по `POSTGRES_DB`.
- Проверь Redis/Celery broker и `CELERY_BEAT_SCHEDULE`.

## Продуктовые контракты

- Проверь отключение наставника на mock/diagnostic/review.
- Проверь SymPy-блокировку и отсутствие утечки ответа.
- Проверь экспертный финальный вердикт части 2.
- Проверь append-only event log и отсутствие ПДн в payload.
- Проверь формулировку прогноза «при текущем темпе».

## Финальный чек-лист

- Зафиксируй версии приложения, движка и экзаменационной таблицы.
- Подготовь план отката кода и совместимых миграций.
- Проверь health/readiness зависимостей.
- Выполни smoke test ученика, родителя, эксперта и методиста.
- Останови релиз при любом незакрытом критическом пункте.
