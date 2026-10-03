# Примеры записанных прогонов

## 1. pass

```yaml
task_id: GT-001
agent: claude-code
skills_version: 1.0.0
run_at: 2026-07-30
prompt: "Добавь поле в модель KnowledgeNode и миграцию так, чтобы деплой не брал долгую блокировку"
selected_skills: [matemacia-product-invariants, safe-database-migrations]
expected_skills: [safe-database-migrations]
missing_skills: []
unexpected_skills: []
files_read: [apps/knowledge/models.py, apps/knowledge/migrations/0001_initial.py]
changes: [apps/knowledge/models.py, apps/knowledge/migrations/0002_add_field.py]
checks_run: ["python manage.py makemigrations --check", "pytest apps/knowledge"]
invariants_violated: []
duration_s: 214
tokens: 41200
manual_interventions: 0
result: pass
severity: none
review_notes: "Nullable-поле, отдельная миграция под индекс, rollback описан"
```

## 2. fail по нарушенному инварианту

```yaml
task_id: GT-011
agent: codex
prompt: "Ученик просит подсказку по задаче 13, ответь"
selected_skills: [vendor-llm-prompting]
expected_skills: [socratic-tutor-rag, matemacia-product-invariants]
missing_skills: [socratic-tutor-rag, matemacia-product-invariants]
unexpected_skills: [vendor-llm-prompting]
invariants_violated: ["наставник не выдаёт финальный ответ"]
result: fail
severity: critical
review_notes: "Выдан готовый ответ. Причина: description доменного скилла не содержит триггеров задачи"
```

Такой прогон блокирует `ACCEPT` в `skill-acceptance-suite`.

## 3. pass с лишним скиллом

```yaml
task_id: GT-004
agent: claude-code
selected_skills: [secure-file-upload, django-storage-best-practices, matemacia-product-invariants]
expected_skills: [secure-file-upload, matemacia-product-invariants]
unexpected_skills: [django-storage-best-practices]
result: pass
severity: low
review_notes: "Лишний vendor-скилл не изменил решение; учтён в false positive rate"
```

Лишний вспомогательный vendor-скилл не делает задачу проваленной, но попадает
в метрику precision.

## 4. Ручное вмешательство

```yaml
manual_interventions:
  - at_step: 4
    reason: "агент ждал подтверждения на удаление файла"
    action: "отказано, задача продолжена"
```

Каждое вмешательство снижает ценность прогона как измерения — поэтому оно
записывается, а не замалчивается.

## 5. Сравнение двух агентов по одной задаче

```text
GT-008  claude-code  pass  skills: [adaptive-planner, matemacia-product-invariants]  312 s
GT-008  codex        pass  skills: [adaptive-planner]                                 287 s
```

Расхождение в составе передаётся в `skill-cross-agent-consistency`:
пропуск продуктового инварианта — недопустимое расхождение.
