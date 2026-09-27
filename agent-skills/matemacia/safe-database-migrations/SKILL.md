---
name: safe-database-migrations
description: Use when adding, altering, backfilling, renaming, or removing Django models and fields, constraints, choices, groups, or production data.
metadata:
  owner: architecture
  version: 1.0.0
  status: active
  last_reviewed: 2026-07-19
  criticality: medium
activation_examples:
  positive:
    - "Проверь миграцию Django на блокировки и возможность rollback"
    - "Добавь обязательное поле в заполненную таблицу через безопасный expand и backfill"
  negative:
    - "Исправь текст кнопки в интерфейсе"
    - "Сравни два варианта промпта наставника"
conflicts_with: []
precedence:
  - "Product invariants first (matemacia-product-invariants)"
  - "Then this domain skill"
  - "Then vendor best practices"
  - "Then generic engineering advice"
---

# Безопасные миграции

Сопровождай каждую правку схемы Django-миграцией в том же изменении.
Не выполняй ручные правки БД.
Не запускай деструктивные database-команды.

## Expand/contract

- Сначала добавляй совместимую nullable/дефолтную структуру.
- Затем выкатывай код двойного чтения или двойной записи, если это необходимо.
- После этого выполняй backfill отдельной идемпотентной data migration.
- Переключай чтение только после проверки заполнения.
- Удаляй старое поле отдельным contract-релизом.
- Не объединяй рискованное удаление и переход логики в один необратимый шаг.

## Data migrations

- Пиши data migration через historical models из `apps.get_model`.
- Не импортируй текущие модели и сервисы приложения в migration.
- Делай повторный запуск логически безопасным.
- Используй `get_or_create`, `update_or_create` или проверку существования.
- Следуй примеру `apps/accounts/migrations/0004_seed_backoffice_groups.py`.
- Задавай обратную операцию, когда она безопасна и однозначна.
- Явно используй `RunPython.noop`, если откат данных намеренно невозможен.

## Риски

- Требуй подтверждение человека для удаления таблиц, столбцов или исторических данных.
- Требуй подтверждение для массового пересчёта баллов, mastery и событий.
- Не удаляй использованный `KnowledgeNode` без миграции истории.
- Не меняй смысл choice-значения задним числом; добавляй новое значение и мигрируй явно.
- Не переписывай append-only события миграцией без отдельного одобрения.

## Совместимость

- Проверяй миграцию на SQLite и PostgreSQL.
- Избегай долгой блокировки большой таблицы; разбивай backfill на безопасные шаги.
- Проверяй unique/foreign key ограничения до их включения.
- Сохраняй чтение старой и новой версией приложения на переходном этапе.

## Проверка

- Запусти `makemigrations --check`.
- Прогони миграции с нуля на чистой тестовой БД.
- Проверь migrate вперёд и безопасный откат до предыдущей версии.
- Проверь повторяемость data migration.
- Зафиксируй человеческое подтверждение перед деструктивным шагом.
