---
name: skill-acceptance-suite
description: Оркестрация полного набора приёмочных тестов системы навыков — routing, conflicts, security, golden tasks, consistency между Claude Code и Codex, структура и метаданные, lock-файл и инсталляция. Использовать при плановой приёмке, перед релизом системы навыков и после обновления vendor-репозиториев.
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
    - skill-routing-evaluation
    - skill-golden-task-runner
    - skill-structure-validator
    - skills-ci-integrity
  conflicts_with: []
---

# skill-acceptance-suite

## Назначение

Собрать все проверки системы навыков в один прогон и выдать одну рекомендацию:
`ACCEPT`, `ACCEPT_WITH_RESTRICTIONS` или `REJECT`. Скилл не выполняет проверки
сам — он определяет состав, порядок, критерии остановки и формат сводного
отчёта.

## Когда активируется

- плановая приёмка системы навыков;
- перед релизом изменений в `agent-skills`;
- после обновления одного или нескольких vendor-репозиториев;
- после добавления или удаления собственного скилла;
- при переносе системы навыков на новую машину;
- когда нужно решение «можно ли пользоваться системой навыков сейчас».

## Когда не активируется

- нужна одна проверка из набора — вызывается соответствующий скилл напрямую;
- проверка одного `SKILL.md` — это `skill-structure-validator`;
- разбор одного конфликта — это `skill-conflict-resolution`;
- прикладной релиз Django-приложения без изменений в скиллах;
- ежемесячный отчёт об использовании — это
  `skill-observability-and-usage-analytics`.

## Входные данные

- `skills.lock.yaml` и фактическое содержимое `agent-skills`;
- наборы кейсов: `tests/routing`, `tests/conflicts`, `tests/golden-tasks`,
  `tests/cross-agent`;
- доступ к обоим агентам для прогона golden tasks;
- предыдущий приёмочный отчёт из `reports/acceptance/`.

## Состав набора

1. routing tests — `skill-routing-evaluation`;
2. conflict tests — `skill-conflict-resolution`;
3. security tests — `skill-supply-chain-audit` по vendor-каталогу;
4. golden engineering tasks — `skill-golden-task-runner`, минимум 18 задач;
5. consistency tests между Claude Code и Codex —
   `skill-cross-agent-consistency`;
6. проверка структуры `SKILL.md` — `skill-structure-validator`;
7. проверка метаданных — `skill-metadata-governance`;
8. проверка lock-файла — `skills-ci-integrity`;
9. контроль инсталляции — `install-skills.ps1` и сравнение целевых каталогов.

Порядок обязателен: дешёвые детерминированные проверки (6–9) идут раньше
прогонов агентов (1, 4, 5). Провал структуры или lock-файла останавливает
набор — прогонять golden tasks на невалидной системе бессмысленно.

Обязательные golden tasks перечислены в
[tests/golden-tasks/golden-tasks.yaml](../../tests/golden-tasks/golden-tasks.yaml);
разбор результатов — в [references/examples.md](references/examples.md).

## Ожидаемый результат

```yaml
suite_version: 1.0.0
claude_code:
  passed: 17
  failed: 1
codex:
  passed: 18
  failed: 0
critical_failures: []
recommendation: ACCEPT | ACCEPT_WITH_RESTRICTIONS | REJECT
```

Правила рекомендации:

- `ACCEPT` — критических провалов нет, целевые метрики routing достигнуты, все
  18 golden tasks проходят на обоих агентах;
- `ACCEPT_WITH_RESTRICTIONS` — провалы только в некритических скиллах; в отчёте
  явно перечислено, что запрещено делать до исправления;
- `REJECT` — есть критический провал: нарушен продуктовый или security-
  инвариант, `BLOCK` в аудите, расхождение агентов в критическом правиле,
  несоответствие lock-файла.

## Запрещено

- выдавать `ACCEPT`, если хотя бы один critical скилл провалил свой тест;
- заменять golden tasks их сокращённым подмножеством;
- прогонять набор только на одном агенте;
- переиспользовать метрики предыдущего прогона после изменения скиллов;
- маскировать провал переводом задачи в «известную проблему» без владельца
  и даты;
- продолжать набор после провала проверок структуры или lock-файла.

## Связанные скиллы

- `skill-golden-task-runner` — выполняет golden tasks и пишет сырые результаты;
- `skill-routing-evaluation` — даёт метрики выбора скиллов;
- `skill-cross-agent-consistency` — сравнивает агентов;
- `skills-ci-integrity` — те же проверки в автоматическом режиме на merge;
- `skill-observability-and-usage-analytics` — сравнивает приёмку с фактическим
  использованием.

## Приоритет при конфликтах

1. Продуктовые, юридические и security-инварианты Математики.
2. `skill-conflict-resolution`.
3. Этот скилл (состав и порядок приёмки).
4. Отдельные скиллы набора (могут ужесточить свои критерии, но не ослабить).
5. Общие рекомендации по тестированию.

## Критерии приёмки

- отчёт содержит все поля обязательного формата и версию набора;
- в отчёте есть результаты по обоим агентам;
- минимум 18 golden tasks выполнены и зафиксированы;
- `critical_failures` пуст при `ACCEPT`;
- при `ACCEPT_WITH_RESTRICTIONS` перечислены конкретные ограничения;
- отчёт сохранён в `reports/acceptance/` с датой и версией набора;
- каждая провалившая проверка имеет владельца и срок.

## Проверка

```powershell
powershell -File agent-skills\scripts\ci-integrity.ps1
powershell -File agent-skills\scripts\validate-all.ps1 -Strict
python agent-skills\scripts\lib\routing_eval.py --cases agent-skills\tests\routing --check-coverage
```
