---
name: django-drf-celery-conventions
description: Use when implementing Django views, DRF endpoints, serializers, service functions, Celery tasks, retries, schedules, or local worker instructions.
---

# Конвенции Django, DRF и Celery

Следуй правилу fat services / thin views.
Используй Django Admin как обязательный продуктовый интерфейс бэкофиса.

## Django и DRF

- Помещай бизнес-логику в сервисы владельца, например `apps/progress/services.py`.
- Оставляй model methods для локальных инвариантов данных, а не сценариев продукта.
- Оставляй serializers для валидации и представления, а не оркестрации.
- Оставляй API views для auth, object lookup, вызова сервиса и формирования ответа.
- Не выполняй расчёт mastery, прогноза, плана или XP в view.
- Используй `/api/` и маршруты из `config/urls.py`.
- Сохраняй session authentication из `REST_FRAMEWORK` в `config/settings.py`.
- Требуй `IsAuthenticated` по умолчанию и object-level проверки владельца.

## Сервисный слой

- Делай сервисные функции явными и тестируемыми.
- Используй `transaction.atomic` для многомодельных инвариантов.
- Не размазывай одну операцию между signal, serializer и view.
- Вызывай `log_event` в том же доменном сценарии, где произошло событие.
- Возвращай доменный результат, а не HTTP response.

## Celery

- Размещай задачи в модуле владельца, например `apps/progress/tasks.py`.
- Делай задачу идемпотентной при повторной доставке.
- Настраивай retries и экспоненциальный backoff для временных внешних ошибок.
- Не ретраить необратимую доменную мутацию без idempotency key.
- Выноси тяжёлые операции: полный реплан, decay, потолок, отчёты и квесты.
- Оставляй запись попытки и BKT-микрообновление синхронными.
- Регистрируй периодику в `CELERY_BEAT_SCHEDULE` в `config/settings.py`.
- Не создавай второй независимый планировщик cron для тех же задач.

## Windows

- Используй нативный PowerShell и `.venv\Scripts\python.exe`.
- Запускай локальный worker с `--pool=solo`.
- Сверяй команду с `scripts/worker.ps1`.
- Не требуй WSL, Ubuntu или Linux-only команд.

## Проверка

- Проверь отсутствие бизнес-логики в view/serializer/admin.
- Проверь auth и фильтрацию объекта по владельцу.
- Проверь повторный запуск Celery-задачи.
- Проверь retries/backoff для внешнего вызова.
- Проверь beat-настройку и Windows-команду worker.
