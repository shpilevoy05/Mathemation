# Примеры отчётов об использовании

## 1. Запись об активации

```yaml
task_id: T-2026-07-3182
agent: claude-code
skills: [matemacia-product-invariants, adaptive-planner]
outcome: success
duration_s: 176
tokens: 28400
conflicts: 0
manual_overrides: 0
```

Персональных данных нет: только идентификатор задачи и агрегаты. Текст запроса
не сохраняется.

## 2. Ежемесячный отчёт

```yaml
period: 2026-07
skills_version: 1.0.0
tasks_observed: 412
avg_skills_per_task: 2.3
most_useful:
  - skill: matemacia-product-invariants
    activations: 388
    success_rate: 0.94
  - skill: safe-database-migrations
    activations: 61
    success_rate: 0.92
merge_candidates:
  - skills: [skill-structure-validator, skill-metadata-governance]
    reason: "78% активаций совместные, области пересекаются"
    owner: platform-engineering
removal_candidates:
  - skill: vendor-generic-refactoring
    reason: "0 активаций за период, дублирует собственный архитектурный скилл"
    owner: platform-engineering
high_false_positive:
  - skill: vendor-llm-prompting
    false_positive_rate: 0.22
    action: "сузить описание или отключить"
critical_regressions: []
description_changes:
  - skill: socratic-tutor-rag
    change: "добавить триггеры «подсказка», «наставник», «не давать ответ»"
```

## 3. Частота без результата — ловушка

```text
skill A: 300 активаций, success_rate 0.51
skill B:  22 активации, success_rate 0.95
```

Скилл A активируется чаще, но половина задач после него требует переделки:
кандидат на правку описания, не на признание самым полезным.

## 4. Сравнение периодов

```yaml
period: 2026-07
compared_to: 2026-06
note: "в июле добавлено 2 скилла и обновлён 1 vendor — прямое сравнение avg_skills_per_task некорректно"
```

## 5. Отключение детального логирования

```yaml
logging:
  level: aggregate | detailed
  detailed_enabled_until: 2026-08-15
  rationale: "расследование роста токенов в задачах планировщика"
```

Детальный режим включается на срок и с причиной, затем возвращается к
агрегатам.
