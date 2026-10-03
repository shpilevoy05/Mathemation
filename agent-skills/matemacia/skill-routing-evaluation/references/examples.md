# Примеры routing-кейсов и разбора метрик

## Положительный кейс

```yaml
- id: RT-011
  kind: positive
  agent: any
  prompt: "Проверь миграцию Django на блокировки и возможность rollback"
  expected: [safe-database-migrations]
  allowed_extra: [postgres-best-practices]
```

`allowed_extra` — скиллы, наличие которых не считается false positive:
вспомогательный vendor-скилл допустим, обязательный доменный — обязателен.

## Отрицательный кейс

```yaml
- id: RT-012
  kind: negative
  agent: any
  prompt: "Исправь текст кнопки в интерфейсе"
  must_not_activate: [safe-database-migrations]
```

## Кейс приоритета

```yaml
- id: RT-013
  kind: priority
  agent: any
  prompt: "Измени схему хранения mastery"
  priority:
    - matemacia-product-invariants
    - mastery-bkt-irt-fsrs
    - postgres-pgvector-schema
    - postgres-best-practices
```

Проверяется порядок применения, а не только состав: продуктовый инвариант
читается раньше, чем vendor-рекомендация по PostgreSQL.

## Разбор провала precision

Прогон:

```yaml
observations:
  - id: RT-012
    selected: [safe-database-migrations, frontend-components]
```

Причина: в описании `safe-database-migrations` есть слово «изменение», без
условия «изменение схемы БД». Правка: добавить в описание объект («схема,
миграции, индексы») и раздел «Когда не активируется» с UI-правками.

## Разбор провала recall критического скилла

Кейс ожидал `socratic-tutor-rag`, агент выбрал общий LLM-скилл. Причина:
описание доменного скилла не содержит триггерных слов задачи («подсказка
ученику», «наставник», «не выдавать ответ»). Правка — в описании, не в кейсе.

## Сравнение агентов

```text
                 precision  recall  fpr
claude-code           0.93    0.96  0.07
codex                 0.88    0.96  0.12
```

Расхождение по precision передаётся в `skill-cross-agent-consistency`:
допустимо расхождение в выборе вспомогательных vendor-скиллов, недопустимо —
в обязательных доменных.
