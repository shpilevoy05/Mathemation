---
name: postgres-pgvector-schema
description: Use when designing queries, schema fields, locking, JSON payloads, vector search, or behavior that must work across SQLite and PostgreSQL.
---

# PostgreSQL, SQLite и pgvector

Сохраняй PostgreSQL полной локальной и production БД.
Сохраняй SQLite доступной для локальной разработки и тестов.
Переключение выполняется по `POSTGRES_DB` в `config/settings.py`.

## Совместимость БД

- Пиши обычные тесты так, чтобы они работали на SQLite.
- Добавляй PostgreSQL-специфичный тест для блокировок, JSONB и CTE, когда поведение важно.
- Не делай локальную разработку зависимой только от запущенного PostgreSQL.
- Не имитируй транзакционные гарантии PostgreSQL утверждениями SQLite.
- Документируй расхождение backend-ов рядом с тестом.

## JSON и события

- Используй `models.JSONField` для гибкого `Event.payload` в `apps/events/models.py`.
- Храни в payload только учебные метрики и идентификаторы.
- Не помещай ПДн в JSONB.
- Стабилизируй контракт ключей перед построением аналитики.
- Добавляй индексы только под измеренный запрос.

## Запросы

- Осторожно используй `.distinct()` при моделях с `Meta.ordering`.
- Помни известный класс ошибок: ordering может добавить столбцы и изменить distinct-результат.
- Сбрасывай ненужный ordering через `.order_by()` перед distinct-агрегацией.
- Проверяй SQL и результат на PostgreSQL для критичных выборок.
- Не решай N+1 переносом бизнес-логики в serializer; применяй `select_related`/`prefetch_related`.

## Блокировки

- Используй `select_for_update` только внутри транзакции.
- Помни, что реальная строковая блокировка работает на PostgreSQL, но не эквивалентно на SQLite.
- Проверяй конкурирующие начисления XP в `apps/gamification/services.py` на PostgreSQL.
- Не объявляй гонку закрытой только по зелёному SQLite-тесту.

## pgvector

- Рассматривай pgvector как будущий слой RAG в том же PostgreSQL.
- Не вводи отдельную векторную БД на старте.
- Версионируй модель эмбеддингов и источник `reference_solution`.
- Не сохраняй в эмбеддинги неразрешённые ПДн или непроверенный контент.

## Проверка

- Прогони SQLite-набор и целевой PostgreSQL-набор.
- Проверь distinct вместе с ordering.
- Проверь блокировку конкурирующим тестом на PostgreSQL.
- Проверь отсутствие ПДн в JSON и векторных данных.
