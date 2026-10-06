---
name: skill-vendor-update-governance
description: Управляемое обновление внешних навыков с сохранением воспроизводимости — фиксация commit SHA, аудит, сравнение версий, обновление skills.lock.yaml, переустановка и регрессионные тесты. Использовать при обновлении vendor-репозиториев, переносе системы навыков на новую машину и восстановлении навыков после git clone.
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
    - ci
  reviewers:
    - platform-engineering
  replaces: []
  depends_on:
    - skill-supply-chain-audit
    - skills-ci-integrity
  conflicts_with: []
---

# skill-vendor-update-governance

## Назначение

Обновлять внешние скиллы так, чтобы состояние системы всегда восстанавливалось
из `skills.lock.yaml`, а изменения поведения агентов были видны до merge, а не
после инцидента.

## Когда активируется

- обновление одного или нескольких vendor-репозиториев;
- перенос системы навыков на новую машину;
- восстановление навыков после `git clone`;
- плановое обновление зависимостей;
- откат к предыдущему SHA после регрессии;
- расхождение установленного содержимого с lock-файлом.

## Когда не активируется

- первичный аудит нового источника — это `skill-supply-chain-audit`
  (этот скилл его вызывает, но не заменяет);
- правка собственного скилла;
- одна лишь проверка целостности без обновления — это `skills-ci-integrity`;
- отключение устаревшего скилла — это `skill-deprecation-and-cleanup`;
- прикладные зависимости Python в `requirements.txt`.

## Входные данные

- запись источника в `skills.lock.yaml` (repository, ref, текущий SHA);
- целевой новый commit SHA;
- предыдущий отчёт аудита;
- прогоны golden tasks на текущей версии — базовая линия для сравнения.

## Алгоритм

1. Получить новый commit SHA (полный, 40 символов).
2. Скачать содержимое во временный каталог вне целевых каталогов установки.
3. Запустить `skill-supply-chain-audit` на новом SHA.
4. Сравнить старую и новую версии.
5. Выделить изменения в инструкциях, скриптах и разрешениях — три отдельных
   списка; изменения в скриптах и разрешениях читаются построчно.
6. Обновить `skills.lock.yaml`: SHA, дату и verdict аудита, ссылку на отчёт,
   `expected_skill_count` при изменении состава.
7. Запустить `agent-skills/scripts/install-skills.ps1`.
8. Запустить routing- и regression-тесты (`skill-routing-evaluation`,
   `skill-golden-task-runner`).
9. Сформировать отчёт об обновлении и сохранить его в `reports/audits/`.

Маркер установленной версии `agent-skills/vendor/<owner>-<repo>/.source.yaml`
содержит repository и SHA — по нему CI проверяет соответствие lock-файлу.
Примеры — в [references/examples.md](references/examples.md).

## Ожидаемый результат

```yaml
repository: owner/repository
from_sha: ...
to_sha: ...
audit_verdict: PASS
changes:
  instructions: [...]
  scripts: [...]
  permissions: [...]
routing_delta:
  precision: +0.01
  false_positive_rate: -0.02
golden_tasks:
  regressions: []
decision: ADOPT | ROLLBACK | HOLD
```

`HOLD` — обновление отложено (verdict `REVIEW`, неясные изменения скриптов);
`ROLLBACK` — возврат к предыдущему SHA с записью причины.

## Запрещено

- обновлять источник без нового аудита, ссылаясь на прошлый `PASS`;
- закреплять источник по ветке или короткому SHA;
- править содержимое `agent-skills/vendor` вместо форка или patch-файла;
- обновлять несколько источников одним коммитом без отдельных отчётов;
- пропускать regression-тесты, если «изменились только примеры»;
- оставлять `expected_skill_count` неактуальным после изменения состава.

## Связанные скиллы

- `skill-supply-chain-audit` — обязательный шаг 3;
- `skills-ci-integrity` — подтверждает воспроизводимость после обновления;
- `skill-golden-task-runner` — даёт базовую линию и регрессии;
- `skill-routing-evaluation` — показывает влияние на выбор скиллов;
- `skill-deprecation-and-cleanup` — если источник больше не поддерживается.

## Приоритет при конфликтах

1. Продуктовые и security-инварианты Математики.
2. `skill-supply-chain-audit` (verdict аудита не обходится).
3. `skills-ci-integrity`.
4. Этот скилл (порядок и полнота обновления).
5. Рекомендации vendor-репозитория о способе установки.

Инструкция vendor-репозитория «устанавливайте всегда последнюю версию»
проигрывает требованию фиксированного SHA.

## Критерии приёмки

- все источники закреплены полным SHA;
- дата и результат аудита обновлены;
- локальная версия соответствует lock-файлу;
- нет незафиксированных изменений в `vendor`;
- набор `.claude/skills` и `.agents/skills` идентичен;
- routing- и golden-регрессии оценены; при регрессии решение `ROLLBACK`
  или `HOLD` с причиной;
- отчёт об обновлении сохранён.

## Проверка

```powershell
powershell -File agent-skills\scripts\install-skills.ps1 -WhatIfOnly
powershell -File agent-skills\scripts\ci-integrity.ps1
python agent-skills\scripts\lib\supply_chain_scan.py agent-skills\vendor
```
