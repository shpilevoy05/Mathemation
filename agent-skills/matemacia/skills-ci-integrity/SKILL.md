---
name: skills-ci-integrity
description: Проверка целостности системы навыков в CI — связь vendor-скиллов с lock-файлом, полные commit SHA, соответствие установленной версии, структура и метаданные собственных скиллов, идентичность каталогов установки, routing-тесты и golden tasks. Использовать в pull request, перед merge и перед релизом.
metadata:
  owner: platform-engineering
  version: 1.0.0
  status: active
  criticality: critical
  last_reviewed: 2026-07-30
  review_cycle_days: 90
  applies_to:
    - claude-code
    - codex
    - ci
  reviewers:
    - platform-engineering
    - security
  replaces: []
  depends_on:
    - skill-structure-validator
    - skill-routing-evaluation
  conflicts_with: []
---

# skills-ci-integrity

## Назначение

Сделать состояние системы навыков воспроизводимым: любой клон репозитория с
тем же lock-файлом даёт тот же набор скиллов того же содержания. Результат —
`PASS` или `FAIL`; `FAIL` блокирует merge и release.

Реализация — `agent-skills/scripts/ci-integrity.ps1` (12 проверок, без запуска
агентов).

## Когда активируется

- открыт или обновлён pull request, затрагивающий `agent-skills`;
- перед merge в основную ветку;
- перед релизом;
- после `git clone` на новой машине;
- после запуска `install-skills.ps1`;
- при подозрении на расхождение локального состояния с lock-файлом.

## Когда не активируется

- нужна одна проверка структуры скилла локально — это
  `skill-structure-validator`;
- требуется прогон агентов и метрики — это `skill-acceptance-suite`;
- аудит нового внешнего источника — это `skill-supply-chain-audit`;
- изменения только в `apps/` без правок скиллов;
- анализ пользы скиллов — это `skill-observability-and-usage-analytics`.

## Входные данные

- `skills.lock.yaml`;
- содержимое `agent-skills/matemacia` и `agent-skills/vendor`;
- каталоги установки `.claude/skills` и `.agents/skills`;
- `agent-skills/CHANGELOG.md`;
- наборы кейсов `tests/routing`, `tests/golden-tasks`;
- записанные прогоны в `reports/acceptance/`, если есть.

## Обязательные проверки

1. Каждый vendor-skill связан с записью в `skills.lock.yaml`.
2. Для каждого источника указан полный commit SHA и аудит с verdict `PASS`.
3. Фактическая версия соответствует lock-файлу (маркер `.source.yaml`).
4. Повторный аудит не возвращает `BLOCK`.
5. Количество установленных навыков соответствует `expected_skill_count`.
6. `.claude/skills` и `.agents/skills` содержат одинаковый набор.
7. В `agent-skills/vendor` нет ручных незакоммиченных изменений.
8. Каждый собственный skill имеет обязательную структуру.
9. Метаданные проходят schema validation.
10. Изменения critical skills получили обязательное ревью: запись в
    `CHANGELOG.md` с версией и заполненный `metadata.reviewers`.
11. Routing tests пройдены: покрытие critical скиллов и метрики записанных
    прогонов.
12. Golden tasks не имеют критических регрессий: описано минимум 18 задач,
    в записанных прогонах нет `fail` с severity `critical` или `high`.

Проверки 5 и 6 пропускаются только явным флагом `-SkipInstallChecks` —
например, в задании, которое запускается до установки.

## Ожидаемый результат

```text
PASS — система навыков воспроизводима и пригодна к использованию;
FAIL — merge или release блокируется.
```

Вывод содержит строку по каждой проверке со статусом `PASS`, `FAIL` или `SKIP`
и списком конкретных проблем. Пример разбора — в
[references/examples.md](references/examples.md).

## Запрещено

- пропускать проверки, чтобы «разблокировать» merge;
- считать `SKIP` эквивалентом `PASS` в отчёте о релизе;
- коммитить `.claude/skills` и `.agents/skills` вместо восстановления из
  lock-файла;
- править lock-файл под фактическое состояние диска вместо переустановки;
- отключать проверку 7, потому что «правка в vendor временная»;
- изменять критический скилл без записи в `CHANGELOG.md` и ревьюеров.

## Связанные скиллы

- `skill-structure-validator` — реализует проверки 8 и 9;
- `skill-metadata-governance` — задаёт схему метаданных для проверки 9;
- `skill-supply-chain-audit` — источник verdict для проверок 2 и 4;
- `skill-vendor-update-governance` — приводит систему в состояние, при котором
  проверки 1–3 проходят;
- `skill-acceptance-suite` — надмножество, добавляющее прогоны агентов.

## Приоритет при конфликтах

1. Продуктовые и security-инварианты Математики.
2. Этот скилл: `FAIL` нельзя обойти ни одним другим скиллом.
3. `skill-vendor-update-governance` и прочие governance-скиллы.
4. Vendor-рекомендации по организации CI.

## Критерии приёмки

- все 12 проверок реализованы и выполняются одной командой;
- в отчёте по каждой проверке указан статус и причины провала;
- `FAIL` даёт ненулевой код выхода;
- проверки детерминированы: не зависят от сети и запуска агентов;
- `SKIP` возможен только по явному флагу или при отсутствии vendor-скиллов;
- вывод пригоден для вставки в комментарий pull request.

## Проверка

```powershell
powershell -File agent-skills\scripts\install-skills.ps1
powershell -File agent-skills\scripts\ci-integrity.ps1
```
