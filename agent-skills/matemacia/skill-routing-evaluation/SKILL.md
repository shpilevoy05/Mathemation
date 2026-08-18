---
name: skill-routing-evaluation
description: Проверка того, что Claude Code и Codex выбирают правильные скиллы для пользовательской задачи. Использовать при создании нового скилла, изменении его описания или области применения, появлении пересечений между навыками, регулярной активации нерелевантного скилла и при плановой приёмке системы навыков.
metadata:
  owner: platform-engineering
  version: 1.0.0
  status: active
  criticality: high
  last_reviewed: 2026-07-30
  review_cycle_days: 90
  applies_to:
    - claude-code
    - codex
  reviewers:
    - platform-engineering
  replaces: []
  depends_on:
    - skill-golden-task-runner
  conflicts_with: []
---

# skill-routing-evaluation

## Назначение

Измерить качество выбора скиллов агентом и превратить «кажется, он берёт не тот
скилл» в числа: precision, recall, false positive rate, число конфликтов, доля
задач с ручным выбором и расхождения между Claude Code и Codex.

Набор кейсов живёт в [tests/routing](../../tests/routing), инструмент подсчёта —
`agent-skills/scripts/lib/routing_eval.py`.

## Когда активируется

- создаётся новый скилл (до его включения в lock-файл);
- меняется `description` или область применения существующего скилла;
- появляются пересечения между несколькими навыками;
- агент регулярно активирует нерелевантный скилл;
- проводится плановая приёмка системы навыков;
- обновление vendor-репозитория изменило описания навыков.

## Когда не активируется

- нужно проверить структуру `SKILL.md` — это `skill-structure-validator`;
- уже известно, какие скиллы конфликтуют, и нужен разбор приоритета — это
  `skill-conflict-resolution`;
- задача про прикладной код, а не про выбор скиллов;
- требуется полный прогон приёмки — это `skill-acceptance-suite`, который сам
  вызывает routing-тесты;
- нужно понять фактическое использование в проде — это
  `skill-observability-and-usage-analytics`.

## Входные данные

- набор кейсов `tests/routing/*.yaml` (positive, negative, priority);
- список critical скиллов (из `metadata.criticality`);
- записанные прогоны агентов `reports/acceptance/routing-run-<agent>-<дата>.yaml`.

Формат кейса:

```yaml
cases:
  - id: RT-001
    kind: positive | negative | priority
    agent: any | claude-code | codex
    prompt: "Проверь миграцию Django на блокировки и возможность rollback"
    expected: [safe-database-migrations]        # для positive
    must_not_activate: [safe-database-migrations]  # для negative
    priority: [matemacia-product-invariants, mastery-bkt-irt-fsrs]  # для priority
```

Формат прогона:

```yaml
suite: governance-routing
agent: claude-code
run_at: 2026-07-30
manual_overrides: 0
observations:
  - id: RT-001
    selected: [safe-database-migrations]
    order: [safe-database-migrations]
```

## Процедура

1. Проверить полноту набора: у каждого critical скилла есть positive и
   negative кейс.
2. Прогнать кейсы на Claude Code и на Codex, записав фактически выбранные
   скиллы и порядок их применения (см. `skill-golden-task-runner`).
3. Посчитать метрики:
   `python agent-skills/scripts/lib/routing_eval.py --cases agent-skills/tests/routing --check-coverage --run <прогон>`.
4. Сравнить с целевыми значениями.
5. Для каждого провала указать причину: слишком широкое описание, отсутствие
   negative-условий, пересечение областей, конкуренция с vendor-скиллом.
6. Сформировать правки описаний и повторить прогон.

## Ожидаемый результат

```yaml
suite: governance-routing
agent: claude-code
precision: 0.93
recall: 0.96
false_positive_rate: 0.07
priority_cases: 6/6
conflicts: 0
manual_overrides: 1
failures: []
recommendations:
  - skill: skill-metadata-governance
    action: сузить description — активируется на любую правку YAML
```

Целевые значения:

```text
Precision обязательных доменных skills: >= 0.90
Recall критических security skills:     >= 0.95
False positive rate:                    <= 0.10
```

## Запрещено

- менять кейсы под фактическое поведение агента, чтобы метрика «сошлась»;
- принимать систему навыков при недостижении целевых значений по critical
  скиллам;
- оценивать routing только на одном агенте, если скилл объявлен для обоих;
- удалять negative-кейсы вместо сужения описания скилла;
- считать метрики по прогону, где часть кейсов не наблюдалась (это failure,
  а не пропуск).

## Связанные скиллы

- `skill-golden-task-runner` — даёт записанные прогоны, по которым считаются
  метрики;
- `skill-acceptance-suite` — включает routing-тесты в приёмку;
- `skill-conflict-resolution` — разбирает priority-кейсы, которые не сошлись;
- `skill-structure-validator` — ловит причину провалов в описании;
- `skill-cross-agent-consistency` — сравнивает расхождения между агентами.

## Приоритет при конфликтах

1. Продуктовые и юридические инварианты Математики.
2. `skill-conflict-resolution` (иерархия приоритетов важнее метрики).
3. Этот скилл.
4. Рекомендации vendor-скиллов по формату описаний.

Если исправление метрики требует ослабить продуктовый инвариант — метрика
остаётся хуже, инвариант не меняется.

## Критерии приёмки

- каждый critical скилл покрыт минимум одним positive и одним negative кейсом;
- все `id` кейсов уникальны, у каждого есть `prompt`;
- есть прогон для Claude Code и для Codex;
- целевые значения достигнуты либо каждый провал имеет причину и план правки;
- priority-кейсы воспроизводят иерархию из `skill-conflict-resolution`;
- отчёт сохранён в `reports/acceptance/`.

## Проверка

```powershell
python agent-skills\scripts\lib\routing_eval.py --cases agent-skills\tests\routing --check-coverage
powershell -File agent-skills\scripts\validate-skill.ps1 agent-skills\matemacia\skills-governance\skill-routing-evaluation
```
